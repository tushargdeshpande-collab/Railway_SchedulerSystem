"""
Generates synthetic COA-style maintenance block windows for the
Pune-Lonavala demonstration corridor.

The normal timetable is checked before a block is made available.
The unexpected priority freight event is intentionally not included
at this stage because it arrives after the original plan is created.
"""

import json
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    DEPARTMENT_CONFIG,
)
from backend.app.data.pune_lonavala_config import (
    CORRIDOR,
    SCENARIO_DISCLAIMER,
    SECTIONS,
    WEEKLY_PLANNING_DAYS,
    WEEKLY_PLANNING_START,
)
from backend.app.schemas.domain import (
    BlockStatus,
    BlockWindow,
    Department,
    DisconnectionType,
    TrafficLevel,
)


SCENARIO_PATH = Path(
    "synthetic_data/scenarios/pune_lonavala/base"
)

CANDIDATE_WINDOWS = [
    {
        "name": "Overnight Primary Window",
        "start": time(0, 30),
        "end": time(4, 30),
        "traffic_level": TrafficLevel.LOW,
    },
    {
        "name": "Late Night Contingency Window",
        "start": time(22, 15),
        "end": time(23, 55),
        "traffic_level": TrafficLevel.MEDIUM,
    },
]

DIRECTION_TRACK = {
    "Pune to Lonavala": "PL-UP",
    "Lonavala to Pune": "PL-DOWN",
}

PERMITTED_DEPARTMENTS = [
    Department.ENGINEERING,
    Department.SIGNAL_TELECOM,
    Department.TRACTION_DISTRIBUTION,
]

SUPPORTED_DISCONNECTIONS = [
    DisconnectionType.NONE,
    DisconnectionType.POWER,
    DisconnectionType.SIGNALLING,
    DisconnectionType.TRACK_POSSESSION,
    DisconnectionType.POWER_AND_TRACK,
]


