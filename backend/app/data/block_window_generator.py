"""
Generates synthetic maintenance block windows after considering
scheduled train movements and forecast goods traffic.

All records are fictional demonstration data.
"""

import csv
import json
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    CORRIDORS,
    DEPARTMENT_CONFIG,
    SECTIONS,
    SYNTHETIC_DATA_DISCLAIMER,
)
from backend.app.schemas.domain import (
    BlockStatus,
    BlockWindow,
    Department,
    DisconnectionType,
    GoodsTrainForecast,
    TrafficLevel,
    TrainMovement,
)


RANDOM_SEED = 168
MINIMUM_WINDOW_MINUTES = 45
SAFETY_BUFFER_MINUTES = 10

BASE_DATA_PATH = Path("synthetic_data/generated/base")

CANDIDATE_WINDOWS = [
    (time(0, 0), time(5, 0)),
    (time(10, 0), time(14, 0)),
    (time(21, 30), time(23, 59)),
]

ALL_DEPARTMENTS = [
    Department.ENGINEERING,
    Department.SIGNAL_TELECOM,
    Department.TRACTION_DISTRIBUTION,
]

ALL_DISCONNECTION_TYPES = [
    DisconnectionType.NONE,
    DisconnectionType.POWER,
    DisconnectionType.SIGNALLING,
    DisconnectionType.TRACK_POSSESSION,
    DisconnectionType.POWER_AND_TRACK,
]


def load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def load_train_movements() -> list[TrainMovement]:
    records = load_json(
        BASE_DATA_PATH / "train_timetable.json"
    )

    return [
        TrainMovement.model_validate(record)
        for record in records
    ]


def load_goods_forecasts() -> list[GoodsTrainForecast]:
    records = load_json(
        BASE_DATA_PATH / "goods_forecasts.json"
    )

    return [
        GoodsTrainForecast.model_validate(record)
        for record in records
    ]


def get_track_ids(corridor_id: str) -> list[str]:
    corridor = next(
        item
        for item in CORRIDORS
        if item["corridor_id"] == corridor_id
    )
    return corridor["tracks"]


def get_all_teams() -> list[str]:
    return [
        team
        for config in DEPARTMENT_CONFIG.values()
        for team in config["teams"]
    ]


def get_all_equipment() -> list[str]:
    return [
        equipment
        for config in DEPARTMENT_CONFIG.values()
        for equipment in config["equipment"]
    ]


def subtract_busy_intervals(
    candidate_start: datetime,
    candidate_end: datetime,
    movements: list[TrainMovement],
) -> list[tuple[datetime, datetime]]:
    busy_intervals = []

    for movement in movements:
        busy_start = movement.scheduled_entry - timedelta(
            minutes=SAFETY_BUFFER_MINUTES
        )
        busy_end = movement.scheduled_exit + timedelta(
            minutes=SAFETY_BUFFER_MINUTES
        )

        if (
            busy_start < candidate_end
            and busy_end > candidate_start
        ):
            busy_intervals.append(
                (
                    max(busy_start, candidate_start),
                    min(busy_end, candidate_end),
                )
            )

    busy_intervals.sort(key=lambda item: item[0])

    free_intervals = []
    cursor = candidate_start

    for busy_start, busy_end in busy_intervals:
        if busy_start > cursor:
            free_intervals.append((cursor, busy_start))

        cursor = max(cursor, busy_end)

    if cursor < candidate_end:
        free_intervals.append((cursor, candidate_end))

    return [
        (free_start, free_end)
        for free_start, free_end in free_intervals
        if int(
            (free_end - free_start).total_seconds() / 60
        ) >= MINIMUM_WINDOW_MINUTES
    ]


def find_matching_forecast(
    forecasts: list[GoodsTrainForecast],
    section_id: str,
    window_start: datetime,
) -> GoodsTrainForecast | None:
    for forecast in forecasts:
        if (
            forecast.section_id == section_id
            and forecast.window_start
            <= window_start
            < forecast.window_end
        ):
            return forecast

    return None


def calculate_traffic_level(
    forecast: GoodsTrainForecast | None,
    scheduled_movement_count: int,
) -> TrafficLevel:
    forecast_count = (
        forecast.expected_train_count
        if forecast
        else 0
    )

    combined_load = (
        forecast_count + scheduled_movement_count
    )

    if combined_load <= 2:
        return TrafficLevel.LOW
    if combined_load <= 4:
        return TrafficLevel.MEDIUM
    if combined_load <= 6:
        return TrafficLevel.HIGH

    return TrafficLevel.PEAK


