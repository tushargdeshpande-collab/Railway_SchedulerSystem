"""
OR-Tools CP-SAT maintenance block scheduler.

Schedules synthetic railway maintenance tasks into conflict-free
maintenance block windows. The model prioritises critical work,
low-traffic windows, cross-department bundling, resource safety
and correct task-dependency sequencing.
"""

import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from backend.app.data.master_data import (
    SYNTHETIC_DATA_DISCLAIMER,
)
from backend.app.schemas.domain import (
    BlockStatus,
    BlockWindow,
    MaintenanceTask,
    PriorityLevel,
    ScheduledBlock,
    TrafficLevel,
)


BASE_DATA_PATH = Path(
    "synthetic_data/generated/base"
)

SOLVER_TIME_LIMIT_SECONDS = 30

TRAFFIC_PENALTY = {
    TrafficLevel.LOW: 0,
    TrafficLevel.MEDIUM: 150,
    TrafficLevel.HIGH: 500,
    TrafficLevel.PEAK: 1000,
}

TRAIN_IMPACT_MINUTES = {
    TrafficLevel.LOW: 0.0,
    TrafficLevel.MEDIUM: 2.0,
    TrafficLevel.HIGH: 5.0,
    TrafficLevel.PEAK: 10.0,
}

PRIORITY_LEVEL_BONUS = {
    PriorityLevel.CRITICAL: 2500,
    PriorityLevel.HIGH: 1000,
    PriorityLevel.MEDIUM: 300,
    PriorityLevel.LOW: 0,
}


def load_json(path: Path) -> Any:
    with path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        return json.load(input_file)


def load_inputs() -> tuple[
    list[MaintenanceTask],
    list[BlockWindow],
    dict[str, list[str]],
]:
    task_records = load_json(
        BASE_DATA_PATH
        / "scored_maintenance_tasks.json"
    )

    block_records = load_json(
        BASE_DATA_PATH
        / "block_windows.json"
    )

    candidate_report = load_json(
        BASE_DATA_PATH
        / "candidate_report.json"
    )

    tasks = [
        MaintenanceTask.model_validate(record)
        for record in task_records
    ]

    blocks = [
        BlockWindow.model_validate(record)
        for record in block_records
    ]

    candidate_map: dict[str, list[str]] = (
        candidate_report["candidate_map"]
    )

    return tasks, blocks, candidate_map


def assignment_reward(
    task: MaintenanceTask,
    block: BlockWindow,
    horizon_start: datetime,
) -> int:
    priority_score = (
        task.priority_score
        if task.priority_score is not None
        else 0.0
    )

    priority_level = (
        task.priority_level
        if task.priority_level is not None
        else PriorityLevel.LOW
    )

    priority_reward = int(
        priority_score * 100
    )

    overdue_reward = (
        min(task.overdue_days, 60) * 20
    )

    level_bonus = PRIORITY_LEVEL_BONUS[
        priority_level
    ]

    lateness_days = max(
        0,
        (
            block.start_time.date()
            - task.due_date
        ).days,
    )

    lateness_penalty = min(
        lateness_days * 25,
        1500,
    )

    horizon_day = (
        block.start_time.date()
        - horizon_start.date()
    ).days

    later_date_penalty = horizon_day * 5

    return (
        priority_reward
        + overdue_reward
        + level_bonus
        - TRAFFIC_PENALTY[
            block.traffic_level
        ]
        - lateness_penalty
        - later_date_penalty
    )


