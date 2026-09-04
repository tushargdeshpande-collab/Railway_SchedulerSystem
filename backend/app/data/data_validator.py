"""
Validates all generated synthetic railway datasets before they are
used by the priority and optimization engines.
"""

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.data.master_data import (
    CORRIDORS,
    SECTIONS,
    SYNTHETIC_DATA_DISCLAIMER,
    validate_master_data,
)
from backend.app.schemas.domain import (
    BlockWindow,
    Department,
    GoodsTrainForecast,
    MaintenanceTask,
    SourceSystem,
    TrainMovement,
)


BASE_DATA_PATH = Path("synthetic_data/generated/base")

EXPECTED_TASKS = 200
EXPECTED_TRAIN_MOVEMENTS = 1800
EXPECTED_GOODS_FORECASTS = 1800
EXPECTED_PLANNING_DAYS = 30


def load_json(filename: str) -> list[dict[str, Any]]:
    path = BASE_DATA_PATH / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Required dataset not found: {path}"
        )

    with path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def duplicate_values(values: list[str]) -> list[str]:
    counts = Counter(values)

    return [
        value
        for value, count in counts.items()
        if count > 1
    ]


def validate_records(
    records: list[dict[str, Any]],
    model_class: type,
    dataset_name: str,
    errors: list[str],
) -> list[Any]:
    validated_records = []

    for row_number, record in enumerate(records, start=1):
        try:
            validated_records.append(
                model_class.model_validate(record)
            )
        except ValidationError as error:
            errors.append(
                f"{dataset_name} row {row_number}: {error}"
            )

    return validated_records


