"""
Generates the focused Pune-Lonavala weekly demonstration dataset.

All train timings, counts, maintenance records and chainages
are synthetic demonstration data.
"""

import json
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    DEPARTMENT_CONFIG,
)
from backend.app.data.pune_lonavala_config import (
    CORRIDOR,
    PRIORITY_FREIGHT_EVENT,
    SCENARIO_DISCLAIMER,
    SCENARIO_NAME,
    SECTIONS,
    SYNTHETIC_DAILY_SERVICE_COUNTS,
    WEEKLY_PLANNING_DAYS,
    WEEKLY_PLANNING_START,
    validate_configuration,
)
from backend.app.schemas.domain import (
    Department,
    DisconnectionType,
    MaintenanceTask,
    SourceSystem,
    TrainMovement,
    TrainType,
)
from backend.app.services.priority_engine import (
    score_task,
)


RANDOM_SEED = 2026
REFERENCE_DATE = WEEKLY_PLANNING_START - timedelta(days=1)

OUTPUT_PATH = Path(
    "synthetic_data/scenarios/pune_lonavala/base"
)

DEPARTMENT_VALUES = {
    "Engineering": Department.ENGINEERING,
    "Signal & Telecommunication": (
        Department.SIGNAL_TELECOM
    ),
    "Traction Distribution": (
        Department.TRACTION_DISTRIBUTION
    ),
}

SOURCE_VALUES = {
    "TMS": SourceSystem.TMS,
    "SMMS": SourceSystem.SMMS,
    "TDMS": SourceSystem.TDMS,
}

DISCONNECTION_VALUES = {
    "Engineering": (
        DisconnectionType.TRACK_POSSESSION
    ),
    "Signal & Telecommunication": (
        DisconnectionType.SIGNALLING
    ),
    "Traction Distribution": (
        DisconnectionType.POWER
    ),
}

TRAIN_CONFIG = {
    TrainType.SUBURBAN: {
        "prefix": "SUB",
        "name": "Synthetic Suburban",
        "priority": 6,
        "maximum_delay": 8,
        "section_duration": (7, 10),
    },
    TrainType.EXPRESS: {
        "prefix": "EXP",
        "name": "Synthetic Express",
        "priority": 9,
        "maximum_delay": 5,
        "section_duration": (5, 8),
    },
    TrainType.PASSENGER: {
        "prefix": "PAS",
        "name": "Synthetic Passenger",
        "priority": 7,
        "maximum_delay": 10,
        "section_duration": (8, 12),
    },
    TrainType.GOODS: {
        "prefix": "GDS",
        "name": "Synthetic Goods",
        "priority": 4,
        "maximum_delay": 30,
        "section_duration": (10, 15),
    },
}


def build_daily_service_types() -> list[TrainType]:
    service_types = []

    mapping = {
        "Suburban": TrainType.SUBURBAN,
        "Express": TrainType.EXPRESS,
        "Passenger": TrainType.PASSENGER,
        "Goods": TrainType.GOODS,
    }

    for name, count in (
        SYNTHETIC_DAILY_SERVICE_COUNTS.items()
    ):
        service_types.extend(
            [mapping[name]] * count
        )

    return service_types