def generate_block_windows(
    movements: list[TrainMovement],
    forecasts: list[GoodsTrainForecast],
    seed: int = RANDOM_SEED,
) -> list[BlockWindow]:
    rng = random.Random(seed)

    planning_dates = sorted(
        {
            movement.operating_date
            for movement in movements
        }
    )

    all_teams = get_all_teams()
    all_equipment = get_all_equipment()

    block_windows: list[BlockWindow] = []
    block_number = 1

    for planning_date in planning_dates:
        for section in SECTIONS:
            section_movements = [
                movement
                for movement in movements
                if movement.section_id
                == section["section_id"]
                and movement.operating_date
                == planning_date
            ]

            for candidate_start_time, candidate_end_time in (
                CANDIDATE_WINDOWS
            ):
                candidate_start = datetime.combine(
                    planning_date,
                    candidate_start_time,
                )
                candidate_end = datetime.combine(
                    planning_date,
                    candidate_end_time,
                )

                free_intervals = subtract_busy_intervals(
                    candidate_start,
                    candidate_end,
                    section_movements,
                )

                for free_start, free_end in free_intervals:
                    movement_count = sum(
                        movement.scheduled_entry < free_end
                        and movement.scheduled_exit > free_start
                        for movement in section_movements
                    )

                    matching_forecast = find_matching_forecast(
                        forecasts,
                        section["section_id"],
                        free_start,
                    )

                    traffic_level = calculate_traffic_level(
                        matching_forecast,
                        movement_count,
                    )

                    duration_minutes = int(
                        (
                            free_end - free_start
                        ).total_seconds()
                        / 60
                    )

                    for track_id in get_track_ids(
                        section["corridor_id"]
                    ):
                        disconnection_available = (
                            rng.random() < 0.88
                        )

                        supported_types = (
                            ALL_DISCONNECTION_TYPES
                            if disconnection_available
                            else [DisconnectionType.NONE]
                        )

                        block = BlockWindow(
                            block_id=(
                                f"BLOCK-{block_number:06d}"
                            ),
                            corridor_id=section["corridor_id"],
                            section_id=section["section_id"],
                            track_id=track_id,
                            start_time=free_start,
                            end_time=free_end,
                            available_duration_minutes=(
                                duration_minutes
                            ),
                            traffic_level=traffic_level,
                            permitted_departments=(
                                ALL_DEPARTMENTS
                            ),
                            disconnection_available=(
                                disconnection_available
                            ),
                            supported_disconnection_types=(
                                supported_types
                            ),
                            available_teams=all_teams,
                            available_equipment=all_equipment,
                            status=BlockStatus.AVAILABLE,
                        )

                        block_windows.append(block)
                        block_number += 1

    return block_windows


def serialise_block(
    block: BlockWindow,
) -> dict[str, Any]:
    return block.model_dump(mode="json")


def save_block_windows(
    block_windows: list[BlockWindow],
    output_directory: Path,
) -> None:
    records = [
        serialise_block(block)
        for block in block_windows
    ]

    json_path = output_directory / "block_windows.json"
    csv_path = output_directory / "block_windows.csv"
    metadata_path = (
        output_directory / "block_window_metadata.json"
    )

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=2)

    csv_records = []

    for record in records:
        csv_record = record.copy()

        for field in [
            "permitted_departments",
            "supported_disconnection_types",
            "available_teams",
            "available_equipment",
        ]:
            csv_record[field] = "|".join(
                csv_record[field]
            )

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
        "minimum_window_minutes": (
            MINIMUM_WINDOW_MINUTES
        ),
        "safety_buffer_minutes": SAFETY_BUFFER_MINUTES,
        "record_count": len(block_windows),
    }

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(metadata, metadata_file, indent=2)


def print_summary(
    block_windows: list[BlockWindow],
) -> None:
    print(SYNTHETIC_DATA_DISCLAIMER)
    print(
        f"Block windows generated: "
        f"{len(block_windows)}"
    )

    total_minutes = sum(
        block.available_duration_minutes
        for block in block_windows
    )

    print(
        f"Total available block hours: "
        f"{total_minutes / 60:.1f}"
    )

    for traffic_level in TrafficLevel:
        count = sum(
            block.traffic_level == traffic_level
            for block in block_windows
        )
        print(f"{traffic_level.value} traffic: {count}")

    with_disconnection = sum(
        block.disconnection_available
        for block in block_windows
    )

    print(
        "Windows with disconnection availability: "
        f"{with_disconnection}"
    )


if __name__ == "__main__":
    train_movements = load_train_movements()
    goods_forecasts = load_goods_forecasts()

    generated_blocks = generate_block_windows(
        train_movements,
        goods_forecasts,
    )

    save_block_windows(
        generated_blocks,
        BASE_DATA_PATH,
    )

    print_summary(generated_blocks)
    print(f"Files saved to: {BASE_DATA_PATH.resolve()}")