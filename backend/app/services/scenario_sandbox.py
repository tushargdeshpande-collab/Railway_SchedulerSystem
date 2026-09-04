from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from backend.app.optimization import (
    pune_lonavala_replanner as replanner,
)
from backend.app.simulation import (
    pune_lonavala_disruption as disruption,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]

BASE_SCENARIO_PATH = (
    PROJECT_ROOT
    / "synthetic_data"
    / "scenarios"
    / "pune_lonavala"
    / "base"
)

SANDBOX_ROOT = (
    PROJECT_ROOT
    / "synthetic_data"
    / "scenarios"
    / "pune_lonavala"
    / "sandbox"
)

REPLANNING_LOCK = Lock()

APPROVAL_STORE_PATH = (
    PROJECT_ROOT
    / "synthetic_data"
    / "approvals"
    / "approval_store.json"
)



def load_active_weekly_block_locks() -> set[str]:
    if not APPROVAL_STORE_PATH.exists():
        return set()

    try:
        store = json.loads(
            APPROVAL_STORE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Approval store contains invalid JSON."
        ) from exc

    return {
        str(record["block_id"])
        for record in store.get(
            "block_locks",
            {},
        ).values()
        if (
            record.get("planning_horizon")
            == "weekly"
            and record.get("locked") is True
            and record.get("block_id")
        )
    }


def apply_weekly_locks_to_schedule(
    schedules: list[dict[str, Any]],
    locked_block_ids: set[str],
) -> list[dict[str, Any]]:
    protected_schedules: list[
        dict[str, Any]
    ] = []

    for schedule in schedules:
        protected_schedule = dict(schedule)

        protected_schedule["is_locked"] = (
            str(schedule.get("block_id"))
            in locked_block_ids
        )

        protected_schedules.append(
            protected_schedule
        )

    return protected_schedules


def find_locked_conflicts(
    conflicts: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    locked_block_ids: set[str],
) -> list[dict[str, Any]]:
    if not locked_block_ids:
        return []

    locked_schedules = {
        str(schedule.get("block_id")): schedule
        for schedule in schedules
        if (
            str(schedule.get("block_id"))
            in locked_block_ids
        )
    }

    locked_task_ids = {
        str(task_id)
        for schedule in locked_schedules.values()
        for task_id in schedule.get(
            "task_ids",
            [],
        )
    }

    locked_conflicts: list[
        dict[str, Any]
    ] = []

    for conflict in conflicts:
        conflict_block_id = str(
            conflict.get("block_id")
            or conflict.get(
                "maintenance_block_id"
            )
            or conflict.get(
                "schedule_block_id"
            )
            or ""
        )

        conflict_task_ids = {
            str(task_id)
            for task_id in (
                conflict.get("task_ids")
                or conflict.get(
                    "affected_task_ids"
                )
                or []
            )
        }

        if (
            conflict_block_id
            in locked_block_ids
            or bool(
                conflict_task_ids
                & locked_task_ids
            )
        ):
            locked_conflicts.append(conflict)

    return locked_conflicts


def save_json(
    path: Path,
    data: Any,
) -> None:
    path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def copy_base_scenario(
    destination: Path,
) -> None:
    if not BASE_SCENARIO_PATH.exists():
        raise FileNotFoundError(
            f"Base scenario not found: {BASE_SCENARIO_PATH}"
        )

    destination.mkdir(
        parents=True,
        exist_ok=False,
    )

    for source_file in BASE_SCENARIO_PATH.glob("*.json"):
        shutil.copy2(
            source_file,
            destination / source_file.name,
        )