def load_timetable() -> list[dict[str, Any]]:
    path = (
        SCENARIO_PATH
        / "train_timetable.json"
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        return json.load(input_file)


def get_all_teams() -> list[str]:
    return [
        team
        for config
        in DEPARTMENT_CONFIG.values()
        for team in config["teams"]
    ]


def get_all_equipment() -> list[str]:
    return [
        equipment
        for config
        in DEPARTMENT_CONFIG.values()
        for equipment
        in config["equipment"]
    ]


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


def has_normal_train_conflict(
    timetable: list[dict[str, Any]],
    section_id: str,
    track_id: str,
    block_start: datetime,
    block_end: datetime,
) -> bool:
    for movement in timetable:
        movement_track = DIRECTION_TRACK[
            movement["direction"]
        ]

        if movement_track != track_id:
            continue

        if movement["section_id"] != section_id:
            continue

        movement_start = datetime.fromisoformat(
            movement["scheduled_entry"]
        )

        movement_end = datetime.fromisoformat(
            movement["scheduled_exit"]
        )

        if intervals_overlap(
            block_start,
            block_end,
            movement_start,
            movement_end,
        ):
            return True

    return False


def generate_block_windows(
    timetable: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    int,
]:
    block_records = []
    rejected_conflicts = 0
    block_number = 1

    all_teams = get_all_teams()
    all_equipment = get_all_equipment()

    for day_offset in range(
        WEEKLY_PLANNING_DAYS
    ):
        planning_date = (
            WEEKLY_PLANNING_START
            + timedelta(days=day_offset)
        )

        for section in SECTIONS:
            for track_id in CORRIDOR["tracks"]:
                for window in CANDIDATE_WINDOWS:
                    block_start = datetime.combine(
                        planning_date,
                        window["start"],
                    )

                    block_end = datetime.combine(
                        planning_date,
                        window["end"],
                    )

                    if has_normal_train_conflict(
                        timetable,
                        section["section_id"],
                        track_id,
                        block_start,
                        block_end,
                    ):
                        rejected_conflicts += 1
                        continue

                    duration_minutes = int(
                        (
                            block_end
                            - block_start
                        ).total_seconds()
                        / 60
                    )

                    block = BlockWindow(
                        block_id=(
                            f"PL-BLOCK-"
                            f"{block_number:05d}"
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
                        track_id=track_id,
                        start_time=block_start,
                        end_time=block_end,
                        available_duration_minutes=(
                            duration_minutes
                        ),
                        traffic_level=(
                            window[
                                "traffic_level"
                            ]
                        ),
                        permitted_departments=(
                            PERMITTED_DEPARTMENTS
                        ),
                        disconnection_available=True,
                        supported_disconnection_types=(
                            SUPPORTED_DISCONNECTIONS
                        ),
                        available_teams=all_teams,
                        available_equipment=(
                            all_equipment
                        ),
                        status=(
                            BlockStatus.AVAILABLE
                        ),
                    )

                    record = block.model_dump(
                        mode="json"
                    )

                    record["window_name"] = (
                        window["name"]
                    )

                    record[
                        "generated_before_priority_freight_event"
                    ] = True

                    block_records.append(record)
                    block_number += 1

    return block_records, rejected_conflicts


def validate_generated_blocks(
    timetable: list[dict[str, Any]],
    block_records: list[dict[str, Any]],
) -> int:
    remaining_conflicts = 0

    for record in block_records:
        block = BlockWindow.model_validate(
            record
        )

        if has_normal_train_conflict(
            timetable,
            block.section_id,
            block.track_id,
            block.start_time,
            block.end_time,
        ):
            remaining_conflicts += 1

    return remaining_conflicts


def save_outputs(
    block_records: list[dict[str, Any]],
    rejected_conflicts: int,
    remaining_conflicts: int,
) -> None:
    SCENARIO_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    block_path = (
        SCENARIO_PATH
        / "block_windows.json"
    )

    metadata_path = (
        SCENARIO_PATH
        / "block_window_metadata.json"
    )

    with block_path.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            block_records,
            output_file,
            indent=2,
        )

    metadata = {
        "disclaimer": (
            SCENARIO_DISCLAIMER
        ),
        "generated_block_windows": len(
            block_records
        ),
        "windows_rejected_due_to_normal_trains": (
            rejected_conflicts
        ),
        "remaining_normal_train_conflicts": (
            remaining_conflicts
        ),
        "priority_freight_event_included": False,
        "planning_days": (
            WEEKLY_PLANNING_DAYS
        ),
        "section_count": len(SECTIONS),
        "track_count": len(
            CORRIDOR["tracks"]
        ),
        "windows_per_track_per_day": len(
            CANDIDATE_WINDOWS
        ),
    }

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            metadata,
            output_file,
            indent=2,
        )


def print_summary(
    block_records: list[dict[str, Any]],
    rejected_conflicts: int,
    remaining_conflicts: int,
) -> None:
    print(SCENARIO_DISCLAIMER)
    print(
        f"COA block windows generated: "
        f"{len(block_records)}"
    )
    print(
        "Windows rejected because of normal trains: "
        f"{rejected_conflicts}"
    )
    print(
        "Remaining normal train conflicts: "
        f"{remaining_conflicts}"
    )
    print(
        "Priority freight included in original plan: No"
    )
    print(
        f"Files saved to: "
        f"{SCENARIO_PATH.resolve()}"
    )


if __name__ == "__main__":
    train_timetable = load_timetable()

    (
        generated_blocks,
        rejected_windows,
    ) = generate_block_windows(
        train_timetable
    )

    conflicts_after_generation = (
        validate_generated_blocks(
            train_timetable,
            generated_blocks,
        )
    )

    save_outputs(
        generated_blocks,
        rejected_windows,
        conflicts_after_generation,
    )

    print_summary(
        generated_blocks,
        rejected_windows,
        conflicts_after_generation,
    )

    if conflicts_after_generation:
        raise SystemExit(
            "Generated blocks still conflict "
            "with normal train movements"
        )