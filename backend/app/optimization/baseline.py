"""
Decentralized maintenance-planning baseline.

Simulates Engineering, S&T and Traction Distribution processing
their maintenance requests independently. Tasks use separate blocks;
no cross-department bundling or global optimization is performed.
"""

import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

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

TRAIN_IMPACT_MINUTES = {
    TrafficLevel.LOW: 0.0,
    TrafficLevel.MEDIUM: 2.0,
    TrafficLevel.HIGH: 5.0,
    TrafficLevel.PEAK: 10.0,
}


def load_json(filename: str) -> Any:
    path = BASE_DATA_PATH / filename

    with path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        return json.load(input_file)


def intervals_overlap(
    first_start,
    first_end,
    second_start,
    second_end,
) -> bool:
    return (
        first_start < second_end
        and second_start < first_end
    )


def load_inputs() -> tuple[
    list[MaintenanceTask],
    list[BlockWindow],
    dict[str, list[str]],
]:
    tasks = [
        MaintenanceTask.model_validate(record)
        for record in load_json(
            "scored_maintenance_tasks.json"
        )
    ]

    blocks = [
        BlockWindow.model_validate(record)
        for record in load_json(
            "block_windows.json"
        )
    ]

    candidate_report = load_json(
        "candidate_report.json"
    )

    candidate_map: dict[str, list[str]] = (
        candidate_report["candidate_map"]
    )

    return tasks, blocks, candidate_map


def team_is_available(
    team_bookings: list[tuple],
    proposed_start,
    proposed_end,
) -> bool:
    return not any(
        intervals_overlap(
            proposed_start,
            proposed_end,
            existing_start,
            existing_end,
        )
        for existing_start, existing_end
        in team_bookings
    )


