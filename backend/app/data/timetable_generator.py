"""
Generates a fictional 30-day train timetable.

All services, corridors, timings and identifiers are synthetic
demonstration data.
"""

import csv
import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    SECTIONS,
    SYNTHETIC_DATA_DISCLAIMER,
    validate_master_data,
)
from backend.app.schemas.domain import TrainMovement, TrainType


RANDOM_SEED = 84
START_DATE = date(2026, 9, 1)
PLANNING_DAYS = 30
MOVEMENTS_PER_SECTION_PER_DAY = 4


TRAIN_CONFIGURATION = {
    TrainType.EXPRESS: {
        "prefix": "EXP",
        "name": "Gati Express",
        "priority": 9,
        "maximum_delay": 5,
        "duration_range": (8, 16),
    },
    TrainType.PASSENGER: {
        "prefix": "PAS",
        "name": "Jan Pragati Passenger",
        "priority": 7,
        "maximum_delay": 10,
        "duration_range": (12, 22),
    },
    TrainType.SUBURBAN: {
        "prefix": "SUB",
        "name": "Gati Suburban",
        "priority": 6,
        "maximum_delay": 8,
        "duration_range": (10, 18),
    },
    TrainType.GOODS: {
        "prefix": "GDS",
        "name": "Gati Freight",
        "priority": 4,
        "maximum_delay": 30,
        "duration_range": (18, 30),
    },
}

TRAIN_TYPE_SEQUENCE = [
    TrainType.EXPRESS,
    TrainType.PASSENGER,
    TrainType.SUBURBAN,
    TrainType.GOODS,
]

TIME_BANDS = [
    (5 * 60, 8 * 60),
    (9 * 60, 12 * 60),
    (14 * 60, 17 * 60),
    (18 * 60, 22 * 60),
]


def minutes_to_datetime(
    operating_date: date,
    minutes_after_midnight: int,
) -> datetime:
    return datetime.combine(
        operating_date,
        time.min,
    ) + timedelta(minutes=minutes_after_midnight)


def generate_timetable(
    start_date: date = START_DATE,
    planning_days: int = PLANNING_DAYS,
    seed: int = RANDOM_SEED,
) -> list[TrainMovement]:
    validate_master_data()
    rng = random.Random(seed)

    movements: list[TrainMovement] = []
    movement_number = 1

    for day_offset in range(planning_days):
        operating_date = start_date + timedelta(days=day_offset)

        for section_index, section in enumerate(SECTIONS):
            for slot_index in range(
                MOVEMENTS_PER_SECTION_PER_DAY
            ):
                train_type = TRAIN_TYPE_SEQUENCE[
                    (section_index + slot_index + day_offset)
                    % len(TRAIN_TYPE_SEQUENCE)
                ]

                config = TRAIN_CONFIGURATION[train_type]
                band_start, band_end = TIME_BANDS[slot_index]

                entry_minutes = rng.randint(
                    band_start,
                    band_end - 35,
                )

                duration = rng.randint(
                    config["duration_range"][0],
                    config["duration_range"][1],
                )

                scheduled_entry = minutes_to_datetime(
                    operating_date,
                    entry_minutes,
                )

                scheduled_exit = scheduled_entry + timedelta(
                    minutes=duration
                )

                service_number = (
                    section_index * 10
                    + slot_index
                    + 1
                )

                train_id = (
                    f"{config['prefix']}-"
                    f"{service_number:03d}"
                )

                movement = TrainMovement(
                    movement_id=f"MOVE-{movement_number:06d}",
                    train_id=train_id,
                    train_name=(
                        f"{config['name']} "
                        f"{service_number:03d}"
                    ),
                    train_type=train_type,
                    corridor_id=section["corridor_id"],
                    section_id=section["section_id"],
                    operating_date=operating_date,
                    scheduled_entry=scheduled_entry,
                    scheduled_exit=scheduled_exit,
                    priority=config["priority"],
                    maximum_permissible_delay_minutes=(
                        config["maximum_delay"]
                    ),
                )

                movements.append(movement)
                movement_number += 1

    return movements


def serialise_movement(
    movement: TrainMovement,
) -> dict[str, Any]:
    return movement.model_dump(mode="json")


def save_timetable(
    movements: list[TrainMovement],
    output_directory: Path,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    records = [
        serialise_movement(movement)
        for movement in movements
    ]

    json_path = output_directory / "train_timetable.json"
    csv_path = output_directory / "train_timetable.csv"
    metadata_path = output_directory / "timetable_metadata.json"

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=2)

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=records[0].keys(),
        )
        writer.writeheader()
        writer.writerows(records)

    metadata = {
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
        "random_seed": RANDOM_SEED,
        "planning_start": START_DATE.isoformat(),
        "planning_days": PLANNING_DAYS,
        "record_count": len(movements),
        "corridor_count": 5,
        "section_count": 15,
    }

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(metadata, metadata_file, indent=2)


def print_summary(
    movements: list[TrainMovement],
) -> None:
    print(SYNTHETIC_DATA_DISCLAIMER)
    print(f"Train movements generated: {len(movements)}")
    print(f"Planning period: {PLANNING_DAYS} days")

    for train_type in TrainType:
        count = sum(
            movement.train_type == train_type
            for movement in movements
        )

        if count:
            print(f"{train_type.value}: {count}")

    covered_sections = {
        movement.section_id
        for movement in movements
    }

    print(f"Sections covered: {len(covered_sections)}")


if __name__ == "__main__":
    generated_movements = generate_timetable()

    output_path = Path(
        "synthetic_data/generated/base"
    )

    save_timetable(
        generated_movements,
        output_path,
    )

    print_summary(generated_movements)
    print(f"Files saved to: {output_path.resolve()}")