"""
Generates reproducible synthetic maintenance tasks representing
fictional TMS, SMMS and TDMS feeds.

This data is for demonstration only and is not official
Indian Railways operational data.
"""

import csv
import json
import random
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    DEPARTMENT_CONFIG,
    SECTIONS,
    SYNTHETIC_DATA_DISCLAIMER,
    validate_master_data,
)
from backend.app.schemas.domain import (
    Department,
    DisconnectionType,
    MaintenanceTask,
    SourceSystem,
)


RANDOM_SEED = 42
REFERENCE_DATE = date(2026, 8, 28)
DEFAULT_TASK_COUNT = 200

DEPARTMENT_ENUMS = {
    "Engineering": Department.ENGINEERING,
    "Signal & Telecommunication": Department.SIGNAL_TELECOM,
    "Traction Distribution": Department.TRACTION_DISTRIBUTION,
}

SOURCE_ENUMS = {
    "TMS": SourceSystem.TMS,
    "SMMS": SourceSystem.SMMS,
    "TDMS": SourceSystem.TDMS,
}

DISCONNECTION_BY_DEPARTMENT = {
    "Engineering": [
        DisconnectionType.TRACK_POSSESSION,
        DisconnectionType.TRACK_POSSESSION,
        DisconnectionType.POWER_AND_TRACK,
    ],
    "Signal & Telecommunication": [
        DisconnectionType.SIGNALLING,
        DisconnectionType.SIGNALLING,
        DisconnectionType.TRACK_POSSESSION,
    ],
    "Traction Distribution": [
        DisconnectionType.POWER,
        DisconnectionType.POWER,
        DisconnectionType.POWER_AND_TRACK,
    ],
}

DURATION_OPTIONS = {
    "Engineering": [60, 90, 120, 150, 180],
    "Signal & Telecommunication": [30, 45, 60, 90, 120],
    "Traction Distribution": [45, 60, 90, 120, 150],
}

PERSONNEL_OPTIONS = {
    "Engineering": [4, 6, 8, 10],
    "Signal & Telecommunication": [2, 3, 4, 5],
    "Traction Distribution": [3, 4, 6, 8],
}

PREFERRED_WINDOWS = [
    (time(0, 0), time(4, 0)),
    (time(1, 0), time(5, 0)),
    (time(10, 30), time(13, 30)),
    (time(14, 0), time(17, 0)),
    (time(22, 0), time(23, 59)),
]


def calculate_overdue_days(due_date: date) -> int:
    return max(0, (REFERENCE_DATE - due_date).days)


def choose_equipment(
    rng: random.Random,
    equipment_list: list[str],
) -> list[str]:
    equipment_count = rng.randint(1, min(2, len(equipment_list)))
    return rng.sample(equipment_list, equipment_count)


def generate_maintenance_tasks(
    count: int = DEFAULT_TASK_COUNT,
    seed: int = RANDOM_SEED,
) -> list[MaintenanceTask]:
    validate_master_data()
    rng = random.Random(seed)

    tasks: list[MaintenanceTask] = []
    department_names = list(DEPARTMENT_CONFIG.keys())

    for index in range(1, count + 1):
        department_name = department_names[(index - 1) % 3]
        config = DEPARTMENT_CONFIG[department_name]
        section = rng.choice(SECTIONS)

        section_start = float(section["start_km"])
        section_end = float(section["end_km"])
        section_length = section_end - section_start

        task_start_km = round(
            rng.uniform(
                section_start,
                section_end - min(0.5, section_length / 2),
            ),
            2,
        )

        maximum_task_length = min(
            3.0,
            section_end - task_start_km,
        )

        task_end_km = round(
            task_start_km + rng.uniform(0.2, maximum_task_length),
            2,
        )

        detection_date = REFERENCE_DATE - timedelta(
            days=rng.randint(1, 90)
        )

        allowed_completion_days = rng.randint(3, 60)
        due_date = detection_date + timedelta(
            days=allowed_completion_days
        )

        severity = rng.randint(1, 5)
        safety = rng.randint(1, 5)

        if severity == 5:
            safety = max(safety, 4)

        failure_probability = round(
            min(
                0.98,
                max(
                    0.02,
                    (
                        severity * 0.10
                        + safety * 0.08
                        + rng.uniform(-0.10, 0.15)
                    ),
                ),
            ),
            3,
        )

        estimated_duration = rng.choice(
            DURATION_OPTIONS[department_name]
        )

        preparation_buffer = rng.choice([15, 30, 45])
        minimum_block = estimated_duration + preparation_buffer

        preferred_start, preferred_end = rng.choice(
            PREFERRED_WINDOWS
        )

        asset_index = rng.randrange(len(config["assets"]))
        asset_type = config["assets"][asset_index]
        defect_type = config["defects"][asset_index]

        required_equipment = choose_equipment(
            rng,
            config["equipment"],
        )

        task = MaintenanceTask(
            task_id=f"TASK-{index:04d}",
            source_system=SOURCE_ENUMS[config["source_system"]],
            department=DEPARTMENT_ENUMS[department_name],
            asset_id=f"ASSET-{section['section_id']}-{index:04d}",
            asset_type=asset_type,
            corridor_id=section["corridor_id"],
            section_id=section["section_id"],
            start_km=task_start_km,
            end_km=task_end_km,
            defect_type=defect_type,
            defect_severity=severity,
            safety_criticality=safety,
            failure_probability=failure_probability,
            asset_importance=rng.randint(1, 5),
            operational_impact=rng.randint(1, 5),
            detection_date=detection_date,
            due_date=due_date,
            overdue_days=calculate_overdue_days(due_date),
            estimated_duration_minutes=estimated_duration,
            minimum_block_minutes=minimum_block,
            disconnection_type=rng.choice(
                DISCONNECTION_BY_DEPARTMENT[department_name]
            ),
            required_team=rng.choice(config["teams"]),
            required_personnel=rng.choice(
                PERSONNEL_OPTIONS[department_name]
            ),
            required_equipment=required_equipment,
            preferred_start_time=preferred_start,
            preferred_end_time=preferred_end,
            dependency_task_ids=[],
            compatible_task_ids=[],
            weather_sensitive=(
                rng.random() < 0.30
                if department_name != "Signal & Telecommunication"
                else rng.random() < 0.10
            ),
        )

        tasks.append(task)

    add_compatibility_links(tasks)
    add_dependency_links(tasks, rng)

    return [
        MaintenanceTask.model_validate(task.model_dump())
        for task in tasks
    ]