def generate_baseline(
    tasks: list[MaintenanceTask],
    blocks: list[BlockWindow],
    candidate_map: dict[str, list[str]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    block_lookup = {
        block.block_id: block
        for block in blocks
    }

    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    used_blocks: set[str] = set()
    scheduled_task_lookup = {}
    team_bookings = defaultdict(list)

    baseline_schedules = []
    unscheduled_tasks = []

    # Tasks without dependencies are processed first.
    # Within that group, departments effectively submit
    # work in due-date order.
    task_queue = sorted(
        tasks,
        key=lambda task: (
            bool(task.dependency_task_ids),
            task.due_date,
            task.detection_date,
            task.task_id,
        ),
    )

    remaining_tasks = list(task_queue)
    maximum_passes = len(tasks) + 1
    pass_number = 0

    while remaining_tasks and pass_number < maximum_passes:
        pass_number += 1
        progress_made = False
        next_pass = []

        for task in remaining_tasks:
            dependency_finish = None
            dependencies_ready = True

            for dependency_id in (
                task.dependency_task_ids
            ):
                dependency_schedule = (
                    scheduled_task_lookup.get(
                        dependency_id
                    )
                )

                if dependency_schedule is None:
                    dependencies_ready = False
                    break

                dependency_task = (
                    task_lookup[dependency_id]
                )

                finish_time = (
                    dependency_schedule[
                        "scheduled_start_object"
                    ]
                    + timedelta(
                        minutes=(
                            dependency_task
                            .minimum_block_minutes
                        )
                    )
                )

                if (
                    dependency_finish is None
                    or finish_time
                    > dependency_finish
                ):
                    dependency_finish = finish_time

            if not dependencies_ready:
                next_pass.append(task)
                continue

            selected_block = None

            for block_id in candidate_map.get(
                task.task_id,
                [],
            ):
                if block_id in used_blocks:
                    continue

                block = block_lookup[block_id]

                task_start = block.start_time
                task_end = (
                    task_start
                    + timedelta(
                        minutes=(
                            task.minimum_block_minutes
                        )
                    )
                )

                if (
                    dependency_finish is not None
                    and task_start
                    < dependency_finish
                ):
                    continue

                if not team_is_available(
                    team_bookings[
                        task.required_team
                    ],
                    task_start,
                    task_end,
                ):
                    continue

                selected_block = block
                break

            if selected_block is None:
                next_pass.append(task)
                continue

            task_start = selected_block.start_time

            task_end = (
                task_start
                + timedelta(
                    minutes=(
                        task.minimum_block_minutes
                    )
                )
            )

            utilization = round(
                task.minimum_block_minutes
                / (
                    selected_block
                    .available_duration_minutes
                )
                * 100,
                2,
            )

            schedule = ScheduledBlock(
                schedule_id=(
                    f"BASELINE-"
                    f"{len(baseline_schedules) + 1:05d}"
                ),
                block_id=selected_block.block_id,
                corridor_id=task.corridor_id,
                section_id=task.section_id,
                track_id=selected_block.track_id,
                scheduled_start=task_start,
                scheduled_end=task_end,
                task_ids=[task.task_id],
                departments=[task.department],
                utilization_percent=utilization,
                estimated_train_impact_minutes=(
                    TRAIN_IMPACT_MINUTES[
                        selected_block.traffic_level
                    ]
                ),
                is_bundled=False,
                is_locked=False,
                status=BlockStatus.PROPOSED,
                explanation=(
                    f"{task.department.value} independently "
                    f"selected the first available valid block "
                    f"for {task.task_id}. No cross-department "
                    "bundling was attempted."
                ),
            )

            schedule_record = (
                schedule.model_dump(
                    mode="json"
                )
            )

            baseline_schedules.append(
                schedule_record
            )

            used_blocks.add(
                selected_block.block_id
            )

            team_bookings[
                task.required_team
            ].append(
                (task_start, task_end)
            )

            scheduled_task_lookup[
                task.task_id
            ] = {
                "schedule": schedule_record,
                "scheduled_start_object": (
                    task_start
                ),
            }

            progress_made = True

        if not progress_made:
            remaining_tasks = next_pass
            break

        remaining_tasks = next_pass

    for task in remaining_tasks:
        unscheduled_tasks.append(
            {
                "task_id": task.task_id,
                "department": (
                    task.department.value
                ),
                "priority_score": (
                    task.priority_score
                ),
                "priority_level": (
                    task.priority_level.value
                    if task.priority_level
                    is not None
                    else None
                ),
                "overdue_days": (
                    task.overdue_days
                ),
                "reason": (
                    "No separate block could be allocated "
                    "by the decentralized greedy process."
                ),
                "synthetic_data": True,
            }
        )

    baseline_schedules.sort(
        key=lambda schedule: (
            schedule["scheduled_start"]
        )
    )

    return (
        baseline_schedules,
        unscheduled_tasks,
    )


def calculate_baseline_metrics(
    tasks: list[MaintenanceTask],
    schedules: list[dict[str, Any]],
    unscheduled: list[dict[str, Any]],
) -> dict[str, Any]:
    scheduled_task_ids = {
        task_id
        for schedule in schedules
        for task_id in schedule["task_ids"]
    }

    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    priority_counts = Counter()

    for task_id in scheduled_task_ids:
        level = (
            task_lookup[
                task_id
            ].priority_level
        )

        if level is not None:
            priority_counts[
                level.value
            ] += 1

    average_utilization = (
        sum(
            float(
                schedule[
                    "utilization_percent"
                ]
            )
            for schedule in schedules
        )
        / len(schedules)
        if schedules
        else 0.0
    )

    train_impact = sum(
        float(
            schedule[
                "estimated_train_impact_minutes"
            ]
        )
        for schedule in schedules
    )

    return {
        "disclaimer": (
            SYNTHETIC_DATA_DISCLAIMER
        ),
        "planning_method": (
            "Decentralized greedy baseline"
        ),
        "total_tasks": len(tasks),
        "scheduled_tasks": len(
            scheduled_task_ids
        ),
        "unscheduled_tasks": len(
            unscheduled
        ),
        "critical_tasks_scheduled": (
            priority_counts.get(
                PriorityLevel.CRITICAL.value,
                0,
            )
        ),
        "high_tasks_scheduled": (
            priority_counts.get(
                PriorityLevel.HIGH.value,
                0,
            )
        ),
        "blocks_used": len(schedules),
        "bundled_blocks": 0,
        "tasks_in_bundled_blocks": 0,
        "average_block_utilization_percent": round(
            average_utilization,
            2,
        ),
        "estimated_total_train_impact_minutes": (
            train_impact
        ),
    }


def build_comparison(
    baseline_metrics: dict[str, Any],
    optimized_metrics: dict[str, Any],
) -> dict[str, Any]:
    baseline_blocks = baseline_metrics[
        "blocks_used"
    ]

    optimized_blocks = optimized_metrics[
        "blocks_used"
    ]

    blocks_avoided = (
        baseline_blocks
        - optimized_blocks
    )

    block_reduction_percent = (
        blocks_avoided
        / baseline_blocks
        * 100
        if baseline_blocks
        else 0.0
    )

    utilization_improvement = (
        optimized_metrics[
            "average_block_utilization_percent"
        ]
        - baseline_metrics[
            "average_block_utilization_percent"
        ]
    )

    train_impact_change = (
        optimized_metrics[
            "estimated_total_train_impact_minutes"
        ]
        - baseline_metrics[
            "estimated_total_train_impact_minutes"
        ]
    )

    return {
        "disclaimer": (
            SYNTHETIC_DATA_DISCLAIMER
        ),
        "baseline": baseline_metrics,
        "optimized": optimized_metrics,
        "improvement": {
            "blocks_avoided": (
                blocks_avoided
            ),
            "block_reduction_percent": round(
                block_reduction_percent,
                2,
            ),
            "utilization_improvement_percentage_points": round(
                utilization_improvement,
                2,
            ),
            "train_impact_change_minutes": (
                train_impact_change
            ),
            "additional_tasks_in_bundled_blocks": (
                optimized_metrics[
                    "tasks_in_bundled_blocks"
                ]
            ),
        },
    }


def save_outputs(
    schedules: list[dict[str, Any]],
    unscheduled: list[dict[str, Any]],
    baseline_metrics: dict[str, Any],
    comparison: dict[str, Any],
) -> None:
    output_files = {
        "baseline_schedule.json": schedules,
        "baseline_unscheduled_tasks.json": (
            unscheduled
        ),
        "baseline_metrics.json": (
            baseline_metrics
        ),
        "planning_comparison.json": (
            comparison
        ),
    }

    for filename, data in (
        output_files.items()
    ):
        path = BASE_DATA_PATH / filename

        with path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                indent=2,
            )


def print_comparison(
    comparison: dict[str, Any],
) -> None:
    baseline = comparison["baseline"]
    optimized = comparison["optimized"]
    improvement = comparison["improvement"]

    print(SYNTHETIC_DATA_DISCLAIMER)

    print(
        f"Baseline scheduled tasks: "
        f"{baseline['scheduled_tasks']}/"
        f"{baseline['total_tasks']}"
    )

    print(
        f"Optimized scheduled tasks: "
        f"{optimized['scheduled_tasks']}/"
        f"{optimized['total_tasks']}"
    )

    print(
        f"Baseline blocks used: "
        f"{baseline['blocks_used']}"
    )

    print(
        f"Optimized blocks used: "
        f"{optimized['blocks_used']}"
    )

    print(
        f"Blocks avoided: "
        f"{improvement['blocks_avoided']}"
    )

    print(
        "Block reduction: "
        f"{improvement['block_reduction_percent']}%"
    )

    print(
        "Baseline average utilization: "
        f"{baseline['average_block_utilization_percent']}%"
    )

    print(
        "Optimized average utilization: "
        f"{optimized['average_block_utilization_percent']}%"
    )

    print(
        "Utilization improvement: "
        f"{improvement['utilization_improvement_percentage_points']} "
        "percentage points"
    )

    print(
        "Tasks coordinated in bundled blocks: "
        f"{optimized['tasks_in_bundled_blocks']}"
    )

    print(
        "Synthetic train-impact change: "
        f"{improvement['train_impact_change_minutes']} "
        "minutes"
    )


if __name__ == "__main__":
    (
        maintenance_tasks,
        block_windows,
        candidates,
    ) = load_inputs()

    (
        baseline_schedule,
        baseline_unscheduled,
    ) = generate_baseline(
        maintenance_tasks,
        block_windows,
        candidates,
    )

    baseline_metrics = (
        calculate_baseline_metrics(
            maintenance_tasks,
            baseline_schedule,
            baseline_unscheduled,
        )
    )

    optimized_metrics = load_json(
        "optimization_metrics.json"
    )

    comparison = build_comparison(
        baseline_metrics,
        optimized_metrics,
    )

    save_outputs(
        baseline_schedule,
        baseline_unscheduled,
        baseline_metrics,
        comparison,
    )

    print_comparison(comparison)