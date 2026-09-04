"""
Independent validator for the optimized maintenance schedule.

The validator reloads the source data and independently verifies
every important hard scheduling constraint.

All data used by this prototype is synthetic demonstration data.
"""
import os
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    SYNTHETIC_DATA_DISCLAIMER,
)
from backend.app.schemas.domain import (
    BlockWindow,
    MaintenanceTask,
    PriorityLevel,
    ScheduledBlock,
    TrainMovement,
)


BASE_DATA_PATH = Path(
    os.getenv(
        "SCHEDULE_DATA_PATH",
        "synthetic_data/generated/base",
    )
)


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


def run_schedule_validation() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    passed_checks: list[str] = []

    task_records = load_json(
        "scored_maintenance_tasks.json"
    )

    block_records = load_json(
        "block_windows.json"
    )

    movement_records = load_json(
        "train_timetable.json"
    )

    schedule_records = load_json(
        "optimized_schedule.json"
    )

    tasks = [
        MaintenanceTask.model_validate(record)
        for record in task_records
    ]

    blocks = [
        BlockWindow.model_validate(record)
        for record in block_records
    ]

    movements = [
        TrainMovement.model_validate(record)
        for record in movement_records
    ]

    schedules = [
        ScheduledBlock.model_validate(record)
        for record in schedule_records
    ]

    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    block_lookup = {
        block.block_id: block
        for block in blocks
    }

    scheduled_task_lookup: dict[
        str,
        ScheduledBlock,
    ] = {}

    used_block_ids: set[str] = set()

    duplicate_assignment_errors = 0

    for schedule in schedules:
        if schedule.block_id in used_block_ids:
            errors.append(
                f"Block {schedule.block_id} "
                "is used more than once"
            )

            duplicate_assignment_errors += 1

        used_block_ids.add(
            schedule.block_id
        )

        for task_id in schedule.task_ids:
            if task_id in scheduled_task_lookup:
                errors.append(
                    f"Task {task_id} "
                    "is scheduled more than once"
                )

                duplicate_assignment_errors += 1
            else:
                scheduled_task_lookup[
                    task_id
                ] = schedule

    if duplicate_assignment_errors == 0:
        passed_checks.append(
            "Task and block assignments are unique"
        )

    hard_constraint_errors = 0

    for schedule in schedules:
        block = block_lookup.get(
            schedule.block_id
        )

        if block is None:
            errors.append(
                f"Unknown block "
                f"{schedule.block_id}"
            )

            hard_constraint_errors += 1
            continue

        if (
            schedule.corridor_id
            != block.corridor_id
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "corridor mismatch"
            )

            hard_constraint_errors += 1

        if (
            schedule.section_id
            != block.section_id
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "section mismatch"
            )

            hard_constraint_errors += 1

        if (
            schedule.track_id
            != block.track_id
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "track mismatch"
            )

            hard_constraint_errors += 1

        if (
            schedule.scheduled_start
            < block.start_time
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "starts before block window"
            )

            hard_constraint_errors += 1

        if (
            schedule.scheduled_end
            > block.end_time
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "exceeds block window"
            )

            hard_constraint_errors += 1

        if len(schedule.task_ids) > 3:
            errors.append(
                f"{schedule.schedule_id}: "
                "contains more than three tasks"
            )

            hard_constraint_errors += 1

        selected_tasks: list[
            MaintenanceTask
        ] = []

        for task_id in schedule.task_ids:
            task = task_lookup.get(task_id)

            if task is None:
                errors.append(
                    f"{schedule.schedule_id}: "
                    f"unknown task {task_id}"
                )

                hard_constraint_errors += 1
                continue

            selected_tasks.append(task)

            if (
                task.corridor_id
                != schedule.corridor_id
            ):
                errors.append(
                    f"{task_id}: "
                    "assigned to wrong corridor"
                )

                hard_constraint_errors += 1

            if (
                task.section_id
                != schedule.section_id
            ):
                errors.append(
                    f"{task_id}: "
                    "assigned to wrong section"
                )

                hard_constraint_errors += 1

            if (
                task.minimum_block_minutes
                > block.available_duration_minutes
            ):
                errors.append(
                    f"{task_id}: block duration "
                    "is insufficient"
                )

                hard_constraint_errors += 1

            if (
                task.department
                not in block.permitted_departments
            ):
                errors.append(
                    f"{task_id}: department "
                    "is not permitted"
                )

                hard_constraint_errors += 1

            if (
                task.disconnection_type
                not in (
                    block
                    .supported_disconnection_types
                )
            ):
                errors.append(
                    f"{task_id}: required "
                    "disconnection is unavailable"
                )

                hard_constraint_errors += 1

            if (
                task.required_team
                not in block.available_teams
            ):
                errors.append(
                    f"{task_id}: required "
                    "team is unavailable"
                )

                hard_constraint_errors += 1

            missing_equipment = [
                equipment
                for equipment
                in task.required_equipment
                if equipment
                not in block.available_equipment
            ]

            if missing_equipment:
                errors.append(
                    f"{task_id}: missing equipment "
                    f"{missing_equipment}"
                )

                hard_constraint_errors += 1

        departments = [
            task.department
            for task in selected_tasks
        ]

        if (
            len(departments)
            != len(set(departments))
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "more than one task from the "
                "same department shares a block"
            )

            hard_constraint_errors += 1

        if (
            set(departments)
            != set(schedule.departments)
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "department list does not "
                "match selected tasks"
            )

            hard_constraint_errors += 1

        expected_bundled = (
            len(set(departments)) >= 2
        )

        if (
            schedule.is_bundled
            != expected_bundled
        ):
            errors.append(
                f"{schedule.schedule_id}: "
                "bundled flag is incorrect"
            )

            hard_constraint_errors += 1

        if selected_tasks:
            required_minutes = max(
                task.minimum_block_minutes
                for task in selected_tasks
            )

            actual_minutes = int(
                (
                    schedule.scheduled_end
                    - schedule.scheduled_start
                ).total_seconds()
                / 60
            )

            if actual_minutes != required_minutes:
                errors.append(
                    f"{schedule.schedule_id}: "
                    f"scheduled duration is "
                    f"{actual_minutes}, expected "
                    f"{required_minutes}"
                )

                hard_constraint_errors += 1

            expected_utilization = round(
                required_minutes
                / block.available_duration_minutes
                * 100,
                2,
            )

            utilization_difference = abs(
                schedule.utilization_percent
                - expected_utilization
            )

            if utilization_difference > 0.01:
                errors.append(
                    f"{schedule.schedule_id}: "
                    "utilization calculation "
                    "is incorrect"
                )

                hard_constraint_errors += 1

    if hard_constraint_errors == 0:
        passed_checks.append(
            "All task-to-block hard "
            "constraints are satisfied"
        )

    critical_task_errors = 0

    for task in tasks:
        if (
            task.priority_level
            == PriorityLevel.CRITICAL
            and task.task_id
            not in scheduled_task_lookup
        ):
            errors.append(
                f"Critical task {task.task_id} "
                "is unscheduled"
            )

            critical_task_errors += 1

    if critical_task_errors == 0:
        passed_checks.append(
            "All critical maintenance "
            "tasks are scheduled"
        )

    dependency_errors = 0

    for task in tasks:
        task_schedule = (
            scheduled_task_lookup.get(
                task.task_id
            )
        )

        if task_schedule is None:
            continue

        for dependency_id in (
            task.dependency_task_ids
        ):
            dependency_task = (
                task_lookup.get(
                    dependency_id
                )
            )

            dependency_schedule = (
                scheduled_task_lookup.get(
                    dependency_id
                )
            )

            if dependency_task is None:
                errors.append(
                    f"{task.task_id}: unknown "
                    f"dependency {dependency_id}"
                )

                dependency_errors += 1
                continue

            if dependency_schedule is None:
                errors.append(
                    f"{task.task_id}: dependency "
                    f"{dependency_id} is unscheduled"
                )

                dependency_errors += 1
                continue

            dependency_finish = (
                dependency_schedule.scheduled_start
                + timedelta(
                    minutes=(
                        dependency_task
                        .minimum_block_minutes
                    )
                )
            )

            if (
                task_schedule.scheduled_start
                < dependency_finish
            ):
                errors.append(
                    f"{task.task_id}: starts "
                    f"before dependency "
                    f"{dependency_id} finishes"
                )

                dependency_errors += 1

    if dependency_errors == 0:
        passed_checks.append(
            "All task dependencies "
            "are correctly sequenced"
        )

    team_assignments = defaultdict(list)

    for task_id, schedule in (
        scheduled_task_lookup.items()
    ):
        task = task_lookup[task_id]

        task_finish = (
            schedule.scheduled_start
            + timedelta(
                minutes=(
                    task.minimum_block_minutes
                )
            )
        )

        team_assignments[
            task.required_team
        ].append(
            (
                schedule.scheduled_start,
                task_finish,
                task_id,
            )
        )

    team_conflict_errors = 0

    for team, assignments in (
        team_assignments.items()
    ):
        assignments.sort(
            key=lambda item: item[0]
        )

        for index in range(
            len(assignments) - 1
        ):
            first = assignments[index]
            second = assignments[index + 1]

            if intervals_overlap(
                first[0],
                first[1],
                second[0],
                second[1],
            ):
                errors.append(
                    f"Team {team} is "
                    "double-booked for "
                    f"{first[2]} and {second[2]}"
                )

                team_conflict_errors += 1

    if team_conflict_errors == 0:
        passed_checks.append(
            "No maintenance team is double-booked"
        )

    track_schedules = defaultdict(list)

    for schedule in schedules:
        track_key = (
            schedule.section_id,
            schedule.track_id,
        )

        track_schedules[
            track_key
        ].append(schedule)

    track_conflict_errors = 0

    for track_key, track_records in (
        track_schedules.items()
    ):
        track_records.sort(
            key=lambda item: (
                item.scheduled_start
            )
        )

        for index in range(
            len(track_records) - 1
        ):
            first = track_records[index]
            second = track_records[index + 1]

            if intervals_overlap(
                first.scheduled_start,
                first.scheduled_end,
                second.scheduled_start,
                second.scheduled_end,
            ):
                errors.append(
                    f"Track {track_key} has "
                    "overlapping schedules "
                    f"{first.schedule_id} and "
                    f"{second.schedule_id}"
                )

                track_conflict_errors += 1

    if track_conflict_errors == 0:
        passed_checks.append(
            "No track has overlapping "
            "maintenance schedules"
        )

    movements_by_section_date = (
        defaultdict(list)
    )

    for movement in movements:
        movement_key = (
            movement.section_id,
            movement.operating_date,
        )

        movements_by_section_date[
            movement_key
        ].append(movement)

    train_conflicts = []

    for schedule in schedules:
        movement_key = (
            schedule.section_id,
            schedule.scheduled_start.date(),
        )

        for movement in (
            movements_by_section_date[
                movement_key
            ]
        ):
            if intervals_overlap(
                schedule.scheduled_start,
                schedule.scheduled_end,
                movement.scheduled_entry,
                movement.scheduled_exit,
            ):
                train_conflicts.append(
                    {
                        "schedule_id": (
                            schedule.schedule_id
                        ),
                        "movement_id": (
                            movement.movement_id
                        ),
                    }
                )

    if train_conflicts:
        errors.append(
            f"Found {len(train_conflicts)} "
            "maintenance/train conflicts"
        )
    else:
        passed_checks.append(
            "No optimized maintenance "
            "block overlaps a train"
        )

    report: dict[str, Any] = {
        "disclaimer": (
            SYNTHETIC_DATA_DISCLAIMER
        ),
        "status": (
            "PASS"
            if not errors
            else "FAIL"
        ),
        "scheduled_blocks": len(
            schedules
        ),
        "scheduled_tasks": len(
            scheduled_task_lookup
        ),
        "passed_check_count": len(
            passed_checks
        ),
        "passed_checks": passed_checks,
        "warning_count": len(
            warnings
        ),
        "warnings": warnings,
        "error_count": len(
            errors
        ),
        "errors": errors,
        "train_conflict_samples": (
            train_conflicts[:10]
        ),
    }

    report_path = (
        BASE_DATA_PATH
        / "schedule_validation_report.json"
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as report_file:
        json.dump(
            report,
            report_file,
            indent=2,
        )

    return report


def print_report(
    report: dict[str, Any],
) -> None:
    print(
        SYNTHETIC_DATA_DISCLAIMER
    )

    print(
        f"Schedule validation: "
        f"{report['status']}"
    )

    print(
        f"Scheduled blocks checked: "
        f"{report['scheduled_blocks']}"
    )

    print(
        f"Scheduled tasks checked: "
        f"{report['scheduled_tasks']}"
    )

    print(
        f"Passed checks: "
        f"{report['passed_check_count']}"
    )

    print(
        f"Warnings: "
        f"{report['warning_count']}"
    )

    print(
        f"Errors: "
        f"{report['error_count']}"
    )

    for error in report["errors"][:10]:
        print(f"ERROR: {error}")

    print(
        "Report saved to: "
        f"{BASE_DATA_PATH / 'schedule_validation_report.json'}"
    )


if __name__ == "__main__":
    validation_report = (
        run_schedule_validation()
    )

    print_report(
        validation_report
    )

    if (
        validation_report["status"]
        != "PASS"
    ):
        raise SystemExit(1)