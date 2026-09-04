from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DATA_PATH = Path(
    "synthetic_data/scenarios/pune_lonavala/base"
)

REPORT_PATH = DATA_PATH / "replan_validation_report.json"


def load_json(filename: str) -> Any:
    path = DATA_PATH / filename

    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    """
    Half-open interval comparison.

    Example:
    01:00-02:00 and 02:00-03:00 do not overlap.
    """
    return first_start < second_end and second_start < first_end


def direction_to_track(direction: str | None) -> str | None:
    if not direction:
        return None

    normalized = direction.strip().lower()

    if normalized in {
        "pune to lonavala",
        "pune-lonavala",
        "up",
        "pl-up",
    }:
        return "PL-UP"

    if normalized in {
        "lonavala to pune",
        "lonavala-pune",
        "down",
        "pl-down",
    }:
        return "PL-DOWN"

    return None


def task_schedule_map(
    schedules: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for schedule in schedules:
        for task_id in schedule.get("task_ids", []):
            result[task_id] = schedule

    return result


def schedule_signature(
    schedule: dict[str, Any],
) -> tuple[str, str, str, str, str]:
    return (
        str(schedule.get("block_id")),
        str(schedule.get("section_id")),
        str(schedule.get("track_id")),
        str(schedule.get("scheduled_start")),
        str(schedule.get("scheduled_end")),
    )


def add_pass(
    passed_checks: list[str],
    message: str,
) -> None:
    passed_checks.append(message)


def add_warning(
    warnings: list[str],
    message: str,
) -> None:
    warnings.append(message)


def add_error(
    errors: list[str],
    message: str,
) -> None:
    errors.append(message)


def validate_replanned_schedule() -> dict[str, Any]:
    tasks = load_json("scored_maintenance_tasks.json")
    blocks = load_json("block_windows.json")
    timetable = load_json("train_timetable.json")
    freight_movements = load_json(
        "priority_freight_movements.json"
    )
    original_schedule = load_json("optimized_schedule.json")
    revised_schedule = load_json("revised_schedule.json")
    replanning_changes = load_json("replanning_changes.json")
    replanning_metrics = load_json("replanning_metrics.json")

    task_by_id = {
        task["task_id"]: task
        for task in tasks
    }

    block_by_id = {
        block["block_id"]: block
        for block in blocks
    }

    original_task_map = task_schedule_map(original_schedule)
    revised_task_map = task_schedule_map(revised_schedule)

    changed_task_ids = {
        change["task_id"]
        for change in replanning_changes
    }

    passed_checks: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    validation_statistics: dict[str, Any] = {}

    # ---------------------------------------------------------
    # 1. Basic schedule record validation
    # ---------------------------------------------------------

    duplicate_schedule_ids = [
        schedule_id
        for schedule_id, count in Counter(
            schedule["schedule_id"]
            for schedule in revised_schedule
        ).items()
        if count > 1
    ]

    if duplicate_schedule_ids:
        add_error(
            errors,
            "Duplicate revised schedule IDs: "
            + ", ".join(duplicate_schedule_ids),
        )
    else:
        add_pass(
            passed_checks,
            "All revised schedule IDs are unique.",
        )

    all_revised_task_ids: list[str] = []

    for schedule in revised_schedule:
        all_revised_task_ids.extend(
            schedule.get("task_ids", [])
        )

    duplicate_task_ids = [
        task_id
        for task_id, count in Counter(
            all_revised_task_ids
        ).items()
        if count > 1
    ]

    if duplicate_task_ids:
        add_error(
            errors,
            "Tasks assigned more than once: "
            + ", ".join(duplicate_task_ids),
        )
    else:
        add_pass(
            passed_checks,
            "No maintenance task is assigned more than once.",
        )

    unknown_task_ids = sorted(
        set(all_revised_task_ids) - set(task_by_id)
    )

    if unknown_task_ids:
        add_error(
            errors,
            "Unknown task IDs in revised schedule: "
            + ", ".join(unknown_task_ids),
        )
    else:
        add_pass(
            passed_checks,
            "Every scheduled task exists in the maintenance dataset.",
        )

    unknown_block_ids = sorted(
        {
            schedule["block_id"]
            for schedule in revised_schedule
            if schedule["block_id"] not in block_by_id
        }
    )

    if unknown_block_ids:
        add_error(
            errors,
            "Unknown block IDs in revised schedule: "
            + ", ".join(unknown_block_ids),
        )
    else:
        add_pass(
            passed_checks,
            "Every revised schedule uses a valid COA block window.",
        )

    # ---------------------------------------------------------
    # 2. Schedule-to-block and task feasibility
    # ---------------------------------------------------------

    feasibility_error_count_before = len(errors)

    for schedule in revised_schedule:
        schedule_id = schedule["schedule_id"]
        block_id = schedule["block_id"]

        if block_id not in block_by_id:
            continue

        block = block_by_id[block_id]

        schedule_start = parse_datetime(
            schedule["scheduled_start"]
        )
        schedule_end = parse_datetime(
            schedule["scheduled_end"]
        )
        block_start = parse_datetime(block["start_time"])
        block_end = parse_datetime(block["end_time"])

        if schedule_end <= schedule_start:
            add_error(
                errors,
                f"{schedule_id}: scheduled end must be after start.",
            )

        if (
            schedule_start < block_start
            or schedule_end > block_end
        ):
            add_error(
                errors,
                f"{schedule_id}: schedule interval is outside "
                f"block {block_id}.",
            )

        if schedule.get("corridor_id") != block.get(
            "corridor_id"
        ):
            add_error(
                errors,
                f"{schedule_id}: corridor does not match "
                f"block {block_id}.",
            )

        if schedule.get("section_id") != block.get(
            "section_id"
        ):
            add_error(
                errors,
                f"{schedule_id}: section does not match "
                f"block {block_id}.",
            )

        if schedule.get("track_id") != block.get("track_id"):
            add_error(
                errors,
                f"{schedule_id}: track does not match "
                f"block {block_id}.",
            )

        schedule_duration = int(
            (schedule_end - schedule_start).total_seconds()
            / 60
        )

        permitted_departments = set(
            block.get("permitted_departments", [])
        )
        available_teams = set(
            block.get("available_teams", [])
        )
        available_equipment = set(
            block.get("available_equipment", [])
        )
        supported_disconnections = set(
            block.get("supported_disconnection_types", [])
        )

        for task_id in schedule.get("task_ids", []):
            task = task_by_id.get(task_id)

            if task is None:
                continue

            if task.get("corridor_id") != schedule.get(
                "corridor_id"
            ):
                add_error(
                    errors,
                    f"{task_id}: task corridor does not match "
                    f"{schedule_id}.",
                )

            if task.get("section_id") != schedule.get(
                "section_id"
            ):
                add_error(
                    errors,
                    f"{task_id}: task section does not match "
                    f"{schedule_id}.",
                )

            minimum_minutes = int(
                task.get("minimum_block_minutes", 0)
            )

            if schedule_duration < minimum_minutes:
                add_error(
                    errors,
                    f"{task_id}: requires {minimum_minutes} minutes "
                    f"but {schedule_id} provides only "
                    f"{schedule_duration} minutes.",
                )

            department = task.get("department")

            if (
                permitted_departments
                and department not in permitted_departments
            ):
                add_error(
                    errors,
                    f"{task_id}: department {department} is not "
                    f"permitted in block {block_id}.",
                )

            required_team = task.get("required_team")

            if (
                available_teams
                and required_team
                and required_team not in available_teams
            ):
                add_error(
                    errors,
                    f"{task_id}: team {required_team} is unavailable "
                    f"in block {block_id}.",
                )

            required_equipment = set(
                task.get("required_equipment", [])
            )

            missing_equipment = sorted(
                required_equipment - available_equipment
            )

            if missing_equipment:
                add_error(
                    errors,
                    f"{task_id}: equipment unavailable in "
                    f"{block_id}: {', '.join(missing_equipment)}.",
                )

            disconnection_type = task.get(
                "disconnection_type"
            )

            no_disconnection_values = {
                None,
                "",
                "None",
                "No Disconnection",
                "Not Required",
            }

            if disconnection_type not in no_disconnection_values:
                if not block.get(
                    "disconnection_available",
                    False,
                ):
                    add_error(
                        errors,
                        f"{task_id}: requires "
                        f"{disconnection_type}, but block "
                        f"{block_id} has no disconnection.",
                    )

                if (
                    supported_disconnections
                    and disconnection_type
                    not in supported_disconnections
                ):
                    add_error(
                        errors,
                        f"{task_id}: disconnection type "
                        f"{disconnection_type} is unsupported "
                        f"in block {block_id}.",
                    )

    if len(errors) == feasibility_error_count_before:
        add_pass(
            passed_checks,
            "All revised task assignments satisfy block, duration, "
            "department, team, equipment and disconnection constraints.",
        )

    # ---------------------------------------------------------
    # 3. Maintenance-team overlap validation
    # ---------------------------------------------------------

    team_assignments: dict[
        str,
        list[tuple[str, str, datetime, datetime]],
    ] = defaultdict(list)

    for schedule in revised_schedule:
        schedule_start = parse_datetime(
            schedule["scheduled_start"]
        )

        for task_id in schedule.get("task_ids", []):
            task = task_by_id.get(task_id)

            if task is None:
                continue

            team = task.get("required_team")

            if not team:
                continue

            task_end = schedule_start + timedelta(
                minutes=int(
                    task.get("minimum_block_minutes", 0)
                )
            )

            team_assignments[team].append(
                (
                    task_id,
                    schedule["schedule_id"],
                    schedule_start,
                    task_end,
                )
            )

    team_errors_before = len(errors)

    for team, assignments in team_assignments.items():
        assignments.sort(key=lambda item: item[2])

        for first_index in range(len(assignments)):
            first = assignments[first_index]

            for second_index in range(
                first_index + 1,
                len(assignments),
            ):
                second = assignments[second_index]

                if second[2] >= first[3]:
                    break

                if first[1] == second[1]:
                    add_error(
                        errors,
                        f"Team {team}: tasks {first[0]} and "
                        f"{second[0]} are bundled in the same "
                        "schedule but require the same team.",
                    )
                elif intervals_overlap(
                    first[2],
                    first[3],
                    second[2],
                    second[3],
                ):
                    add_error(
                        errors,
                        f"Team {team}: overlapping assignments "
                        f"{first[0]} ({first[1]}) and "
                        f"{second[0]} ({second[1]}).",
                    )

    if len(errors) == team_errors_before:
        add_pass(
            passed_checks,
            "No maintenance team has overlapping assignments.",
        )

    # ---------------------------------------------------------
    # 4. Dependency validation
    # ---------------------------------------------------------

    dependency_errors_before = len(errors)

    for task_id, schedule in revised_task_map.items():
        task = task_by_id.get(task_id)

        if task is None:
            continue

        task_start = parse_datetime(
            schedule["scheduled_start"]
        )

        for dependency_id in task.get(
            "dependency_task_ids",
            [],
        ):
            dependency_schedule = revised_task_map.get(
                dependency_id
            )

            if dependency_schedule is None:
                add_error(
                    errors,
                    f"{task_id}: dependency {dependency_id} "
                    "is not present in the revised schedule.",
                )
                continue

            dependency_task = task_by_id.get(dependency_id)

            if dependency_task is None:
                add_error(
                    errors,
                    f"{task_id}: dependency {dependency_id} "
                    "does not exist in the maintenance dataset.",
                )
                continue

            dependency_start = parse_datetime(
                dependency_schedule["scheduled_start"]
            )
            dependency_finish = (
                dependency_start
                + timedelta(
                    minutes=int(
                        dependency_task.get(
                            "minimum_block_minutes",
                            0,
                        )
                    )
                )
            )

            if task_start < dependency_finish:
                add_error(
                    errors,
                    f"{task_id}: starts at {task_start.isoformat()} "
                    f"before dependency {dependency_id} finishes at "
                    f"{dependency_finish.isoformat()}.",
                )

    if len(errors) == dependency_errors_before:
        add_pass(
            passed_checks,
            "All scheduled task dependencies are respected.",
        )

    # ---------------------------------------------------------
    # 5. Normal train conflict validation
    # ---------------------------------------------------------

    train_conflict_errors_before = len(errors)
    normal_train_conflicts = 0

    for schedule in revised_schedule:
        schedule_start = parse_datetime(
            schedule["scheduled_start"]
        )
        schedule_end = parse_datetime(
            schedule["scheduled_end"]
        )
        schedule_track = schedule.get("track_id")
        schedule_section = schedule.get("section_id")

        for movement in timetable:
            if movement.get("section_id") != schedule_section:
                continue

            movement_track = direction_to_track(
                movement.get("direction")
            )

            if (
                movement_track is not None
                and movement_track != schedule_track
            ):
                continue

            movement_start = parse_datetime(
                movement["scheduled_entry"]
            )
            movement_end = parse_datetime(
                movement["scheduled_exit"]
            )

            if intervals_overlap(
                schedule_start,
                schedule_end,
                movement_start,
                movement_end,
            ):
                normal_train_conflicts += 1

                add_error(
                    errors,
                    f"{schedule['schedule_id']}: conflicts with "
                    f"normal train movement "
                    f"{movement['movement_id']} on "
                    f"{schedule_section}/{schedule_track}.",
                )

    if len(errors) == train_conflict_errors_before:
        add_pass(
            passed_checks,
            "The revised schedule has no normal train conflicts.",
        )

    # ---------------------------------------------------------
    # 6. Priority freight conflict validation
    # ---------------------------------------------------------

    freight_errors_before = len(errors)
    freight_conflicts = 0

    for schedule in revised_schedule:
        schedule_start = parse_datetime(
            schedule["scheduled_start"]
        )
        schedule_end = parse_datetime(
            schedule["scheduled_end"]
        )

        for movement in freight_movements:
            same_corridor = (
                schedule.get("corridor_id")
                == movement.get("corridor_id")
            )
            same_section = (
                schedule.get("section_id")
                == movement.get("section_id")
            )
            same_track = (
                schedule.get("track_id")
                == movement.get("track_id")
            )

            if not (
                same_corridor
                and same_section
                and same_track
            ):
                continue

            movement_start = parse_datetime(
                movement["scheduled_entry"]
            )
            movement_end = parse_datetime(
                movement["scheduled_exit"]
            )

            if intervals_overlap(
                schedule_start,
                schedule_end,
                movement_start,
                movement_end,
            ):
                freight_conflicts += 1

                add_error(
                    errors,
                    f"{schedule['schedule_id']}: conflicts with "
                    f"priority freight movement "
                    f"{movement['movement_id']} on "
                    f"{movement['section_id']}/"
                    f"{movement['track_id']}.",
                )

    if len(errors) == freight_errors_before:
        add_pass(
            passed_checks,
            "The revised schedule has zero priority freight conflicts.",
        )

    # ---------------------------------------------------------
    # 7. Preserve the originally scheduled task population
    # ---------------------------------------------------------

    original_task_ids = set(original_task_map)
    revised_task_ids = set(revised_task_map)

    missing_original_tasks = sorted(
        original_task_ids - revised_task_ids
    )
    unexpected_new_tasks = sorted(
        revised_task_ids - original_task_ids
    )

    if missing_original_tasks:
        add_error(
            errors,
            "Originally scheduled tasks missing after replanning: "
            + ", ".join(missing_original_tasks),
        )

    if unexpected_new_tasks:
        add_warning(
            warnings,
            "Previously unscheduled tasks added during replanning: "
            + ", ".join(unexpected_new_tasks),
        )

    if not missing_original_tasks:
        add_pass(
            passed_checks,
            "No originally scheduled maintenance task was lost "
            "during replanning.",
        )

    # ---------------------------------------------------------
    # 8. Unaffected schedule preservation
    # ---------------------------------------------------------

    unaffected_task_ids = (
        original_task_ids - changed_task_ids
    )

    changed_unaffected_tasks: list[str] = []

    for task_id in sorted(unaffected_task_ids):
        original = original_task_map.get(task_id)
        revised = revised_task_map.get(task_id)

        if original is None or revised is None:
            continue

        if schedule_signature(original) != schedule_signature(
            revised
        ):
            changed_unaffected_tasks.append(task_id)

    if changed_unaffected_tasks:
        add_error(
            errors,
            "Tasks outside the declared replanning scope changed: "
            + ", ".join(changed_unaffected_tasks),
        )
    else:
        add_pass(
            passed_checks,
            "All tasks outside the declared replanning scope "
            "were preserved.",
        )

    preserved_original_schedule_ids: list[str] = []

    revised_signatures = {
        (
            schedule["block_id"],
            schedule["section_id"],
            schedule["track_id"],
            schedule["scheduled_start"],
            schedule["scheduled_end"],
            tuple(sorted(schedule.get("task_ids", []))),
        )
        for schedule in revised_schedule
    }

    for schedule in original_schedule:
        signature = (
            schedule["block_id"],
            schedule["section_id"],
            schedule["track_id"],
            schedule["scheduled_start"],
            schedule["scheduled_end"],
            tuple(sorted(schedule.get("task_ids", []))),
        )

        if signature in revised_signatures:
            preserved_original_schedule_ids.append(
                schedule["schedule_id"]
            )

    reported_preserved_count = int(
        replanning_metrics.get(
            "unaffected_schedules_preserved",
            0,
        )
    )

    actual_preserved_count = len(
        preserved_original_schedule_ids
    )

    if actual_preserved_count != reported_preserved_count:
        add_warning(
            warnings,
            "Preserved schedule metric differs from exact full-record "
            f"comparison: reported={reported_preserved_count}, "
            f"exact={actual_preserved_count}. This can happen when "
            "a schedule keeps its timing but its task bundle changes.",
        )
    else:
        add_pass(
            passed_checks,
            "The reported preserved-schedule count matches the "
            "recomputed count.",
        )

    # ---------------------------------------------------------
    # 9. Replanning cutoff / no-time-travel validation
    # ---------------------------------------------------------

    notification_time = parse_datetime(
        replanning_metrics["replanning_notification_time"]
    )

    cutoff_errors_before = len(errors)

    for change in replanning_changes:
        task_id = change["task_id"]
        original = original_task_map.get(task_id)
        revised = revised_task_map.get(task_id)

        if original is None or revised is None:
            continue

        original_signature = schedule_signature(original)
        revised_signature = schedule_signature(revised)

        actually_changed = (
            original_signature != revised_signature
        )

        revised_start = parse_datetime(
            revised["scheduled_start"]
        )

        if actually_changed and revised_start < notification_time:
            add_error(
                errors,
                f"{task_id}: was changed to "
                f"{revised_start.isoformat()}, before the replanning "
                f"notification time {notification_time.isoformat()}.",
            )

    if len(errors) == cutoff_errors_before:
        add_pass(
            passed_checks,
            "No changed task was moved into a block before the "
            "replanning notification time.",
        )

    # ---------------------------------------------------------
    # 10. Locked schedule preservation
    # ---------------------------------------------------------

    locked_errors_before = len(errors)

    for original in original_schedule:
        if not original.get("is_locked", False):
            continue

        for task_id in original.get("task_ids", []):
            revised = revised_task_map.get(task_id)

            if revised is None:
                add_error(
                    errors,
                    f"{task_id}: locked task is missing from the "
                    "revised schedule.",
                )
                continue

            if schedule_signature(original) != schedule_signature(
                revised
            ):
                add_error(
                    errors,
                    f"{task_id}: locked assignment was changed.",
                )

    if len(errors) == locked_errors_before:
        add_pass(
            passed_checks,
            "All locked schedules were preserved.",
        )

    # ---------------------------------------------------------
    # 11. Replanning change classification analysis
    # ---------------------------------------------------------

    change_classification = Counter()

    for change in replanning_changes:
        task_id = change["task_id"]
        original = original_task_map.get(task_id)
        revised = revised_task_map.get(task_id)

        if original is None and revised is None:
            change_classification["Missing"] += 1
            continue

        if revised is None:
            change_classification["Unscheduled"] += 1
            continue

        if original is None:
            change_classification["Newly Scheduled"] += 1
            continue

        same_block = (
            original.get("block_id")
            == revised.get("block_id")
        )
        same_start = (
            original.get("scheduled_start")
            == revised.get("scheduled_start")
        )
        same_end = (
            original.get("scheduled_end")
            == revised.get("scheduled_end")
        )
        same_bundle = set(
            original.get("task_ids", [])
        ) == set(
            revised.get("task_ids", [])
        )

        if (
            same_block
            and same_start
            and same_end
            and same_bundle
        ):
            classification = "Unchanged"
        elif not same_start or not same_end:
            classification = "Rescheduled"
        elif not same_block:
            classification = "Reassigned"
        elif not same_bundle:
            classification = "Rebundled"
        else:
            classification = "Modified"

        change_classification[classification] += 1

    # ---------------------------------------------------------
    # Final statistics and report
    # ---------------------------------------------------------

    validation_statistics.update(
        {
            "maintenance_tasks_available": len(tasks),
            "original_schedule_blocks": len(
                original_schedule
            ),
            "revised_schedule_blocks": len(
                revised_schedule
            ),
            "original_scheduled_tasks": len(
                original_task_ids
            ),
            "revised_scheduled_tasks": len(
                revised_task_ids
            ),
            "declared_replanning_scope_tasks": len(
                changed_task_ids
            ),
            "unaffected_tasks_checked": len(
                unaffected_task_ids
            ),
            "exact_original_schedules_preserved": (
                actual_preserved_count
            ),
            "normal_train_conflicts": (
                normal_train_conflicts
            ),
            "priority_freight_conflicts": (
                freight_conflicts
            ),
            "change_classification": dict(
                change_classification
            ),
        }
    )

    validation_status = (
        "PASS"
        if not errors
        else "FAIL"
    )

    report = {
        "disclaimer": (
            "Synthetic Demonstration Data - Station names are "
            "used only to demonstrate the planning workflow. "
            "Train timings, counts, chainages, maintenance tasks "
            "and forecasts are not official Indian Railways "
            "operational data."
        ),
        "validation_status": validation_status,
        "passed_check_count": len(passed_checks),
        "warning_count": len(warnings),
        "error_count": len(errors),
        "passed_checks": passed_checks,
        "warnings": warnings,
        "errors": errors,
        "statistics": validation_statistics,
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return report


def main() -> None:
    report = validate_replanned_schedule()

    print(report["disclaimer"])
    print(
        "Replanned schedule validation:",
        report["validation_status"],
    )
    print(
        "Passed checks:",
        report["passed_check_count"],
    )
    print(
        "Warnings:",
        report["warning_count"],
    )
    print(
        "Errors:",
        report["error_count"],
    )

    statistics = report["statistics"]

    print(
        "Original scheduled tasks:",
        statistics["original_scheduled_tasks"],
    )
    print(
        "Revised scheduled tasks:",
        statistics["revised_scheduled_tasks"],
    )
    print(
        "Revised schedule blocks:",
        statistics["revised_schedule_blocks"],
    )
    print(
        "Normal train conflicts:",
        statistics["normal_train_conflicts"],
    )
    print(
        "Priority freight conflicts:",
        statistics["priority_freight_conflicts"],
    )
    print(
        "Change classification:",
        statistics["change_classification"],
    )

    for warning in report["warnings"]:
        print("WARNING:", warning)

    for error in report["errors"]:
        print("ERROR:", error)

    print("Report saved to:", REPORT_PATH)


if __name__ == "__main__":
    main()