def build_event(
    event_type: str,
    train_id: str,
    corridor_entry: str,
    corridor_exit: str,
    direction: str,
    priority: int,
    maximum_permissible_delay_minutes: int,
    description: str | None,
) -> dict[str, Any]:
    entry = datetime.fromisoformat(corridor_entry)
    exit_time = datetime.fromisoformat(corridor_exit)

    if exit_time <= entry:
        raise ValueError(
            "Corridor exit must be after corridor entry."
        )

    corridor_duration_minutes = (
        exit_time - entry
    ).total_seconds() / 60

    if corridor_duration_minutes < 15:
        raise ValueError(
            "Corridor movement must be at least "
            "15 minutes long."
        )

    if corridor_duration_minutes > 240:
        raise ValueError(
            "Corridor movement cannot exceed 4 hours "
            "in this demonstration. Check the entry "
            "and exit dates."
        )

    if direction not in {
        "Pune to Lonavala",
        "Lonavala to Pune",
    }:
        raise ValueError(
            "Direction must be 'Pune to Lonavala' or "
            "'Lonavala to Pune'."
        )

    if not 1 <= priority <= 10:
        raise ValueError(
            "Priority must be between 1 and 10."
        )

    if maximum_permissible_delay_minutes < 0:
        raise ValueError(
            "Maximum permissible delay cannot be negative."
        )

    return {
        "event_id": (
            f"SANDBOX-EVENT-{uuid4().hex[:8].upper()}"
        ),
        "event_type": event_type,
        "train_id": train_id,
        "description": (
            description
            or (
                "A synthetic user-injected priority movement "
                "requires corridor access and triggers automated "
                "maintenance conflict analysis."
            )
        ),
        "operating_date": entry.date().isoformat(),
        "requested_corridor_entry": entry.isoformat(),
        "requested_corridor_exit": exit_time.isoformat(),
        "corridor_entry": entry.isoformat(),
        "corridor_exit": exit_time.isoformat(),
        "direction": direction,
        "priority": priority,
        "maximum_permissible_delay_minutes": (
            maximum_permissible_delay_minutes
        ),
        "delay_applied_minutes": 0,
        "delay_evaluated": False,
        "synthetic_data": True,
        "user_injected_scenario": True,
    }


def apply_delay_to_event(
    event: dict[str, Any],
    delay_minutes: int,
) -> dict[str, Any]:
    delayed_event = dict(event)

    requested_entry = datetime.fromisoformat(
        str(event["requested_corridor_entry"])
    )
    requested_exit = datetime.fromisoformat(
        str(event["requested_corridor_exit"])
    )

    delayed_entry = requested_entry + timedelta(
        minutes=delay_minutes
    )
    delayed_exit = requested_exit + timedelta(
        minutes=delay_minutes
    )

    delayed_event["operating_date"] = (
        delayed_entry.date().isoformat()
    )
    delayed_event["corridor_entry"] = (
        delayed_entry.isoformat()
    )
    delayed_event["corridor_exit"] = (
        delayed_exit.isoformat()
    )
    delayed_event["delay_applied_minutes"] = (
        delay_minutes
    )
    delayed_event["delay_evaluated"] = True

    return delayed_event