def generate_train_movements(
    rng: random.Random,
) -> list[dict[str, Any]]:
    movement_records = []
    movement_number = 1

    base_service_types = (
        build_daily_service_types()
    )

    for day_offset in range(
        WEEKLY_PLANNING_DAYS
    ):
        operating_date = (
            WEEKLY_PLANNING_START
            + timedelta(days=day_offset)
        )

        daily_types = list(
            base_service_types
        )

        rng.shuffle(daily_types)

        for service_index, train_type in enumerate(
            daily_types,
            start=1,
        ):
            config = TRAIN_CONFIG[
                train_type
            ]

            departure_minutes = (
                5 * 60
                + (service_index - 1) * 25
                + rng.randint(-4, 4)
            )

            departure = (
                datetime.combine(
                    operating_date,
                    time.min,
                )
                + timedelta(
                    minutes=departure_minutes
                )
            )

            direction = (
                "Pune to Lonavala"
                if service_index % 2
                else "Lonavala to Pune"
            )

            route_sections = (
                list(SECTIONS)
                if direction == "Pune to Lonavala"
                else list(reversed(SECTIONS))
            )

            current_time = departure

            service_id = (
                f"PL-{config['prefix']}-"
                f"{service_index:03d}"
            )

            for route_sequence, section in enumerate(
                route_sections,
                start=1,
            ):
                duration = rng.randint(
                    config[
                        "section_duration"
                    ][0],
                    config[
                        "section_duration"
                    ][1],
                )

                entry_time = current_time
                exit_time = (
                    entry_time
                    + timedelta(
                        minutes=duration
                    )
                )

                movement = TrainMovement(
                    movement_id=(
                        f"PL-MOVE-"
                        f"{movement_number:06d}"
                    ),
                    train_id=service_id,
                    train_name=(
                        f"{config['name']} "
                        f"{service_index:03d}"
                    ),
                    train_type=train_type,
                    corridor_id=(
                        CORRIDOR[
                            "corridor_id"
                        ]
                    ),
                    section_id=(
                        section[
                            "section_id"
                        ]
                    ),
                    operating_date=(
                        operating_date
                    ),
                    scheduled_entry=entry_time,
                    scheduled_exit=exit_time,
                    priority=config["priority"],
                    maximum_permissible_delay_minutes=(
                        config[
                            "maximum_delay"
                        ]
                    ),
                )

                record = movement.model_dump(
                    mode="json"
                )

                record["direction"] = direction
                record["route_sequence"] = (
                    route_sequence
                )
                record["synthetic_service_id"] = (
                    service_id
                )

                movement_records.append(
                    record
                )

                movement_number += 1

                current_time = (
                    exit_time
                    + timedelta(
                        minutes=rng.randint(1, 3)
                    )
                )

    return movement_records


def calculate_overdue_days(
    due_date,
) -> int:
    return max(
        0,
        (REFERENCE_DATE - due_date).days,
    )


def generate_maintenance_tasks(
    rng: random.Random,
) -> list[MaintenanceTask]:
    tasks = []
    task_number = 1

    department_names = list(
        DEPARTMENT_CONFIG.keys()
    )

    previous_task_by_section_department = {}

    for maintenance_round in range(3):
        for section in SECTIONS:
            for department_name in department_names:
                config = DEPARTMENT_CONFIG[
                    department_name
                ]

                detection_date = (
                    REFERENCE_DATE
                    - timedelta(
                        days=rng.randint(2, 50)
                    )
                )

                due_date = (
                    detection_date
                    + timedelta(
                        days=rng.randint(7, 35)
                    )
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
                                + rng.uniform(
                                    -0.08,
                                    0.12,
                                )
                            ),
                        ),
                    ),
                    3,
                )

                duration = rng.choice(
                    [45, 60, 75, 90, 120]
                )

                minimum_block = (
                    duration
                    + rng.choice([15, 30])
                )

                asset_index = rng.randrange(
                    len(config["assets"])
                )

                dependency_key = (
                    section["section_id"],
                    department_name,
                )

                dependencies = []

                if (
                    maintenance_round > 0
                    and rng.random() < 0.25
                    and dependency_key
                    in previous_task_by_section_department
                ):
                    dependencies = [
                        previous_task_by_section_department[
                            dependency_key
                        ]
                    ]

                section_length = (
                    section["end_km"]
                    - section["start_km"]
                )

                margin = min(
                    0.2,
                    section_length / 10,
                )

                task = MaintenanceTask(
                    task_id=(
                        f"PL-TASK-"
                        f"{task_number:04d}"
                    ),
                    source_system=(
                        SOURCE_VALUES[
                            config[
                                "source_system"
                            ]
                        ]
                    ),
                    department=(
                        DEPARTMENT_VALUES[
                            department_name
                        ]
                    ),
                    asset_id=(
                        f"PL-ASSET-"
                        f"{section['section_id']}-"
                        f"{task_number:04d}"
                    ),
                    asset_type=(
                        config["assets"][
                            asset_index
                        ]
                    ),
                    corridor_id=(
                        CORRIDOR[
                            "corridor_id"
                        ]
                    ),
                    section_id=(
                        section[
                            "section_id"
                        ]
                    ),
                    start_km=round(
                        section["start_km"]
                        + margin,
                        2,
                    ),
                    end_km=round(
                        section["end_km"]
                        - margin,
                        2,
                    ),
                    defect_type=(
                        config["defects"][
                            asset_index
                        ]
                    ),
                    defect_severity=severity,
                    safety_criticality=safety,
                    failure_probability=(
                        failure_probability
                    ),
                    asset_importance=(
                        rng.randint(2, 5)
                    ),
                    operational_impact=(
                        rng.randint(2, 5)
                    ),
                    detection_date=(
                        detection_date
                    ),
                    due_date=due_date,
                    overdue_days=(
                        calculate_overdue_days(
                            due_date
                        )
                    ),
                    estimated_duration_minutes=(
                        duration
                    ),
                    minimum_block_minutes=(
                        minimum_block
                    ),
                    disconnection_type=(
                        DISCONNECTION_VALUES[
                            department_name
                        ]
                    ),
                    required_team=(
                        rng.choice(
                            config["teams"]
                        )
                    ),
                    required_personnel=(
                        rng.randint(3, 8)
                    ),
                    required_equipment=(
                        rng.sample(
                            config["equipment"],
                            k=rng.randint(1, 2),
                        )
                    ),
                    dependency_task_ids=(
                        dependencies
                    ),
                    compatible_task_ids=[],
                    weather_sensitive=(
                        rng.random() < 0.20
                    ),
                )

                tasks.append(task)

                previous_task_by_section_department[
                    dependency_key
                ] = task.task_id

                task_number += 1

    for task in tasks:
        compatible = [
            other.task_id
            for other in tasks
            if (
                other.task_id
                != task.task_id
                and other.section_id
                == task.section_id
                and other.department
                != task.department
            )
        ]

        task.compatible_task_ids = (
            compatible[:3]
        )

    return [
        MaintenanceTask.model_validate(
            task.model_dump()
        )
        for task in tasks
    ]


