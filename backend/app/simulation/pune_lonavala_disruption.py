"""
Injects the unexpected priority perishable-goods movement into the
validated Pune-Lonavala maintenance plan and detects affected blocks.

This step performs conflict detection only. Replanning happens after
the affected blocks and tasks are identified.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.pune_lonavala_config import (
    SCENARIO_DISCLAIMER,
    SECTIONS,
)


SCENARIO_PATH = Path(
    "synthetic_data/scenarios/pune_lonavala/base"
)

DIRECTION_TRACK = {
    "Pune to Lonavala": "PL-UP",
    "Lonavala to Pune": "PL-DOWN",
}


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


def generate_priority_freight_movements(
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    corridor_entry = datetime.fromisoformat(
        event["corridor_entry"]
    )

    corridor_exit = datetime.fromisoformat(
        event["corridor_exit"]
    )

    direction = event["direction"]
    track_id = DIRECTION_TRACK[direction]

    route_sections = (
        list(SECTIONS)
        if direction == "Pune to Lonavala"
        else list(reversed(SECTIONS))
    )

    total_seconds = (
        corridor_exit - corridor_entry
    ).total_seconds()

    section_slot_seconds = (
        total_seconds / len(route_sections)
    )

    movements = []

    for index, section in enumerate(
        route_sections
    ):
        section_entry = (
            corridor_entry
            + timedelta(
                seconds=(
                    index
                    * section_slot_seconds
                )
            )
        )

        section_exit = (
            corridor_entry
            + timedelta(
                seconds=(
                    (index + 1)
                    * section_slot_seconds
                )
            )
            - timedelta(minutes=1)
        )

        movements.append(
            {
                "movement_id": (
                    f"{event['train_id']}-"
                    f"SEC-{index + 1:02d}"
                ),
                "event_id": event["event_id"],
                "train_id": event["train_id"],
                "event_type": event["event_type"],
                "corridor_id": "PL-COR-01",
                "section_id": (
                    section["section_id"]
                ),
                "track_id": track_id,
                "direction": direction,
                "scheduled_entry": (
                    section_entry.isoformat()
                ),
                "scheduled_exit": (
                    section_exit.isoformat()
                ),
                "priority": event["priority"],
                "maximum_permissible_delay_minutes": (
                    event[
                        "maximum_permissible_delay_minutes"
                    ]
                ),
                "synthetic_data": True,
            }
        )

    return movements


def detect_conflicts(
    schedules: list[dict[str, Any]],
    freight_movements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    conflicts = []

    for schedule in schedules:
        schedule_start = datetime.fromisoformat(
            schedule["scheduled_start"]
        )

        schedule_end = datetime.fromisoformat(
            schedule["scheduled_end"]
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

            movement_start = datetime.fromisoformat(
                movement["scheduled_entry"]
            )

            movement_end = datetime.fromisoformat(
                movement["scheduled_exit"]
            )

            if intervals_overlap(
                schedule_start,
                schedule_end,
                movement_start,
                movement_end,
            ):
                conflicts.append(
                    {
                        "schedule_id": (
                            schedule[
                                "schedule_id"
                            ]
                        ),
                        "block_id": (
                            schedule["block_id"]
                        ),
                        "task_ids": (
                            schedule["task_ids"]
                        ),
                        "section_id": (
                            schedule["section_id"]
                        ),
                        "track_id": (
                            schedule["track_id"]
                        ),
                        "maintenance_start": (
                            schedule[
                                "scheduled_start"
                            ]
                        ),
                        "maintenance_end": (
                            schedule[
                                "scheduled_end"
                            ]
                        ),
                        "freight_movement_id": (
                            movement[
                                "movement_id"
                            ]
                        ),
                        "freight_entry": (
                            movement[
                                "scheduled_entry"
                            ]
                        ),
                        "freight_exit": (
                            movement[
                                "scheduled_exit"
                            ]
                        ),
                        "is_locked": (
                            schedule.get(
                                "is_locked",
                                False,
                            )
                        ),
                    }
                )

    return conflicts


def build_analysis(
    event: dict[str, Any],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    affected_schedule_ids = sorted(
        {
            conflict["schedule_id"]
            for conflict in conflicts
        }
    )

    affected_block_ids = sorted(
        {
            conflict["block_id"]
            for conflict in conflicts
        }
    )

    affected_task_ids = sorted(
        {
            task_id
            for conflict in conflicts
            for task_id in conflict["task_ids"]
        }
    )

    locked_conflicts = [
        conflict
        for conflict in conflicts
        if conflict["is_locked"]
    ]

    return {
        "disclaimer": SCENARIO_DISCLAIMER,
        "event": event,
        "conflict_detected": bool(conflicts),
        "conflict_record_count": len(
            conflicts
        ),
        "affected_schedule_count": len(
            affected_schedule_ids
        ),
        "affected_block_count": len(
            affected_block_ids
        ),
        "affected_task_count": len(
            affected_task_ids
        ),
        "affected_schedule_ids": (
            affected_schedule_ids
        ),
        "affected_block_ids": (
            affected_block_ids
        ),
        "affected_task_ids": (
            affected_task_ids
        ),
        "locked_conflict_count": len(
            locked_conflicts
        ),
        "recommended_action": (
            "Re-optimize affected future maintenance tasks "
            "while preserving unaffected and locked blocks."
            if conflicts
            else
            "No replanning required."
        ),
    }


def print_summary(
    event: dict[str, Any],
    movements: list[dict[str, Any]],
    analysis: dict[str, Any],
) -> None:
    print(SCENARIO_DISCLAIMER)

    print(
        f"Injected event: "
        f"{event['event_type']}"
    )

    print(
        f"Direction: {event['direction']}"
    )

    print(
        f"Priority freight section movements: "
        f"{len(movements)}"
    )

    print(
        f"Conflict detected: "
        f"{analysis['conflict_detected']}"
    )

    print(
        f"Affected maintenance schedules: "
        f"{analysis['affected_schedule_count']}"
    )

    print(
        f"Affected maintenance blocks: "
        f"{analysis['affected_block_count']}"
    )

    print(
        f"Affected maintenance tasks: "
        f"{analysis['affected_task_count']}"
    )

    print(
        f"Locked conflicts: "
        f"{analysis['locked_conflict_count']}"
    )

    print(
        "Affected task IDs: "
        f"{analysis['affected_task_ids']}"
    )

    print(
        f"Files saved to: "
        f"{SCENARIO_PATH.resolve()}"
    )


if __name__ == "__main__":
    priority_event = load_json(
        "priority_freight_event.json"
    )

    original_schedule = load_json(
        "optimized_schedule.json"
    )

    priority_movements = (
        generate_priority_freight_movements(
            priority_event
        )
    )

    detected_conflicts = detect_conflicts(
        original_schedule,
        priority_movements,
    )

    disruption_analysis = build_analysis(
        priority_event,
        detected_conflicts,
    )

    save_json(
        "priority_freight_movements.json",
        priority_movements,
    )

    save_json(
        "disruption_conflicts.json",
        detected_conflicts,
    )

    save_json(
        "disruption_analysis.json",
        disruption_analysis,
    )

    print_summary(
        priority_event,
        priority_movements,
        disruption_analysis,
    )

    if not detected_conflicts:
        raise SystemExit(
            "The synthetic event did not overlap the current plan. "
            "The event timing or track must be adjusted."
        )