def evaluate_delay_options(
    event: dict[str, Any],
    original_schedule: list[dict[str, Any]],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    maximum_delay = int(
        event["maximum_permissible_delay_minutes"]
    )

    evaluations: list[dict[str, Any]] = []
    best_event: dict[str, Any] | None = None
    best_movements: list[dict[str, Any]] = []
    best_conflicts: list[dict[str, Any]] = []
    best_conflict_count: int | None = None

    for delay_minutes in range(maximum_delay + 1):
        candidate_event = apply_delay_to_event(
            event,
            delay_minutes,
        )

        candidate_movements = (
            disruption.generate_priority_freight_movements(
                candidate_event
            )
        )

        candidate_conflicts = (
            disruption.detect_conflicts(
                original_schedule,
                candidate_movements,
            )
        )

        conflict_count = len(candidate_conflicts)

        affected_task_ids = {
            task_id
            for conflict in candidate_conflicts
            for task_id in conflict.get(
                "task_ids",
                [],
            )
        }

        evaluations.append(
            {
                "delay_minutes": delay_minutes,
                "corridor_entry": candidate_event[
                    "corridor_entry"
                ],
                "corridor_exit": candidate_event[
                    "corridor_exit"
                ],
                "conflicting_blocks": conflict_count,
                "directly_affected_tasks": len(
                    affected_task_ids
                ),
            }
        )

        if (
            best_conflict_count is None
            or conflict_count < best_conflict_count
        ):
            best_event = candidate_event
            best_movements = candidate_movements
            best_conflicts = candidate_conflicts
            best_conflict_count = conflict_count

        # The earliest conflict-free option is optimal.
        if conflict_count == 0:
            break

    if best_event is None:
        raise RuntimeError(
            "No permissible-delay option could be evaluated."
        )

    original_conflicts = evaluations[0][
        "conflicting_blocks"
    ]

    best_event["conflicts_at_requested_time"] = (
        original_conflicts
    )
    best_event["conflicts_after_delay"] = len(
        best_conflicts
    )
    best_event["conflicts_avoided_by_delay"] = max(
        0,
        original_conflicts - len(best_conflicts),
    )

    return (
        best_event,
        best_movements,
        best_conflicts,
        evaluations,
    )


def add_delay_metrics(
    metrics: dict[str, Any],
    event: dict[str, Any],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched_metrics = dict(metrics)

    enriched_metrics.update(
        {
            "requested_corridor_entry": event[
                "requested_corridor_entry"
            ],
            "requested_corridor_exit": event[
                "requested_corridor_exit"
            ],
            "final_corridor_entry": event[
                "corridor_entry"
            ],
            "final_corridor_exit": event[
                "corridor_exit"
            ],
            "maximum_permissible_delay_minutes": event[
                "maximum_permissible_delay_minutes"
            ],
            "delay_applied_minutes": event[
                "delay_applied_minutes"
            ],
            "conflicts_at_requested_time": event[
                "conflicts_at_requested_time"
            ],
            "conflicts_after_delay": event[
                "conflicts_after_delay"
            ],
            "conflicts_avoided_by_delay": event[
                "conflicts_avoided_by_delay"
            ],
            "delay_options_evaluated": len(
                evaluations
            ),
        }
    )

    return enriched_metrics


def build_no_conflict_metrics(
    event: dict[str, Any],
    original_schedule: list[dict[str, Any]],
) -> dict[str, Any]:
    scheduled_tasks = {
        task_id
        for schedule in original_schedule
        for task_id in schedule.get("task_ids", [])
    }

    return {
        "disclaimer": (
            "Synthetic Demonstration Data - Not an official "
            "Indian Railways operational dataset."
        ),
        "event_type": event["event_type"],
        "event_corridor_entry": event[
            "corridor_entry"
        ],
        "original_schedule_count": len(
            original_schedule
        ),
        "directly_conflicting_tasks": 0,
        "resource_or_dependency_cascade_tasks": 0,
        "total_replanning_scope_tasks": 0,
        "unaffected_schedules_preserved": len(
            original_schedule
        ),
        "affected_tasks_rescheduled": 0,
        "affected_tasks_unscheduled": 0,
        "new_schedule_count": len(
            original_schedule
        ),
        "replanning_solver_status": (
            "NO_REPLANNING_REQUIRED"
        ),
        "replanning_runtime_seconds": 0.0,
        "remaining_priority_freight_conflicts": 0,
        "unchanged_schedule_percentage": 100.0,
        "scheduled_tasks": len(scheduled_tasks),
        "synthetic_data": True,
    }


def run_priority_freight_sandbox(
    event_type: str,
    train_id: str,
    corridor_entry: str,
    corridor_exit: str,
    direction: str,
    priority: int = 10,
    maximum_permissible_delay_minutes: int = 0,
    description: str | None = None,
) -> dict[str, Any]:
    scenario_id = (
        "sandbox-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid4().hex[:6]
    )

    scenario_path = SANDBOX_ROOT / scenario_id

    requested_event = build_event(
        event_type=event_type,
        train_id=train_id,
        corridor_entry=corridor_entry,
        corridor_exit=corridor_exit,
        direction=direction,
        priority=priority,
        maximum_permissible_delay_minutes=(
            maximum_permissible_delay_minutes
        ),
        description=description,
    )

    copy_base_scenario(scenario_path)
    approved_schedule_path = (
        scenario_path / "revised_schedule.json"
    )

    if not approved_schedule_path.exists():
        approved_schedule_path = (
            scenario_path / "optimized_schedule.json"
        )

    original_schedule = json.loads(
        approved_schedule_path.read_text(
            encoding="utf-8"
        )
    )

    locked_block_ids = (
        load_active_weekly_block_locks()
    )

    original_schedule = (
        apply_weekly_locks_to_schedule(
            original_schedule,
            locked_block_ids,
        )
    )

    save_json(
        scenario_path / "optimized_schedule.json",
        original_schedule,
    )

    (
        event,
        freight_movements,
        conflicts,
        delay_evaluations,
    ) = evaluate_delay_options(
        requested_event,
        original_schedule,
    )

    analysis = disruption.build_analysis(
        event,
        conflicts,
    )

    analysis["requested_corridor_entry"] = event[
        "requested_corridor_entry"
    ]
    analysis["requested_corridor_exit"] = event[
        "requested_corridor_exit"
    ]
    analysis["delay_applied_minutes"] = event[
        "delay_applied_minutes"
    ]
    analysis["conflicts_avoided_by_delay"] = event[
        "conflicts_avoided_by_delay"
    ]

    save_json(
        scenario_path / "sandbox_request.json",
        requested_event,
    )
    save_json(
        scenario_path / "priority_freight_event.json",
        event,
    )
    save_json(
        scenario_path
        / "priority_freight_movements.json",
        freight_movements,
    )
    save_json(
        scenario_path / "disruption_conflicts.json",
        conflicts,
    )
    save_json(
        scenario_path / "disruption_analysis.json",
        analysis,
    )
    save_json(
        scenario_path / "delay_evaluations.json",
        delay_evaluations,
    )

    locked_conflicts = find_locked_conflicts(
        conflicts,
        original_schedule,
        locked_block_ids,
    )

    if locked_conflicts:
        affected_task_ids = {
            str(task_id)
            for conflict in locked_conflicts
            for task_id in (
                conflict.get("task_ids")
                or conflict.get(
                    "affected_task_ids"
                )
                or []
            )
        }

        metrics = {
            "disclaimer": (
                "Synthetic Demonstration Data - "
                "Not an official Indian Railways "
                "operational dataset."
            ),
            "event_type": event["event_type"],
            "event_corridor_entry": event[
                "corridor_entry"
            ],
            "original_schedule_count": len(
                original_schedule
            ),
            "directly_conflicting_tasks": len(
                affected_task_ids
            ),
            "resource_or_dependency_cascade_tasks": 0,
            "total_replanning_scope_tasks": len(
                affected_task_ids
            ),
            "unaffected_schedules_preserved": (
                len(original_schedule)
            ),
            "affected_tasks_rescheduled": 0,
            "affected_tasks_unscheduled": 0,
            "new_schedule_count": len(
                original_schedule
            ),
            "replanning_solver_status": (
                "MANUAL_INTERVENTION_REQUIRED"
            ),
            "replanning_runtime_seconds": 0.0,
            "remaining_priority_freight_conflicts": (
                len(locked_conflicts)
            ),
            "unchanged_schedule_percentage": 100.0,
            "locked_conflicting_blocks": len(
                locked_conflicts
            ),
            "locked_block_ids": sorted(
                locked_block_ids
            ),
            "synthetic_data": True,
        }

        metrics = add_delay_metrics(
            metrics,
            event,
            delay_evaluations,
        )

        revised_schedule = original_schedule
        changes: list[dict[str, Any]] = []
        candidate_map: dict[str, list[str]] = {}

        analysis["locked_conflicts"] = len(
            locked_conflicts
        )
        analysis["manual_intervention_required"] = (
            True
        )

        save_json(
            scenario_path / "revised_schedule.json",
            revised_schedule,
        )
        save_json(
            scenario_path / "replanning_metrics.json",
            metrics,
        )
        save_json(
            scenario_path / "replanning_changes.json",
            changes,
        )
        save_json(
            scenario_path
            / "replanning_candidate_map.json",
            candidate_map,
        )
        save_json(
            scenario_path / "sandbox_result.json",
            {
                "scenario_id": scenario_id,
                "status": (
                    "MANUAL_INTERVENTION_REQUIRED"
                ),
                "locked_conflicting_blocks": len(
                    locked_conflicts
                ),
                "remaining_conflicts": len(
                    locked_conflicts
                ),
            },
        )

        return {
            "scenario_id": scenario_id,
            "status": (
                "MANUAL_INTERVENTION_REQUIRED"
            ),
            "event": event,
            "delay_evaluations": delay_evaluations,
            "freight_movements": freight_movements,
            "conflicts": conflicts,
            "locked_conflicts": locked_conflicts,
            "analysis": analysis,
            "metrics": metrics,
            "changes": changes,
            "candidate_map": candidate_map,
            "original_schedule": original_schedule,
            "revised_schedule": revised_schedule,
            "remaining_conflicts": locked_conflicts,
            "sandbox_path": str(scenario_path),
            "synthetic_data": True,
        }

    if not conflicts:
        metrics = build_no_conflict_metrics(
            event,
            original_schedule,
        )
        metrics = add_delay_metrics(
            metrics,
            event,
            delay_evaluations,
        )

        revised_schedule = original_schedule
        changes: list[dict[str, Any]] = []
        candidate_map: dict[str, list[str]] = {}

        save_json(
            scenario_path / "revised_schedule.json",
            revised_schedule,
        )
        save_json(
            scenario_path / "replanning_metrics.json",
            metrics,
        )
        save_json(
            scenario_path / "replanning_changes.json",
            changes,
        )
        save_json(
            scenario_path
            / "replanning_candidate_map.json",
            candidate_map,
        )
        save_json(
            scenario_path / "sandbox_result.json",
            {
                "scenario_id": scenario_id,
                "status": "NO_REPLANNING_REQUIRED",
                "delay_applied_minutes": event[
                    "delay_applied_minutes"
                ],
                "conflicts_at_requested_time": event[
                    "conflicts_at_requested_time"
                ],
                "conflicts_after_delay": 0,
                "conflicts_avoided_by_delay": event[
                    "conflicts_avoided_by_delay"
                ],
                "remaining_conflicts": 0,
            },
        )

        return {
            "scenario_id": scenario_id,
            "status": "NO_REPLANNING_REQUIRED",
            "event": event,
            "delay_evaluations": delay_evaluations,
            "freight_movements": freight_movements,
            "conflicts": conflicts,
            "analysis": analysis,
            "metrics": metrics,
            "changes": changes,
            "candidate_map": candidate_map,
            "original_schedule": original_schedule,
            "revised_schedule": revised_schedule,
            "remaining_conflicts": [],
            "sandbox_path": str(scenario_path),
            "synthetic_data": True,
        }

    original_disruption_path = (
        disruption.SCENARIO_PATH
    )
    original_replanner_path = (
        replanner.SCENARIO_PATH
    )

    with REPLANNING_LOCK:
        try:
            disruption.SCENARIO_PATH = scenario_path
            replanner.SCENARIO_PATH = scenario_path

            (
                revised_schedule,
                metrics,
                changes,
                candidate_map,
            ) = replanner.run_replanning()

        finally:
            disruption.SCENARIO_PATH = (
                original_disruption_path
            )
            replanner.SCENARIO_PATH = (
                original_replanner_path
            )

    remaining_conflicts = (
        replanner.detect_freight_conflicts(
            revised_schedule,
            freight_movements,
        )
    )

    if remaining_conflicts:
        raise RuntimeError(
            "Sandbox replanning completed with unresolved "
            "priority freight conflicts."
        )

    metrics = add_delay_metrics(
        metrics,
        event,
        delay_evaluations,
    )

    save_json(
        scenario_path / "replanning_metrics.json",
        metrics,
    )
    save_json(
        scenario_path / "sandbox_result.json",
        {
            "scenario_id": scenario_id,
            "status": metrics.get(
                "replanning_solver_status",
                "UNKNOWN",
            ),
            "delay_applied_minutes": event[
                "delay_applied_minutes"
            ],
            "conflicts_at_requested_time": event[
                "conflicts_at_requested_time"
            ],
            "direct_conflicts_after_delay": len(
                conflicts
            ),
            "conflicts_avoided_by_delay": event[
                "conflicts_avoided_by_delay"
            ],
            "remaining_conflicts": len(
                remaining_conflicts
            ),
        },
    )

    return {
        "scenario_id": scenario_id,
        "status": metrics.get(
            "replanning_solver_status",
            "UNKNOWN",
        ),
        "event": event,
        "delay_evaluations": delay_evaluations,
        "freight_movements": freight_movements,
        "conflicts": conflicts,
        "analysis": analysis,
        "metrics": metrics,
        "changes": changes,
        "candidate_map": candidate_map,
        "original_schedule": original_schedule,
        "revised_schedule": revised_schedule,
        "remaining_conflicts": remaining_conflicts,
        "sandbox_path": str(scenario_path),
        "synthetic_data": True,
    }