def save_json(
    filename: str,
    data: Any,
) -> None:
    OUTPUT_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = OUTPUT_PATH / filename

    with path.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            data,
            output_file,
            indent=2,
            default=str,
        )


def print_summary(
    train_movements: list[dict[str, Any]],
    scored_tasks: list[dict[str, Any]],
) -> None:
    print(SCENARIO_DISCLAIMER)
    print(f"Scenario: {SCENARIO_NAME}")
    print(
        f"Weekly section movements: "
        f"{len(train_movements)}"
    )
    print(
        f"Maintenance tasks: "
        f"{len(scored_tasks)}"
    )

    for department in Department:
        count = sum(
            record["department"]
            == department.value
            for record in scored_tasks
        )

        print(
            f"{department.value}: {count}"
        )

    critical_count = sum(
        record["priority_level"]
        == "Critical"
        for record in scored_tasks
    )

    high_count = sum(
        record["priority_level"]
        == "High"
        for record in scored_tasks
    )

    print(
        f"Critical tasks: {critical_count}"
    )
    print(
        f"High-priority tasks: {high_count}"
    )
    print(
        "Priority freight event: "
        f"{PRIORITY_FREIGHT_EVENT['event_type']}"
    )
    print(
        f"Files saved to: "
        f"{OUTPUT_PATH.resolve()}"
    )


if __name__ == "__main__":
    validate_configuration()

    random_generator = random.Random(
        RANDOM_SEED
    )

    generated_movements = (
        generate_train_movements(
            random_generator
        )
    )

    maintenance_tasks = (
        generate_maintenance_tasks(
            random_generator
        )
    )

    scored_tasks = [
        score_task(task)
        for task in maintenance_tasks
    ]

    freight_event_record = {
        key: (
            value.isoformat()
            if isinstance(value, datetime)
            else (
                value.isoformat()
                if hasattr(value, "isoformat")
                else value
            )
        )
        for key, value
        in PRIORITY_FREIGHT_EVENT.items()
    }

    metadata = {
        "scenario": SCENARIO_NAME,
        "disclaimer": (
            SCENARIO_DISCLAIMER
        ),
        "random_seed": RANDOM_SEED,
        "planning_start": (
            WEEKLY_PLANNING_START.isoformat()
        ),
        "planning_days": (
            WEEKLY_PLANNING_DAYS
        ),
        "daily_services": 36,
        "section_count": len(SECTIONS),
        "train_section_movements": len(
            generated_movements
        ),
        "maintenance_task_count": len(
            scored_tasks
        ),
    }

    save_json(
        "train_timetable.json",
        generated_movements,
    )

    save_json(
        "scored_maintenance_tasks.json",
        scored_tasks,
    )

    save_json(
        "priority_freight_event.json",
        freight_event_record,
    )

    save_json(
        "scenario_metadata.json",
        metadata,
    )

    print_summary(
        generated_movements,
        scored_tasks,
    )