def sections_overlap(
    first: MaintenanceTask,
    second: MaintenanceTask,
) -> bool:
    return (
        first.start_km < second.end_km
        and second.start_km < first.end_km
    )


def add_compatibility_links(
    tasks: list[MaintenanceTask],
) -> None:
    for task in tasks:
        candidates = [
            other.task_id
            for other in tasks
            if other.task_id != task.task_id
            and other.section_id == task.section_id
            and other.department != task.department
            and sections_overlap(task, other)
        ]

        task.compatible_task_ids = candidates[:3]


def add_dependency_links(
    tasks: list[MaintenanceTask],
    rng: random.Random,
) -> None:
    for index, task in enumerate(tasks):
        if index == 0 or rng.random() >= 0.08:
            continue

        candidates = [
            previous.task_id
            for previous in tasks[:index]
            if previous.section_id == task.section_id
            and previous.department == task.department
        ]

        if candidates:
            task.dependency_task_ids = [rng.choice(candidates)]


def serialise_task(task: MaintenanceTask) -> dict[str, Any]:
    return task.model_dump(mode="json")


def save_tasks(
    tasks: list[MaintenanceTask],
    output_directory: Path,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    records = [serialise_task(task) for task in tasks]

    json_path = output_directory / "maintenance_tasks.json"
    csv_path = output_directory / "maintenance_tasks.csv"

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=2)

    csv_records = []

    for record in records:
        csv_record = record.copy()

        for field in [
            "required_equipment",
            "dependency_task_ids",
            "compatible_task_ids",
        ]:
            csv_record[field] = "|".join(csv_record[field])

        csv_records.append(csv_record)

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=csv_records[0].keys(),
        )
        writer.writeheader()
        writer.writerows(csv_records)

    metadata = {
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
        "random_seed": RANDOM_SEED,
        "reference_date": REFERENCE_DATE.isoformat(),
        "record_count": len(tasks),
        "source_systems": ["TMS", "SMMS", "TDMS"],
    }

    metadata_path = output_directory / "metadata.json"

    with metadata_path.open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=2)


def print_summary(tasks: list[MaintenanceTask]) -> None:
    print(SYNTHETIC_DATA_DISCLAIMER)
    print(f"Maintenance tasks generated: {len(tasks)}")

    for department in Department:
        count = sum(
            task.department == department
            for task in tasks
        )
        print(f"{department.value}: {count}")

    overdue_count = sum(
        task.overdue_days > 0
        for task in tasks
    )

    critical_defects = sum(
        task.safety_criticality == 5
        or task.defect_severity == 5
        for task in tasks
    )

    tasks_with_compatible_work = sum(
        bool(task.compatible_task_ids)
        for task in tasks
    )

    print(f"Overdue tasks: {overdue_count}")
    print(f"High-severity or safety-critical tasks: {critical_defects}")
    print(
        "Tasks with cross-department compatibility: "
        f"{tasks_with_compatible_work}"
    )


if __name__ == "__main__":
    generated_tasks = generate_maintenance_tasks()

    output_path = Path(
        "synthetic_data/generated/base"
    )

    save_tasks(generated_tasks, output_path)
    print_summary(generated_tasks)

    print(f"Files saved to: {output_path.resolve()}")