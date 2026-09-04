"""
Resource-aware Pune-Lonavala dynamic replanner.

The replanner:

1. Identifies tasks directly affected by the unexpected priority
   freight movement.
2. Expands the replanning scope to include resource-linked and
   dependency-linked future tasks when necessary.
3. Preserves unrelated and locked schedules.
4. Prevents scheduling work before the disruption notification.
5. Removes alternatives that conflict with the freight movement.
6. Re-optimizes the affected scope using OR-Tools CP-SAT.
7. Produces a revised plan and before-versus-after change report.

All operational data is synthetic demonstration data.
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from backend.app.data.pune_lonavala_config import (
    SCENARIO_DISCLAIMER,
)
from backend.app.optimization.scheduler import (
    build_outputs,
    solve_schedule,
)
from backend.app.schemas.domain import (
    BlockWindow,
    MaintenanceTask,
)


SCENARIO_PATH = Path(
    "synthetic_data/scenarios/pune_lonavala/base"
)


def load_json(filename: str) -> Any:
    path = SCENARIO_PATH / filename

    with path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        return json.load(input_file)


def save_json(
    filename: str,
    data: Any,
) -> None:
    path = SCENARIO_PATH / filename

    with path.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            data,
            output_file,
            indent=2,
        )


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return (
        first_start < second_end
        and second_start < first_end
    )


def task_finish_time(
    schedule: dict[str, Any],
    task: MaintenanceTask,
) -> datetime:
    schedule_start = datetime.fromisoformat(
        schedule["scheduled_start"]
    )

    return (
        schedule_start
        + timedelta(
            minutes=(
                task.minimum_block_minutes
            )
        )
    )


def build_schedule_by_task(
    schedules: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        task_id: schedule
        for schedule in schedules
        for task_id in schedule["task_ids"]
    }


def expand_replanning_scope(
    direct_affected_task_ids: set[str],
    tasks: list[MaintenanceTask],
    task_lookup: dict[
        str,
        MaintenanceTask,
    ],
    original_schedule: list[
        dict[str, Any]
    ],
    replanning_cutoff: datetime,
) -> set[str]:
    affected_task_ids = set(
        direct_affected_task_ids
    )

    schedule_by_task = (
        build_schedule_by_task(
            original_schedule
        )
    )

    scope_changed = True

    while scope_changed:
        previous_count = len(
            affected_task_ids
        )

        # If one task in a bundled schedule moves,
        # all tasks sharing that block must be
        # reconsidered.
        for schedule in original_schedule:
            schedule_task_ids = set(
                schedule["task_ids"]
            )

            if (
                schedule_task_ids
                & affected_task_ids
            ):
                affected_task_ids.update(
                    schedule_task_ids
                )

        # If an unaffected future task depends on
        # a task being moved, include that downstream
        # task in the replanning scope.
        for task in tasks:
            if (
                task.task_id
                not in schedule_by_task
            ):
                continue

            dependency_overlap = (
                set(
                    task.dependency_task_ids
                )
                & affected_task_ids
            )

            if not dependency_overlap:
                continue

            task_schedule = (
                schedule_by_task[
                    task.task_id
                ]
            )

            task_start = (
                datetime.fromisoformat(
                    task_schedule[
                        "scheduled_start"
                    ]
                )
            )

            if (
                task_start
                >= replanning_cutoff
            ):
                affected_task_ids.add(
                    task.task_id
                )

        # Identify the teams required by all
        # directly or indirectly affected tasks.
        affected_teams = {
            task_lookup[
                task_id
            ].required_team
            for task_id in affected_task_ids
        }

        # Future bookings using one of the affected
        # teams are reopened because they may block
        # every alternative for a directly affected
        # maintenance task.
        for schedule in original_schedule:
            schedule_start = (
                datetime.fromisoformat(
                    schedule[
                        "scheduled_start"
                    ]
                )
            )

            if (
                schedule_start
                < replanning_cutoff
            ):
                continue

            schedule_uses_affected_team = any(
                task_lookup[
                    task_id
                ].required_team
                in affected_teams
                for task_id
                in schedule["task_ids"]
            )

            if schedule_uses_affected_team:
                affected_task_ids.update(
                    schedule["task_ids"]
                )

        scope_changed = (
            len(affected_task_ids)
            > previous_count
        )

    return affected_task_ids


def block_conflicts_with_freight(
    block: BlockWindow,
    task: MaintenanceTask,
    freight_movements: list[
        dict[str, Any]
    ],
) -> bool:
    proposed_start = block.start_time

    proposed_end = (
        proposed_start
        + timedelta(
            minutes=(
                task.minimum_block_minutes
            )
        )
    )

    for movement in freight_movements:
        if (
            block.section_id
            != movement["section_id"]
        ):
            continue

        if (
            block.track_id
            != movement["track_id"]
        ):
            continue

        freight_start = datetime.fromisoformat(
            movement["scheduled_entry"]
        )

        freight_end = datetime.fromisoformat(
            movement["scheduled_exit"]
        )

        if intervals_overlap(
            proposed_start,
            proposed_end,
            freight_start,
            freight_end,
        ):
            return True

    return False


def build_unaffected_team_bookings(
    unaffected_schedules: list[
        dict[str, Any]
    ],
    task_lookup: dict[
        str,
        MaintenanceTask,
    ],
) -> dict[str, list[tuple]]:
    bookings = defaultdict(list)

    for schedule in unaffected_schedules:
        schedule_start = (
            datetime.fromisoformat(
                schedule[
                    "scheduled_start"
                ]
            )
        )

        for task_id in schedule["task_ids"]:
            task = task_lookup[task_id]

            task_end = (
                schedule_start
                + timedelta(
                    minutes=(
                        task.minimum_block_minutes
                    )
                )
            )

            bookings[
                task.required_team
            ].append(
                (
                    schedule_start,
                    task_end,
                    task_id,
                )
            )

    return bookings


def team_is_available(
    task: MaintenanceTask,
    block: BlockWindow,
    team_bookings: dict[
        str,
        list[tuple],
    ],
) -> bool:
    proposed_start = block.start_time

    proposed_end = (
        proposed_start
        + timedelta(
            minutes=(
                task.minimum_block_minutes
            )
        )
    )

    for (
        existing_start,
        existing_end,
        _existing_task_id,
    ) in team_bookings[
        task.required_team
    ]:
        if intervals_overlap(
            proposed_start,
            proposed_end,
            existing_start,
            existing_end,
        ):
            return False

    return True


def dependency_boundaries_satisfied(
    task: MaintenanceTask,
    block: BlockWindow,
    task_lookup: dict[
        str,
        MaintenanceTask,
    ],
    original_task_schedules: dict[
        str,
        dict[str, Any],
    ],
    affected_task_ids: set[str],
) -> bool:
    proposed_start = block.start_time

    proposed_finish = (
        proposed_start
        + timedelta(
            minutes=(
                task.minimum_block_minutes
            )
        )
    )

    # An unaffected prerequisite must finish
    # before the moved task starts.
    for dependency_id in (
        task.dependency_task_ids
    ):
        if (
            dependency_id
            in affected_task_ids
        ):
            continue

        dependency_schedule = (
            original_task_schedules.get(
                dependency_id
            )
        )

        dependency_task = (
            task_lookup.get(
                dependency_id
            )
        )

        if (
            dependency_schedule is None
            or dependency_task is None
        ):
            return False

        dependency_finish = (
            task_finish_time(
                dependency_schedule,
                dependency_task,
            )
        )

        if (
            proposed_start
            < dependency_finish
        ):
            return False

    # If an unaffected downstream task depends
    # on this task, the moved task must still
    # finish before the downstream task starts.
    for other_task_id, other_task in (
        task_lookup.items()
    ):
        if (
            task.task_id
            not in (
                other_task
                .dependency_task_ids
            )
        ):
            continue

        if (
            other_task_id
            in affected_task_ids
        ):
            continue

        downstream_schedule = (
            original_task_schedules.get(
                other_task_id
            )
        )

        if downstream_schedule is None:
            continue

        downstream_start = (
            datetime.fromisoformat(
                downstream_schedule[
                    "scheduled_start"
                ]
            )
        )

        if (
            proposed_finish
            > downstream_start
        ):
            return False

    return True


def detect_freight_conflicts(
    schedules: list[dict[str, Any]],
    freight_movements: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    conflicts = []

    for schedule in schedules:
        schedule_start = (
            datetime.fromisoformat(
                schedule[
                    "scheduled_start"
                ]
            )
        )

        schedule_end = (
            datetime.fromisoformat(
                schedule[
                    "scheduled_end"
                ]
            )
        )

        for movement in freight_movements:
            if (
                schedule["section_id"]
                != movement["section_id"]
            ):
                continue

            if (
                schedule["track_id"]
                != movement["track_id"]
            ):
                continue

            freight_start = (
                datetime.fromisoformat(
                    movement[
                        "scheduled_entry"
                    ]
                )
            )

            freight_end = (
                datetime.fromisoformat(
                    movement[
                        "scheduled_exit"
                    ]
                )
            )

            if intervals_overlap(
                schedule_start,
                schedule_end,
                freight_start,
                freight_end,
            ):
                conflicts.append(
                    {
                        "schedule_id": (
                            schedule[
                                "schedule_id"
                            ]
                        ),
                        "block_id": (
                            schedule[
                                "block_id"
                            ]
                        ),
                        "task_ids": (
                            schedule[
                                "task_ids"
                            ]
                        ),
                        "freight_movement_id": (
                            movement[
                                "movement_id"
                            ]
                        ),
                    }
                )

    return conflicts


def run_replanning() -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, list[str]],
]:
    task_records = load_json(
        "scored_maintenance_tasks.json"
    )

    block_records = load_json(
        "block_windows.json"
    )

    candidate_report = load_json(
        "candidate_report.json"
    )

    original_schedule = load_json(
        "optimized_schedule.json"
    )

    disruption_analysis = load_json(
        "disruption_analysis.json"
    )

    freight_movements = load_json(
        "priority_freight_movements.json"
    )

    tasks = [
        MaintenanceTask.model_validate(
            record
        )
        for record in task_records
    ]

    blocks = [
        BlockWindow.model_validate(
            record
        )
        for record in block_records
    ]

    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    block_lookup = {
        block.block_id: block
        for block in blocks
    }

    original_candidate_map: dict[
        str,
        list[str],
    ] = candidate_report[
        "candidate_map"
    ]

    original_task_schedules = (
        build_schedule_by_task(
            original_schedule
        )
    )

    direct_affected_task_ids = set(
        disruption_analysis[
            "affected_task_ids"
        ]
    )

    event_start = min(
        datetime.fromisoformat(
            movement[
                "scheduled_entry"
            ]
        )
        for movement
        in freight_movements
    )

    # The Control Office communicates the
    # unexpected movement six hours before
    # the corridor entry time.
    replanning_cutoff = (
        event_start
        - timedelta(hours=6)
    )

    affected_task_ids = (
        expand_replanning_scope(
            direct_affected_task_ids,
            tasks,
            task_lookup,
            original_schedule,
            replanning_cutoff,
        )
    )

    locked_affected_schedules = [
        schedule
        for schedule in original_schedule
        if (
            schedule.get(
                "is_locked",
                False,
            )
            and any(
                task_id
                in affected_task_ids
                for task_id
                in schedule["task_ids"]
            )
        )
    ]

    if locked_affected_schedules:
        locked_ids = [
            schedule["schedule_id"]
            for schedule
            in locked_affected_schedules
        ]

        raise SystemExit(
            "Locked schedules require manual "
            f"planner intervention: {locked_ids}"
        )

    affected_tasks = [
        task_lookup[task_id]
        for task_id
        in sorted(affected_task_ids)
    ]

    unaffected_schedules = [
        schedule
        for schedule in original_schedule
        if not any(
            task_id
            in affected_task_ids
            for task_id
            in schedule["task_ids"]
        )
    ]

    used_unaffected_blocks = {
        schedule["block_id"]
        for schedule
        in unaffected_schedules
    }

    team_bookings = (
        build_unaffected_team_bookings(
            unaffected_schedules,
            task_lookup,
        )
    )

    revised_candidate_map: dict[
        str,
        list[str],
    ] = {}

    rejection_counts = {
        "before_notification": 0,
        "used_by_unaffected": 0,
        "freight_conflict": 0,
        "team_unavailable": 0,
        "dependency_violation": 0,
    }

    for task in affected_tasks:
        allowed_blocks = []

        for block_id in (
            original_candidate_map.get(
                task.task_id,
                [],
            )
        ):
            block = block_lookup[
                block_id
            ]

            # Never move a task into the past.
            if (
                block.start_time
                < replanning_cutoff
            ):
                rejection_counts[
                    "before_notification"
                ] += 1
                continue

            if (
                block_id
                in used_unaffected_blocks
            ):
                rejection_counts[
                    "used_by_unaffected"
                ] += 1
                continue

            if block_conflicts_with_freight(
                block,
                task,
                freight_movements,
            ):
                rejection_counts[
                    "freight_conflict"
                ] += 1
                continue

            if not team_is_available(
                task,
                block,
                team_bookings,
            ):
                rejection_counts[
                    "team_unavailable"
                ] += 1
                continue

            if not (
                dependency_boundaries_satisfied(
                    task,
                    block,
                    task_lookup,
                    original_task_schedules,
                    affected_task_ids,
                )
            ):
                rejection_counts[
                    "dependency_violation"
                ] += 1
                continue

            allowed_blocks.append(
                block_id
            )

        revised_candidate_map[
            task.task_id
        ] = allowed_blocks

    tasks_without_alternatives = [
        task_id
        for task_id, block_ids
        in revised_candidate_map.items()
        if not block_ids
    ]

    if tasks_without_alternatives:
        diagnostic = {
            "tasks_without_alternatives": (
                tasks_without_alternatives
            ),
            "rejection_counts": (
                rejection_counts
            ),
            "direct_affected_tasks": (
                sorted(
                    direct_affected_task_ids
                )
            ),
            "expanded_replanning_scope": (
                sorted(
                    affected_task_ids
                )
            ),
        }

        save_json(
            "replanning_failure_diagnostic.json",
            diagnostic,
        )

        raise SystemExit(
            "Affected tasks without alternative "
            f"blocks: "
            f"{tasks_without_alternatives}"
        )

    started_at = time.perf_counter()

    (
        solver,
        status,
        assignment_variables,
    ) = solve_schedule(
        affected_tasks,
        blocks,
        revised_candidate_map,
    )

    runtime = (
        time.perf_counter()
        - started_at
    )

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        raise SystemExit(
            "Dynamic replanning failed. "
            f"Status: "
            f"{solver.status_name(status)}"
        )

    (
        moved_schedules,
        moved_unscheduled_tasks,
        subset_metrics,
    ) = build_outputs(
        solver,
        status,
        affected_tasks,
        blocks,
        revised_candidate_map,
        assignment_variables,
        runtime,
    )

    for index, schedule in enumerate(
        moved_schedules,
        start=1,
    ):
        schedule["schedule_id"] = (
            f"REPLAN-{index:05d}"
        )

        schedule["explanation"] = (
            "This maintenance block was "
            "reconsidered after the unexpected "
            "priority perishable-goods movement. "
            + schedule["explanation"]
        )

    revised_schedule = (
        unaffected_schedules
        + moved_schedules
    )

    revised_schedule.sort(
        key=lambda schedule: (
            schedule[
                "scheduled_start"
            ]
        )
    )

    remaining_conflicts = (
        detect_freight_conflicts(
            revised_schedule,
            freight_movements,
        )
    )

    changes = []

    for task_id in sorted(
        affected_task_ids
    ):
        original = (
            original_task_schedules.get(
                task_id
            )
        )

        revised = next(
            (
                schedule
                for schedule
                in moved_schedules
                if task_id
                in schedule["task_ids"]
            ),
            None,
        )

        changes.append(
            {
                "task_id": task_id,
                "direct_freight_conflict": (
                    task_id
                    in direct_affected_task_ids
                ),
                "original_schedule_id": (
                    original[
                        "schedule_id"
                    ]
                    if original
                    else None
                ),
                "original_block_id": (
                    original["block_id"]
                    if original
                    else None
                ),
                "original_start": (
                    original[
                        "scheduled_start"
                    ]
                    if original
                    else None
                ),
                "revised_schedule_id": (
                    revised[
                        "schedule_id"
                    ]
                    if revised
                    else None
                ),
                "revised_block_id": (
                    revised["block_id"]
                    if revised
                    else None
                ),
                "revised_start": (
                    revised[
                        "scheduled_start"
                    ]
                    if revised
                    else None
                ),
                "status": (
                    "Moved"
                    if revised
                    else "Unscheduled"
                ),
            }
        )

    metrics = {
        "disclaimer": (
            SCENARIO_DISCLAIMER
        ),
        "event_type": (
            "Priority Perishable "
            "Goods Movement"
        ),
        "event_corridor_entry": (
            event_start.isoformat()
        ),
        "replanning_notification_time": (
            replanning_cutoff.isoformat()
        ),
        "original_schedule_count": len(
            original_schedule
        ),
        "directly_conflicting_tasks": len(
            direct_affected_task_ids
        ),
        "resource_or_dependency_cascade_tasks": (
            len(
                affected_task_ids
                - direct_affected_task_ids
            )
        ),
        "total_replanning_scope_tasks": (
            len(affected_task_ids)
        ),
        "unaffected_schedules_preserved": (
            len(
                unaffected_schedules
            )
        ),
        "affected_tasks_rescheduled": sum(
            change["status"] == "Moved"
            for change in changes
        ),
        "affected_tasks_unscheduled": sum(
            change["status"]
            == "Unscheduled"
            for change in changes
        ),
        "new_schedule_count": len(
            revised_schedule
        ),
        "replanning_solver_status": (
            solver.status_name(status)
        ),
        "replanning_runtime_seconds": round(
            runtime,
            3,
        ),
        "remaining_priority_freight_conflicts": (
            len(
                remaining_conflicts
            )
        ),
        "unchanged_schedule_percentage": round(
            len(unaffected_schedules)
            / len(original_schedule)
            * 100,
            2,
        ),
        "candidate_rejection_counts": (
            rejection_counts
        ),
        "subset_optimizer_metrics": (
            subset_metrics
        ),
    }

    return (
        revised_schedule,
        metrics,
        changes,
        revised_candidate_map,
    )


def print_summary(
    metrics: dict[str, Any],
    changes: list[dict[str, Any]],
) -> None:
    print(SCENARIO_DISCLAIMER)

    print(
        f"Replanning status: "
        f"{metrics['replanning_solver_status']}"
    )

    print(
        f"Replanning runtime: "
        f"{metrics['replanning_runtime_seconds']} "
        "seconds"
    )

    print(
        "Directly conflicting tasks: "
        f"{metrics['directly_conflicting_tasks']}"
    )

    print(
        "Resource/dependency cascade tasks: "
        f"{metrics['resource_or_dependency_cascade_tasks']}"
    )

    print(
        "Total replanning scope: "
        f"{metrics['total_replanning_scope_tasks']}"
    )

    print(
        "Unaffected schedules preserved: "
        f"{metrics['unaffected_schedules_preserved']}/"
        f"{metrics['original_schedule_count']}"
    )

    print(
        "Replanned tasks scheduled: "
        f"{metrics['affected_tasks_rescheduled']}"
    )

    print(
        "Replanned tasks unscheduled: "
        f"{metrics['affected_tasks_unscheduled']}"
    )

    print(
        "Unchanged schedule percentage: "
        f"{metrics['unchanged_schedule_percentage']}%"
    )

    print(
        "Remaining priority freight conflicts: "
        f"{metrics['remaining_priority_freight_conflicts']}"
    )

    print("Replanning changes:")

    for change in changes:
        conflict_type = (
            "DIRECT"
            if change[
                "direct_freight_conflict"
            ]
            else "CASCADE"
        )

        print(
            f"  {change['task_id']} "
            f"[{conflict_type}]: "
            f"{change['original_start']} -> "
            f"{change['revised_start']} "
            f"({change['status']})"
        )


if __name__ == "__main__":
    (
        revised_plan,
        replanning_metrics,
        replanning_changes,
        revised_candidates,
    ) = run_replanning()

    save_json(
        "revised_schedule.json",
        revised_plan,
    )

    save_json(
        "replanning_metrics.json",
        replanning_metrics,
    )

    save_json(
        "replanning_changes.json",
        replanning_changes,
    )

    save_json(
        "replanning_candidate_map.json",
        revised_candidates,
    )

    print_summary(
        replanning_metrics,
        replanning_changes,
    )

    if (
        replanning_metrics[
            "remaining_priority_freight_conflicts"
        ]
        > 0
    ):
        raise SystemExit(
            "Revised plan still conflicts "
            "with priority freight"
        )