def solve_schedule(
    tasks: list[MaintenanceTask],
    blocks: list[BlockWindow],
    candidate_map: dict[str, list[str]],
) -> tuple[
    cp_model.CpSolver,
    int,
    dict[tuple[str, str], cp_model.IntVar],
]:
    model = cp_model.CpModel()

    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    block_lookup = {
        block.block_id: block
        for block in blocks
    }

    considered_blocks = [
        block_lookup[block_id]
        for block_ids in candidate_map.values()
        for block_id in block_ids
    ]

    horizon_start = min(
        block.start_time
        for block in considered_blocks
    )

    assignment_variables = {}
    scheduled_variables = {}

    assignments_by_task = defaultdict(list)
    assignments_by_block = defaultdict(list)
    assignments_by_department_block = (
        defaultdict(list)
    )

    team_intervals = defaultdict(list)

    for task in tasks:
        scheduled_variables[task.task_id] = (
            model.new_bool_var(
                f"scheduled_{task.task_id}"
            )
        )

        for block_id in candidate_map[
            task.task_id
        ]:
            block = block_lookup[block_id]

            assignment = model.new_bool_var(
                f"x_{task.task_id}_{block_id}"
            )

            assignment_variables[
                (task.task_id, block_id)
            ] = assignment

            assignments_by_task[
                task.task_id
            ].append(assignment)

            assignments_by_block[
                block_id
            ].append(assignment)

            department_block_key = (
                block_id,
                task.department.value,
            )

            assignments_by_department_block[
                department_block_key
            ].append(assignment)

            start_minutes = int(
                (
                    block.start_time
                    - horizon_start
                ).total_seconds()
                / 60
            )

            task_interval = (
                model
                .new_optional_fixed_size_interval_var(
                    start_minutes,
                    task.minimum_block_minutes,
                    assignment,
                    (
                        f"interval_"
                        f"{task.task_id}_"
                        f"{block_id}"
                    ),
                )
            )

            team_intervals[
                task.required_team
            ].append(task_interval)

    # Each task is scheduled at most once.
    for task in tasks:
        task_assignments = (
            assignments_by_task[
                task.task_id
            ]
        )

        model.add(
            sum(task_assignments)
            == scheduled_variables[
                task.task_id
            ]
        )

        # Critical work must be included.
        if (
            task.priority_level
            == PriorityLevel.CRITICAL
        ):
            model.add(
                scheduled_variables[
                    task.task_id
                ]
                == 1
            )

    # A shared block can contain at most one task
    # from each department.
    for assignments in (
        assignments_by_department_block.values()
    ):
        model.add(
            sum(assignments) <= 1
        )

    block_used_variables = {}
    bundled_block_variables = {}

    # A block can hold up to three tasks:
    # one Engineering, one S&T and one Traction task.
    for block_id, assignments in (
        assignments_by_block.items()
    ):
        block_used = model.new_bool_var(
            f"used_{block_id}"
        )

        bundled_block = model.new_bool_var(
            f"bundled_{block_id}"
        )

        block_used_variables[
            block_id
        ] = block_used

        bundled_block_variables[
            block_id
        ] = bundled_block

        assignment_count = sum(assignments)

        model.add(
            assignment_count <= 3
        )

        model.add(
            assignment_count >= block_used
        )

        model.add(
            assignment_count
            <= 3 * block_used
        )

        # bundled_block = 1 only when at least
        # two tasks share the block.
        model.add(
            assignment_count
            >= 2 * bundled_block
        )

        model.add(
            assignment_count
            <= 1 + 2 * bundled_block
        )

    # A maintenance team cannot work on two
    # overlapping tasks.
    for intervals in team_intervals.values():
        model.add_no_overlap(intervals)

    # Calculate the selected start time for
    # every maintenance task.
    assigned_start_expressions = {}

    for task in tasks:
        start_terms = []

        for block_id in candidate_map[
            task.task_id
        ]:
            block = block_lookup[block_id]

            start_minutes = int(
                (
                    block.start_time
                    - horizon_start
                ).total_seconds()
                / 60
            )

            assignment = (
                assignment_variables[
                    (task.task_id, block_id)
                ]
            )

            start_terms.append(
                start_minutes * assignment
            )

        assigned_start_expressions[
            task.task_id
        ] = sum(start_terms)

    # Correct dependency constraint:
    # a dependent task can start only after
    # its prerequisite task has finished.
    for task in tasks:
        for dependency_id in (
            task.dependency_task_ids
        ):
            if (
                dependency_id
                not in scheduled_variables
            ):
                continue

            dependency_task = (
                task_lookup[dependency_id]
            )

            dependency_duration = (
                dependency_task
                .minimum_block_minutes
            )

            # A dependent task may be scheduled only
            # if its prerequisite is also scheduled.
            model.add(
                scheduled_variables[
                    task.task_id
                ]
                <= scheduled_variables[
                    dependency_id
                ]
            )

            # Dependent start >= prerequisite start
            # + prerequisite duration.
            model.add(
                assigned_start_expressions[
                    task.task_id
                ]
                >= (
                    assigned_start_expressions[
                        dependency_id
                    ]
                    + dependency_duration
                )
            ).only_enforce_if(
                scheduled_variables[
                    task.task_id
                ]
            )

    objective_terms = []

    for assignment_key, assignment in (
        assignment_variables.items()
    ):
        task_id, block_id = assignment_key

        task = task_lookup[task_id]
        block = block_lookup[block_id]

        reward = assignment_reward(
            task,
            block,
            horizon_start,
        )

        objective_terms.append(
            reward * assignment
        )

    # Reward cross-department bundling.
    for bundled_block in (
        bundled_block_variables.values()
    ):
        objective_terms.append(
            800 * bundled_block
        )

    # Penalise use of separate blocks.
    for block_used in (
        block_used_variables.values()
    ):
        objective_terms.append(
            -250 * block_used
        )

    model.maximize(
        sum(objective_terms)
    )

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = (
        SOLVER_TIME_LIMIT_SECONDS
    )

    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = False

    status = solver.solve(model)

    return (
        solver,
        status,
        assignment_variables,
    )