def run_validation() -> dict[str, Any]:
    validate_master_data()

    errors: list[str] = []
    warnings: list[str] = []
    passed_checks: list[str] = []

    task_records = load_json("maintenance_tasks.json")
    movement_records = load_json("train_timetable.json")
    forecast_records = load_json("goods_forecasts.json")
    block_records = load_json("block_windows.json")

    tasks = validate_records(
        task_records,
        MaintenanceTask,
        "maintenance_tasks",
        errors,
    )

    movements = validate_records(
        movement_records,
        TrainMovement,
        "train_timetable",
        errors,
    )

    forecasts = validate_records(
        forecast_records,
        GoodsTrainForecast,
        "goods_forecasts",
        errors,
    )

    blocks = validate_records(
        block_records,
        BlockWindow,
        "block_windows",
        errors,
    )

    if len(tasks) == EXPECTED_TASKS:
        passed_checks.append(
            f"Maintenance task volume: {len(tasks)}"
        )
    else:
        errors.append(
            f"Expected {EXPECTED_TASKS} maintenance tasks, "
            f"found {len(tasks)}"
        )

    if len(movements) == EXPECTED_TRAIN_MOVEMENTS:
        passed_checks.append(
            f"Train movement volume: {len(movements)}"
        )
    else:
        errors.append(
            f"Expected {EXPECTED_TRAIN_MOVEMENTS} train movements, "
            f"found {len(movements)}"
        )

    if len(forecasts) == EXPECTED_GOODS_FORECASTS:
        passed_checks.append(
            f"Goods forecast volume: {len(forecasts)}"
        )
    else:
        errors.append(
            f"Expected {EXPECTED_GOODS_FORECASTS} goods forecasts, "
            f"found {len(forecasts)}"
        )

    if blocks:
        passed_checks.append(
            f"Block window volume: {len(blocks)}"
        )
    else:
        errors.append("No block windows were generated")

    identifier_checks = [
        (
            "task_id",
            [task.task_id for task in tasks],
        ),
        (
            "movement_id",
            [
                movement.movement_id
                for movement in movements
            ],
        ),
        (
            "forecast_id",
            [
                forecast.forecast_id
                for forecast in forecasts
            ],
        ),
        (
            "block_id",
            [block.block_id for block in blocks],
        ),
    ]

    for identifier_name, values in identifier_checks:
        duplicates = duplicate_values(values)

        if duplicates:
            errors.append(
                f"Duplicate {identifier_name} values: "
                f"{duplicates[:10]}"
            )
        else:
            passed_checks.append(
                f"{identifier_name} values are unique"
            )

    corridor_ids = {
        corridor["corridor_id"]
        for corridor in CORRIDORS
    }

    section_lookup = {
        section["section_id"]: section["corridor_id"]
        for section in SECTIONS
    }

    all_domain_records = (
        list(tasks)
        + list(movements)
        + list(forecasts)
        + list(blocks)
    )

    for record in all_domain_records:
        if record.corridor_id not in corridor_ids:
            errors.append(
                f"Unknown corridor {record.corridor_id}"
            )

        expected_corridor = section_lookup.get(
            record.section_id
        )

        if expected_corridor is None:
            errors.append(
                f"Unknown section {record.section_id}"
            )
        elif expected_corridor != record.corridor_id:
            errors.append(
                f"Section {record.section_id} belongs to "
                f"{expected_corridor}, not {record.corridor_id}"
            )

    if not any(
        "Unknown corridor" in error
        or "Unknown section" in error
        or "belongs to" in error
        for error in errors
    ):
        passed_checks.append(
            "All corridor and section references are valid"
        )

    expected_source_by_department = {
        Department.ENGINEERING: SourceSystem.TMS,
        Department.SIGNAL_TELECOM: SourceSystem.SMMS,
        Department.TRACTION_DISTRIBUTION: SourceSystem.TDMS,
    }

    for task in tasks:
        expected_source = expected_source_by_department[
            task.department
        ]

        if task.source_system != expected_source:
            errors.append(
                f"{task.task_id}: {task.department.value} "
                f"must originate from {expected_source.value}"
            )

    if not any(
        "must originate" in error
        for error in errors
    ):
        passed_checks.append(
            "Department and source-system mappings are valid"
        )

    task_lookup = {
        task.task_id: task
        for task in tasks
    }

    for task in tasks:
        for dependency_id in task.dependency_task_ids:
            if dependency_id not in task_lookup:
                errors.append(
                    f"{task.task_id} has unknown dependency "
                    f"{dependency_id}"
                )

        for compatible_id in task.compatible_task_ids:
            compatible_task = task_lookup.get(
                compatible_id
            )

            if compatible_task is None:
                errors.append(
                    f"{task.task_id} has unknown compatible task "
                    f"{compatible_id}"
                )
                continue

            if compatible_task.department == task.department:
                errors.append(
                    f"{task.task_id} compatibility link "
                    f"{compatible_id} is from the same department"
                )

            if compatible_task.section_id != task.section_id:
                errors.append(
                    f"{task.task_id} compatibility link "
                    f"{compatible_id} is in another section"
                )

    relationship_errors = [
        error
        for error in errors
        if "dependency" in error
        or "compatible task" in error
        or "compatibility link" in error
    ]

    if not relationship_errors:
        passed_checks.append(
            "Task dependency and compatibility references are valid"
        )

    timetable_dates = {
        movement.operating_date
        for movement in movements
    }

    forecast_dates = {
        forecast.forecast_date
        for forecast in forecasts
    }

    if len(timetable_dates) == EXPECTED_PLANNING_DAYS:
        passed_checks.append(
            "Train timetable covers 30 planning days"
        )
    else:
        errors.append(
            f"Train timetable covers "
            f"{len(timetable_dates)} days"
        )

    if len(forecast_dates) == EXPECTED_PLANNING_DAYS:
        passed_checks.append(
            "Goods forecast covers 30 planning days"
        )
    else:
        errors.append(
            f"Goods forecast covers "
            f"{len(forecast_dates)} days"
        )

    movements_by_section_date = defaultdict(list)

    for movement in movements:
        key = (
            movement.section_id,
            movement.operating_date,
        )
        movements_by_section_date[key].append(movement)

    train_block_conflicts = []

    for block in blocks:
        key = (
            block.section_id,
            block.start_time.date(),
        )

        for movement in movements_by_section_date[key]:
            overlaps = (
                movement.scheduled_entry < block.end_time
                and movement.scheduled_exit > block.start_time
            )

            if overlaps:
                train_block_conflicts.append(
                    {
                        "block_id": block.block_id,
                        "movement_id": movement.movement_id,
                    }
                )

    if train_block_conflicts:
        errors.append(
            f"Found {len(train_block_conflicts)} "
            "train/block time conflicts"
        )
    else:
        passed_checks.append(
            "No train movement overlaps a generated block window"
        )

    overdue_tasks = [
        task
        for task in tasks
        if task.overdue_days > 0
    ]

    compatible_tasks = [
        task
        for task in tasks
        if task.compatible_task_ids
    ]

    if len(overdue_tasks) / len(tasks) > 0.80:
        warnings.append(
            "More than 80% of tasks are overdue; "
            "the synthetic dataset may be excessively stressed"
        )

    if not compatible_tasks:
        warnings.append(
            "No cross-department task-bundling opportunities found"
        )

    report = {
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
        "status": "PASS" if not errors else "FAIL",
        "summary": {
            "maintenance_tasks": len(tasks),
            "train_movements": len(movements),
            "goods_forecasts": len(forecasts),
            "block_windows": len(blocks),
            "planning_days": len(timetable_dates),
            "overdue_tasks": len(overdue_tasks),
            "tasks_with_bundling_opportunities": (
                len(compatible_tasks)
            ),
        },
        "passed_check_count": len(passed_checks),
        "passed_checks": passed_checks,
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
        "train_block_conflict_samples": (
            train_block_conflicts[:10]
        ),
    }

    report_path = (
        BASE_DATA_PATH / "data_quality_report.json"
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as report_file:
        json.dump(report, report_file, indent=2)

    return report


def print_report(report: dict[str, Any]) -> None:
    print(SYNTHETIC_DATA_DISCLAIMER)
    print(f"Validation status: {report['status']}")
    print(
        f"Passed checks: "
        f"{report['passed_check_count']}"
    )
    print(f"Warnings: {report['warning_count']}")
    print(f"Errors: {report['error_count']}")

    for warning in report["warnings"]:
        print(f"WARNING: {warning}")

    for error in report["errors"][:10]:
        print(f"ERROR: {error}")

    print(
        "Report saved to: "
        f"{BASE_DATA_PATH / 'data_quality_report.json'}"
    )


if __name__ == "__main__":
    validation_report = run_validation()
    print_report(validation_report)

    if validation_report["status"] != "PASS":
        raise SystemExit(1)