def build_outputs(
    solver: cp_model.CpSolver,
    status: int,
    tasks: list[MaintenanceTask],
    blocks: list[BlockWindow],
    candidate_map: dict[str, list[str]],
    assignment_variables: dict[
        tuple[str, str],
        cp_model.IntVar,
    ],
    runtime_seconds: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    block_lookup = {
        block.block_id: block
        for block in blocks
    }

    selected_by_block = defaultdict(list)
    scheduled_task_ids = set()

    for assignment_key, variable in (
        assignment_variables.items()
    ):
        task_id, block_id = assignment_key

        if solver.value(variable) == 1:
            selected_by_block[
                block_id
            ].append(
                task_lookup[task_id]
            )

            scheduled_task_ids.add(
                task_id
            )

    optimized_schedule = []

    sorted_blocks = sorted(
        selected_by_block.items(),
        key=lambda item: (
            block_lookup[
                item[0]
            ].start_time
        ),
    )

    for block_id, selected_tasks in (
        sorted_blocks
    ):
        block = block_lookup[block_id]

        departments = list(
            dict.fromkeys(
                task.department
                for task in selected_tasks
            )
        )

        required_minutes = max(
            task.minimum_block_minutes
            for task in selected_tasks
        )

        scheduled_end = (
            block.start_time
            + timedelta(
                minutes=required_minutes
            )
        )

        utilization = round(
            required_minutes
            / block.available_duration_minutes
            * 100,
            2,
        )

        is_bundled = (
            len(departments) >= 2
        )

        task_ids = [
            task.task_id
            for task in selected_tasks
        ]

        task_text = ", ".join(task_ids)

        explanation = (
            f"Selected {block.block_id} for "
            f"{task_text}. Corridor, section, "
            "duration, team, equipment and "
            "disconnection constraints are "
            f"satisfied. Traffic level is "
            f"{block.traffic_level.value}."
        )

        if is_bundled:
            explanation += (
                f" This block coordinates "
                f"{len(departments)} departments, "
                "avoiding separate possessions."
            )

        schedule = ScheduledBlock(
            schedule_id=(
                f"SCHEDULE-"
                f"{len(optimized_schedule) + 1:05d}"
            ),
            block_id=block.block_id,
            corridor_id=block.corridor_id,
            section_id=block.section_id,
            track_id=block.track_id,
            scheduled_start=block.start_time,
            scheduled_end=scheduled_end,
            task_ids=task_ids,
            departments=departments,
            utilization_percent=utilization,
            estimated_train_impact_minutes=(
                TRAIN_IMPACT_MINUTES[
                    block.traffic_level
                ]
            ),
            is_bundled=is_bundled,
            is_locked=False,
            status=BlockStatus.PROPOSED,
            explanation=explanation,
        )

        optimized_schedule.append(
            schedule.model_dump(
                mode="json"
            )
        )

    unscheduled_tasks = []

    for task in tasks:
        if (
            task.task_id
            in scheduled_task_ids
        ):
            continue

        candidate_count = len(
            candidate_map.get(
                task.task_id,
                [],
            )
        )

        if candidate_count == 0:
            reason = (
                "No feasible block satisfies "
                "the task requirements."
            )
        else:
            reason = (
                "Feasible blocks exist, but the "
                "task was not selected because "
                "higher-value work, dependencies, "
                "resources or coordination created "
                "a better overall plan."
            )

        priority_level = (
            task.priority_level.value
            if task.priority_level is not None
            else None
        )

        unscheduled_tasks.append(
            {
                "task_id": task.task_id,
                "department": (
                    task.department.value
                ),
                "corridor_id": (
                    task.corridor_id
                ),
                "section_id": (
                    task.section_id
                ),
                "priority_score": (
                    task.priority_score
                ),
                "priority_level": (
                    priority_level
                ),
                "overdue_days": (
                    task.overdue_days
                ),
                "candidate_count": (
                    candidate_count
                ),
                "reason": reason,
                "synthetic_data": True,
            }
        )

    scheduled_priority_counts = Counter()

    for task_id in scheduled_task_ids:
        level = (
            task_lookup[
                task_id
            ].priority_level
        )

        if level is not None:
            scheduled_priority_counts[
                level.value
            ] += 1

    bundled_blocks = sum(
        int(schedule["is_bundled"])
        for schedule in optimized_schedule
    )

    tasks_in_bundled_blocks = sum(
        len(schedule["task_ids"])
        for schedule in optimized_schedule
        if schedule["is_bundled"]
    )

    if optimized_schedule:
        average_utilization = (
            sum(
                float(
                    schedule[
                        "utilization_percent"
                    ]
                )
                for schedule
                in optimized_schedule
            )
            / len(optimized_schedule)
        )
    else:
        average_utilization = 0.0

    total_train_impact = sum(
        float(
            schedule[
                "estimated_train_impact_minutes"
            ]
        )
        for schedule in optimized_schedule
    )

    metrics = {
        "disclaimer": (
            SYNTHETIC_DATA_DISCLAIMER
        ),
        "solver_status": (
            solver.status_name(status)
        ),
        "solver_runtime_seconds": round(
            runtime_seconds,
            3,
        ),
        "objective_value": round(
            solver.objective_value,
            2,
        ),
        "total_tasks": len(tasks),
        "scheduled_tasks": len(
            scheduled_task_ids
        ),
        "unscheduled_tasks": len(
            unscheduled_tasks
        ),
        "critical_tasks_scheduled": (
            scheduled_priority_counts.get(
                PriorityLevel.CRITICAL.value,
                0,
            )
        ),
        "high_tasks_scheduled": (
            scheduled_priority_counts.get(
                PriorityLevel.HIGH.value,
                0,
            )
        ),
        "blocks_used": len(
            optimized_schedule
        ),
        "bundled_blocks": (
            bundled_blocks
        ),
        "tasks_in_bundled_blocks": (
            tasks_in_bundled_blocks
        ),
        "average_block_utilization_percent": round(
            average_utilization,
            2,
        ),
        "estimated_total_train_impact_minutes": (
            total_train_impact
        ),
    }

    return (
        optimized_schedule,
        unscheduled_tasks,
        metrics,
    )


def save_outputs(
    schedules: list[dict[str, Any]],
    unscheduled_tasks: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> None:
    output_files = {
        "optimized_schedule.json": schedules,
        "unscheduled_tasks.json": (
            unscheduled_tasks
        ),
        "optimization_metrics.json": metrics,
    }

    for filename, data in (
        output_files.items()
    ):
        output_path = (
            BASE_DATA_PATH / filename
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                indent=2,
            )


def print_summary(
    metrics: dict[str, Any],
) -> None:
    print(
        SYNTHETIC_DATA_DISCLAIMER
    )

    print(
        f"Solver status: "
        f"{metrics['solver_status']}"
    )

    print(
        f"Runtime: "
        f"{metrics['solver_runtime_seconds']} "
        "seconds"
    )

    print(
        f"Scheduled tasks: "
        f"{metrics['scheduled_tasks']}/"
        f"{metrics['total_tasks']}"
    )

    print(
        f"Critical tasks scheduled: "
        f"{metrics['critical_tasks_scheduled']}"
    )

    print(
        f"High-priority tasks scheduled: "
        f"{metrics['high_tasks_scheduled']}"
    )

    print(
        f"Blocks used: "
        f"{metrics['blocks_used']}"
    )

    print(
        f"Bundled blocks: "
        f"{metrics['bundled_blocks']}"
    )

    print(
        f"Tasks in bundled blocks: "
        f"{metrics['tasks_in_bundled_blocks']}"
    )

    print(
        "Average block utilization: "
        f"{metrics['average_block_utilization_percent']}%"
    )

    print(
        "Estimated train impact: "
        f"{metrics['estimated_total_train_impact_minutes']} "
        "minutes"
    )


if __name__ == "__main__":
    (
        maintenance_tasks,
        block_windows,
        candidates,
    ) = load_inputs()

    started_at = time.perf_counter()

    (
        solver,
        solver_status,
        assignment_variables,
    ) = solve_schedule(
        maintenance_tasks,
        block_windows,
        candidates,
    )

    runtime = (
        time.perf_counter()
        - started_at
    )

    if solver_status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        raise SystemExit(
            "No feasible schedule found. "
            f"Status: "
            f"{solver.status_name(solver_status)}"
        )

    (
        schedule_output,
        unscheduled_output,
        metrics_output,
    ) = build_outputs(
        solver,
        solver_status,
        maintenance_tasks,
        block_windows,
        candidates,
        assignment_variables,
        runtime,
    )

    save_outputs(
        schedule_output,
        unscheduled_output,
        metrics_output,
    )

    print_summary(
        metrics_output
    )

    print(
        "Optimization outputs saved to: "
        f"{BASE_DATA_PATH.resolve()}"
    )