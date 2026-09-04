from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import uuid4
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.app.services.scenario_sandbox import (
    run_priority_freight_sandbox,
)
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_PATH = PROJECT_ROOT / "frontend"


BASE_DATA_PATH = (
    PROJECT_ROOT
    / "synthetic_data"
    / "generated"
    / "base"
)

PUNE_LONAVALA_DATA_PATH = (
    PROJECT_ROOT
    / "synthetic_data"
    / "scenarios"
    / "pune_lonavala"
    / "base"
)

DISCLAIMER = (
    "Synthetic Demonstration Data - Station names are used only "
    "to demonstrate the planning workflow. Train timings, counts, "
    "chainages, maintenance tasks and forecasts are not official "
    "Indian Railways operational data."
)


APPROVAL_DATA_PATH = (
    PROJECT_ROOT
    / "synthetic_data"
    / "approvals"
)

APPROVAL_STORE_PATH = (
    APPROVAL_DATA_PATH
    / "approval_store.json"
)

APPROVAL_LOCK = Lock()


app = FastAPI(
    title="GatiPatha Automatic Block Planning API",
    description=(
        "Synthetic railway maintenance block planning, optimization "
        "and dynamic replanning demonstration API."
    ),
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    "/ui",
    StaticFiles(
        directory=str(FRONTEND_PATH),
        html=True,
    ),
    name="ui",
)


def load_json(
    directory: Path,
    filename: str,
    required: bool = True,
) -> Any:
    path = directory / filename

    if not path.exists():
        if required:
            raise HTTPException(
                status_code=404,
                detail=f"Data file not found: {filename}",
            )
        return None

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON in {filename}: {exc}",
        ) from exc


def select_data_path(
    scenario: Literal["base", "pune_lonavala"],
) -> Path:
    if scenario == "base":
        return BASE_DATA_PATH

    return PUNE_LONAVALA_DATA_PATH


def filter_records(
    records: list[dict[str, Any]],
    department: str | None = None,
    section_id: str | None = None,
    priority_level: str | None = None,
    track_id: str | None = None,
) -> list[dict[str, Any]]:
    filtered = records

    if department:
        department_lower = department.lower()

        filtered = [
            record
            for record in filtered
            if (
                str(record.get("department", "")).lower()
                == department_lower
                or department_lower
                in {
                    str(item).lower()
                    for item in record.get("departments", [])
                }
            )
        ]

    if section_id:
        filtered = [
            record
            for record in filtered
            if record.get("section_id") == section_id
        ]

    if priority_level:
        filtered = [
            record
            for record in filtered
            if str(
                record.get("priority_level", "")
            ).lower()
            == priority_level.lower()
        ]

    if track_id:
        filtered = [
            record
            for record in filtered
            if record.get("track_id") == track_id
        ]

    return filtered


def make_task_schedule_map(
    schedules: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for schedule in schedules:
        for task_id in schedule.get("task_ids", []):
            result[task_id] = schedule

    return result

class PriorityFreightSandboxRequest(BaseModel):
    event_type: str = Field(
        default="Priority Perishable Goods Movement",
        min_length=3,
        max_length=100,
    )

    train_id: str = Field(
        default="PL-USER-FREIGHT-001",
        min_length=3,
        max_length=50,
    )

    corridor_entry: datetime

    corridor_exit: datetime

    direction: Literal[
        "Pune to Lonavala",
        "Lonavala to Pune",
    ] = "Pune to Lonavala"

    priority: int = Field(
        default=10,
        ge=1,
        le=10,
    )

    maximum_permissible_delay_minutes: int = Field(
        default=0,
        ge=0,
        le=180,
    )

    description: str | None = Field(
        default=None,
        max_length=500,
    )
    

class PlanDecisionRequest(BaseModel):
    planning_horizon: Literal[
        "weekly",
        "monthly",
    ]

    decision: Literal[
        "approve",
        "reject",
        "reset",
    ]

    approver_name: str = Field(
        min_length=2,
        max_length=100,
    )

    approver_role: str = Field(
        min_length=2,
        max_length=100,
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )


class BlockLockRequest(BaseModel):
    planning_horizon: Literal[
        "weekly",
        "monthly",
    ]

    locked: bool

    actor_name: str = Field(
        min_length=2,
        max_length=100,
    )

    actor_role: str = Field(
        min_length=2,
        max_length=100,
    )

    reason: str | None = Field(
        default=None,
        max_length=500,
    )


def default_approval_store() -> dict[str, Any]:
    return {
        "plans": {
            "weekly": {
                "status": "Pending",
                "planning_horizon": "weekly",
                "approver_name": None,
                "approver_role": None,
                "remarks": None,
                "decided_at": None,
            },
            "monthly": {
                "status": "Pending",
                "planning_horizon": "monthly",
                "approver_name": None,
                "approver_role": None,
                "remarks": None,
                "decided_at": None,
            },
        },
        "block_locks": {},
        "audit_log": [],
        "synthetic_data": True,
    }


def load_approval_store() -> dict[str, Any]:
    if not APPROVAL_STORE_PATH.exists():
        return default_approval_store()

    try:
        return json.loads(
            APPROVAL_STORE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Approval store contains invalid JSON."
            ),
        ) from exc


def save_approval_store(
    store: dict[str, Any],
) -> None:
    APPROVAL_DATA_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        APPROVAL_STORE_PATH.with_suffix(".tmp")
    )

    temporary_path.write_text(
        json.dumps(
            store,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        APPROVAL_STORE_PATH
    )


def get_schedule_for_horizon(
    planning_horizon: Literal[
        "weekly",
        "monthly",
    ],
) -> list[dict[str, Any]]:
    if planning_horizon == "monthly":
        return load_json(
            BASE_DATA_PATH,
            "optimized_schedule.json",
        )

    return load_json(
        PUNE_LONAVALA_DATA_PATH,
        "revised_schedule.json",
    )


def create_audit_entry(
    *,
    action: str,
    planning_horizon: str,
    actor_name: str,
    actor_role: str,
    target_id: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "audit_id": (
            f"AUDIT-{uuid4().hex[:10].upper()}"
        ),
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "planning_horizon": planning_horizon,
        "actor_name": actor_name,
        "actor_role": actor_role,
        "target_id": target_id,
        "details": details,
        "synthetic_data": True,
    }


@app.get("/api/v1/approvals")
def get_approval_status(
    planning_horizon: Literal[
        "weekly",
        "monthly",
    ] = "weekly",
) -> dict[str, Any]:
    with APPROVAL_LOCK:
        store = load_approval_store()

    plan = store.get(
        "plans",
        {},
    ).get(
        planning_horizon,
        {
            "status": "Pending",
            "planning_horizon": planning_horizon,
        },
    )

    locks = [
        lock
        for lock in store.get(
            "block_locks",
            {},
        ).values()
        if (
            lock.get("planning_horizon")
            == planning_horizon
            and lock.get("locked") is True
        )
    ]

    audit_entries = [
        entry
        for entry in store.get(
            "audit_log",
            [],
        )
        if (
            entry.get("planning_horizon")
            == planning_horizon
        )
    ]

    return {
        "planning_horizon": planning_horizon,
        "plan": plan,
        "locked_block_count": len(locks),
        "locked_blocks": locks,
        "audit_log": audit_entries[-100:],
        "synthetic_data": True,
    }


@app.post("/api/v1/approvals/decision")
def record_plan_decision(
    request: PlanDecisionRequest,
) -> dict[str, Any]:
    status_mapping = {
        "approve": "Approved",
        "reject": "Rejected",
        "reset": "Pending",
    }

    status = status_mapping[
        request.decision
    ]

    decided_at = datetime.now().isoformat()

    plan_record = {
        "status": status,
        "planning_horizon": (
            request.planning_horizon
        ),
        "approver_name": request.approver_name,
        "approver_role": request.approver_role,
        "remarks": request.remarks,
        "decided_at": decided_at,
    }

    audit_entry = create_audit_entry(
        action=f"PLAN_{status.upper()}",
        planning_horizon=(
            request.planning_horizon
        ),
        actor_name=request.approver_name,
        actor_role=request.approver_role,
        target_id=(
            f"{request.planning_horizon}-plan"
        ),
        details={
            "decision": request.decision,
            "status": status,
            "remarks": request.remarks,
        },
    )

    with APPROVAL_LOCK:
        store = load_approval_store()

        store.setdefault(
            "plans",
            {},
        )[request.planning_horizon] = (
            plan_record
        )

        store.setdefault(
            "audit_log",
            [],
        ).append(audit_entry)

        save_approval_store(store)

    return {
        "message": (
            f"{request.planning_horizon.title()} "
            f"plan status changed to {status}."
        ),
        "plan": plan_record,
        "audit_entry": audit_entry,
        "synthetic_data": True,
    }


@app.post("/api/v1/blocks/{block_id}/lock")
def update_block_lock(
    block_id: str,
    request: BlockLockRequest,
) -> dict[str, Any]:
    schedules = get_schedule_for_horizon(
        request.planning_horizon
    )

    valid_block_ids = {
        str(schedule.get("block_id"))
        for schedule in schedules
    }

    if block_id not in valid_block_ids:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Block {block_id} was not found in "
                f"the {request.planning_horizon} plan."
            ),
        )

    lock_key = (
        f"{request.planning_horizon}:"
        f"{block_id}"
    )

    lock_record = {
        "block_id": block_id,
        "planning_horizon": (
            request.planning_horizon
        ),
        "locked": request.locked,
        "actor_name": request.actor_name,
        "actor_role": request.actor_role,
        "reason": request.reason,
        "updated_at": datetime.now().isoformat(),
    }

    action = (
        "BLOCK_LOCKED"
        if request.locked
        else "BLOCK_UNLOCKED"
    )

    audit_entry = create_audit_entry(
        action=action,
        planning_horizon=(
            request.planning_horizon
        ),
        actor_name=request.actor_name,
        actor_role=request.actor_role,
        target_id=block_id,
        details={
            "locked": request.locked,
            "reason": request.reason,
        },
    )

    with APPROVAL_LOCK:
        store = load_approval_store()

        store.setdefault(
            "block_locks",
            {},
        )[lock_key] = lock_record

        store.setdefault(
            "audit_log",
            [],
        ).append(audit_entry)

        save_approval_store(store)

    return {
        "message": (
            f"Block {block_id} "
            + (
                "locked."
                if request.locked
                else "unlocked."
            )
        ),
        "block_lock": lock_record,
        "audit_entry": audit_entry,
        "synthetic_data": True,
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "project": "GatiPatha Automatic Block Planning System",
        "team": "GatiPatha Voyage",
        "status": "API operational",
        "api_version": "1.0.0",
        "documentation": "/docs",
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/v1/health")
def health_check() -> dict[str, Any]:
    required_files = [
        "scored_maintenance_tasks.json",
        "block_windows.json",
        "train_timetable.json",
        "optimized_schedule.json",
        "revised_schedule.json",
        "replanning_metrics.json",
        "replan_validation_report.json",
    ]

    file_status = {
        filename: (
            PUNE_LONAVALA_DATA_PATH / filename
        ).exists()
        for filename in required_files
    }

    all_available = all(file_status.values())

    return {
        "status": (
            "healthy"
            if all_available
            else "degraded"
        ),
        "all_required_files_available": all_available,
        "files": file_status,
        "data_path": str(PUNE_LONAVALA_DATA_PATH),
        "synthetic_data": True,
    }


@app.get("/api/v1/scenarios")
def get_scenarios() -> dict[str, Any]:
    return {
        "scenarios": [
            {
                "scenario_id": "base",
                "name": "Multi-Corridor Benchmark",
                "description": (
                    "Thirty-day synthetic benchmark covering "
                    "multiple fictional corridors."
                ),
                "planning_horizon": "Monthly",
            },
            {
                "scenario_id": "pune_lonavala",
                "name": "Pune-Lonavala Dynamic Block Planning",
                "description": (
                    "Focused weekly demonstration with priority "
                    "perishable freight replanning."
                ),
                "planning_horizon": "Weekly",
            },
        ],
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/v1/scenarios/{scenario}/metadata")
def get_scenario_metadata(
    scenario: Literal["base", "pune_lonavala"],
) -> dict[str, Any]:
    data_path = select_data_path(scenario)

    if scenario == "pune_lonavala":
        metadata = load_json(
            data_path,
            "scenario_metadata.json",
        )
    else:
        metadata = load_json(
            data_path,
            "metadata.json",
            required=False,
        )

    return {
        "scenario_id": scenario,
        "metadata": metadata or {},
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/v1/tasks")
def get_tasks(
    scenario: Literal[
        "base",
        "pune_lonavala",
    ] = "pune_lonavala",
    department: str | None = Query(default=None),
    section_id: str | None = Query(default=None),
    priority_level: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    data_path = select_data_path(scenario)

    tasks = load_json(
        data_path,
        "scored_maintenance_tasks.json",
    )

    filtered = filter_records(
        tasks,
        department=department,
        section_id=section_id,
        priority_level=priority_level,
    )

    filtered.sort(
        key=lambda task: float(
            task.get("priority_score", 0)
        ),
        reverse=True,
    )

    return {
        "scenario_id": scenario,
        "count": len(filtered),
        "returned": min(len(filtered), limit),
        "tasks": filtered[:limit],
        "synthetic_data": True,
    }


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    tasks = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "scored_maintenance_tasks.json",
    )

    task = next(
        (
            item
            for item in tasks
            if item.get("task_id") == task_id
        ),
        None,
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task not found: {task_id}",
        )

    original_schedule = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "optimized_schedule.json",
    )
    revised_schedule = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "revised_schedule.json",
    )

    original_map = make_task_schedule_map(
        original_schedule
    )
    revised_map = make_task_schedule_map(
        revised_schedule
    )

    return {
        "task": task,
        "original_assignment": original_map.get(task_id),
        "revised_assignment": revised_map.get(task_id),
        "synthetic_data": True,
    }


@app.get("/api/v1/block-windows")
def get_block_windows(
    scenario: Literal[
        "base",
        "pune_lonavala",
    ] = "pune_lonavala",
    section_id: str | None = Query(default=None),
    track_id: str | None = Query(default=None),
    traffic_level: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> dict[str, Any]:
    data_path = select_data_path(scenario)

    blocks = load_json(
        data_path,
        "block_windows.json",
    )

    filtered = filter_records(
        blocks,
        section_id=section_id,
        track_id=track_id,
    )

    if traffic_level:
        filtered = [
            block
            for block in filtered
            if str(
                block.get("traffic_level", "")
            ).lower()
            == traffic_level.lower()
        ]

    filtered.sort(
        key=lambda block: block.get("start_time", "")
    )

    return {
        "scenario_id": scenario,
        "count": len(filtered),
        "returned": min(len(filtered), limit),
        "block_windows": filtered[:limit],
        "synthetic_data": True,
    }


@app.get("/api/v1/timetable")
def get_timetable(
    section_id: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    train_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    movements = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "train_timetable.json",
    )

    filtered = movements

    if section_id:
        filtered = [
            movement
            for movement in filtered
            if movement.get("section_id") == section_id
        ]

    if direction:
        filtered = [
            movement
            for movement in filtered
            if str(
                movement.get("direction", "")
            ).lower()
            == direction.lower()
        ]

    if train_type:
        filtered = [
            movement
            for movement in filtered
            if str(
                movement.get("train_type", "")
            ).lower()
            == train_type.lower()
        ]

    filtered.sort(
        key=lambda movement: movement.get(
            "scheduled_entry",
            "",
        )
    )

    return {
        "count": len(filtered),
        "returned": min(len(filtered), limit),
        "movements": filtered[:limit],
        "synthetic_data": True,
    }


@app.get("/api/v1/schedules/original")
def get_original_schedule(
    department: str | None = Query(default=None),
    section_id: str | None = Query(default=None),
    track_id: str | None = Query(default=None),
) -> dict[str, Any]:
    schedules = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "optimized_schedule.json",
    )

    filtered = filter_records(
        schedules,
        department=department,
        section_id=section_id,
        track_id=track_id,
    )

    filtered.sort(
        key=lambda schedule: schedule.get(
            "scheduled_start",
            "",
        )
    )

    return {
        "plan": "original",
        "count": len(filtered),
        "schedules": filtered,
        "synthetic_data": True,
    }


@app.get("/api/v1/schedules/revised")
def get_revised_schedule(
    department: str | None = Query(default=None),
    section_id: str | None = Query(default=None),
    track_id: str | None = Query(default=None),
) -> dict[str, Any]:
    schedules = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "revised_schedule.json",
    )

    filtered = filter_records(
        schedules,
        department=department,
        section_id=section_id,
        track_id=track_id,
    )

    filtered.sort(
        key=lambda schedule: schedule.get(
            "scheduled_start",
            "",
        )
    )

    return {
        "plan": "revised",
        "count": len(filtered),
        "schedules": filtered,
        "synthetic_data": True,
    }


@app.get("/api/v1/disruption")
def get_disruption() -> dict[str, Any]:
    event = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "priority_freight_event.json",
    )
    movements = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "priority_freight_movements.json",
    )
    analysis = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "disruption_analysis.json",
    )
    conflicts = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "disruption_conflicts.json",
    )

    return {
        "event": event,
        "movements": movements,
        "analysis": analysis,
        "conflicts": conflicts,
        "synthetic_data": True,
    }


@app.get("/api/v1/replanning")
def get_replanning_result() -> dict[str, Any]:
    metrics = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "replanning_metrics.json",
    )
    changes = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "replanning_changes.json",
    )
    validation = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "replan_validation_report.json",
    )

    return {
        "metrics": metrics,
        "changes": changes,
        "validation": validation,
        "synthetic_data": True,
    }


@app.get("/api/v1/dashboard")
def get_dashboard() -> dict[str, Any]:
    tasks = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "scored_maintenance_tasks.json",
    )
    original = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "optimized_schedule.json",
    )
    revised = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "revised_schedule.json",
    )
    replanning = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "replanning_metrics.json",
    )
    validation = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "replan_validation_report.json",
    )
    scenario = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "scenario_metadata.json",
    )

    original_tasks = make_task_schedule_map(original)
    revised_tasks = make_task_schedule_map(revised)

    priority_counts = Counter(
        str(task.get("priority_level", "Unknown"))
        for task in tasks
    )

    department_counts = Counter(
        str(task.get("department", "Unknown"))
        for task in tasks
    )

    return {
        "project": "GatiPatha Automatic Block Planning",
        "scenario": scenario,
        "kpis": {
            "maintenance_tasks": len(tasks),
            "original_scheduled_tasks": len(
                original_tasks
            ),
            "revised_scheduled_tasks": len(
                revised_tasks
            ),
            "original_blocks": len(original),
            "revised_blocks": len(revised),
            "blocks_reduced_after_replanning": (
                len(original) - len(revised)
            ),
            "direct_freight_conflicts": replanning.get(
                "directly_conflicting_tasks",
                0,
            ),
            "replanning_scope_tasks": replanning.get(
                "total_replanning_scope_tasks",
                0,
            ),
            "remaining_freight_conflicts": replanning.get(
                "remaining_priority_freight_conflicts",
                0,
            ),
            "solver_status": replanning.get(
                "replanning_solver_status"
            ),
            "solver_runtime_seconds": replanning.get(
                "replanning_runtime_seconds"
            ),
            "validation_status": validation.get(
                "validation_status"
            ),
        },
        "priority_distribution": dict(priority_counts),
        "department_distribution": dict(
            department_counts
        ),
        "disclaimer": DISCLAIMER,
        "synthetic_data": True,
    }


@app.get("/api/v1/comparison")
def get_schedule_comparison() -> dict[str, Any]:
    original = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "optimized_schedule.json",
    )
    revised = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "revised_schedule.json",
    )
    changes = load_json(
        PUNE_LONAVALA_DATA_PATH,
        "replanning_changes.json",
    )

    original_map = make_task_schedule_map(original)
    revised_map = make_task_schedule_map(revised)

    comparison: list[dict[str, Any]] = []

    for change in changes:
        task_id = change["task_id"]
        original_assignment = original_map.get(task_id)
        revised_assignment = revised_map.get(task_id)

        if original_assignment is None:
            classification = "Newly Scheduled"
        elif revised_assignment is None:
            classification = "Unscheduled"
        else:
            same_start = (
                original_assignment["scheduled_start"]
                == revised_assignment["scheduled_start"]
            )
            same_end = (
                original_assignment["scheduled_end"]
                == revised_assignment["scheduled_end"]
            )
            same_block = (
                original_assignment["block_id"]
                == revised_assignment["block_id"]
            )
            same_bundle = set(
                original_assignment.get("task_ids", [])
            ) == set(
                revised_assignment.get("task_ids", [])
            )

            if (
                same_start
                and same_end
                and same_block
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

        comparison.append(
            {
                **change,
                "classification": classification,
                "original_assignment": original_assignment,
                "revised_assignment": revised_assignment,
            }
        )

    return {
        "count": len(comparison),
        "changes": comparison,
        "synthetic_data": True,
    }
@app.get("/api/v1/monthly/dashboard")
def get_monthly_dashboard() -> dict[str, Any]:
    tasks = load_json(
        BASE_DATA_PATH,
        "scored_maintenance_tasks.json",
    )
    baseline_schedule = load_json(
        BASE_DATA_PATH,
        "baseline_schedule.json",
    )
    optimized_schedule = load_json(
        BASE_DATA_PATH,
        "optimized_schedule.json",
    )
    baseline_metrics = load_json(
        BASE_DATA_PATH,
        "baseline_metrics.json",
    )
    optimization_metrics = load_json(
        BASE_DATA_PATH,
        "optimization_metrics.json",
    )
    comparison = load_json(
        BASE_DATA_PATH,
        "planning_comparison.json",
    )
    validation = load_json(
        BASE_DATA_PATH,
        "schedule_validation_report.json",
    )

    priority_counts = Counter(
        str(task.get("priority_level", "Unknown"))
        for task in tasks
    )

    department_counts = Counter(
        str(task.get("department", "Unknown"))
        for task in tasks
    )

    return {
        "project": "GatiPatha Automatic Block Planning",
        "planning_horizon": "monthly",
        "planning_period_days": 30,
        "scenario": {
            "scenario_name": (
                "Synthetic Multi-Corridor Monthly Block Plan"
            ),
            "description": (
                "Thirty-day strategic maintenance block plan "
                "covering synthetic railway corridors."
            ),
        },
        "kpis": {
            "maintenance_tasks": len(tasks),
            "original_scheduled_tasks": baseline_metrics.get(
                "scheduled_tasks",
                0,
            ),
            "revised_scheduled_tasks": (
                optimization_metrics.get(
                    "scheduled_tasks",
                    0,
                )
            ),
            "original_blocks": baseline_metrics.get(
                "blocks_used",
                len(baseline_schedule),
            ),
            "revised_blocks": optimization_metrics.get(
                "blocks_used",
                len(optimized_schedule),
            ),
            "blocks_reduced_after_replanning": (
                comparison.get(
                    "improvement",
                    {},
                ).get(
                    "blocks_avoided",
                    0,
                )
            ),
            "block_reduction_percent": (
                comparison.get(
                    "improvement",
                    {},
                ).get(
                    "block_reduction_percent",
                    0,
                )
            ),
            "bundled_blocks": (
                optimization_metrics.get(
                    "bundled_blocks",
                    0,
                )
            ),
            "tasks_in_bundled_blocks": (
                optimization_metrics.get(
                    "tasks_in_bundled_blocks",
                    0,
                )
            ),
            "average_block_utilization_percent": (
                optimization_metrics.get(
                    "average_block_utilization_percent",
                    0,
                )
            ),
            "estimated_train_impact_minutes": (
                optimization_metrics.get(
                    "estimated_total_train_impact_minutes",
                    0,
                )
            ),
            "direct_freight_conflicts": 0,
            "replanning_scope_tasks": 0,
            "remaining_freight_conflicts": 0,
            "solver_status": optimization_metrics.get(
                "solver_status",
                "UNKNOWN",
            ),
            "solver_runtime_seconds": (
                optimization_metrics.get(
                    "solver_runtime_seconds",
                    0,
                )
            ),
            "validation_status": validation.get(
                "status",
                "UNKNOWN",
            ),
        },
        "priority_distribution": dict(priority_counts),
        "department_distribution": dict(
            department_counts
        ),
        "validation": validation,
        "baseline_metrics": baseline_metrics,
        "optimization_metrics": optimization_metrics,
        "improvement": comparison.get(
            "improvement",
            {},
        ),
        "disclaimer": DISCLAIMER,
        "synthetic_data": True,
    }


@app.get("/api/v1/monthly/schedules")
def get_monthly_schedules(
    department: str | None = Query(default=None),
    section_id: str | None = Query(default=None),
    track_id: str | None = Query(default=None),
) -> dict[str, Any]:
    schedules = load_json(
        BASE_DATA_PATH,
        "optimized_schedule.json",
    )

    filtered = filter_records(
        schedules,
        department=department,
        section_id=section_id,
        track_id=track_id,
    )

    filtered.sort(
        key=lambda schedule: schedule.get(
            "scheduled_start",
            "",
        )
    )

    return {
        "plan": "monthly_optimized",
        "planning_horizon": "monthly",
        "planning_period_days": 30,
        "count": len(filtered),
        "schedules": filtered,
        "synthetic_data": True,
    }


@app.get("/api/v1/monthly/comparison")
def get_monthly_comparison() -> dict[str, Any]:
    baseline = load_json(
        BASE_DATA_PATH,
        "baseline_schedule.json",
    )
    optimized = load_json(
        BASE_DATA_PATH,
        "optimized_schedule.json",
    )
    metrics = load_json(
        BASE_DATA_PATH,
        "planning_comparison.json",
    )

    baseline_map = make_task_schedule_map(
        baseline
    )
    optimized_map = make_task_schedule_map(
        optimized
    )

    task_ids = sorted(
        set(baseline_map)
        | set(optimized_map)
    )

    changes: list[dict[str, Any]] = []

    for task_id in task_ids:
        original_assignment = baseline_map.get(
            task_id
        )
        revised_assignment = optimized_map.get(
            task_id
        )

        if original_assignment is None:
            classification = "Newly Scheduled"
        elif revised_assignment is None:
            classification = "Unscheduled"
        else:
            same_start = (
                original_assignment.get(
                    "scheduled_start"
                )
                == revised_assignment.get(
                    "scheduled_start"
                )
            )
            same_end = (
                original_assignment.get(
                    "scheduled_end"
                )
                == revised_assignment.get(
                    "scheduled_end"
                )
            )
            same_block = (
                original_assignment.get("block_id")
                == revised_assignment.get("block_id")
            )
            same_bundle = set(
                original_assignment.get(
                    "task_ids",
                    [],
                )
            ) == set(
                revised_assignment.get(
                    "task_ids",
                    [],
                )
            )

            if (
                same_start
                and same_end
                and same_block
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

        changes.append(
            {
                "task_id": task_id,
                "direct_freight_conflict": False,
                "impact_label": "Monthly optimization",
                "original_start": (
                    original_assignment.get(
                        "scheduled_start"
                    )
                    if original_assignment
                    else None
                ),
                "revised_start": (
                    revised_assignment.get(
                        "scheduled_start"
                    )
                    if revised_assignment
                    else None
                ),
                "original_block_id": (
                    original_assignment.get(
                        "block_id"
                    )
                    if original_assignment
                    else None
                ),
                "revised_block_id": (
                    revised_assignment.get(
                        "block_id"
                    )
                    if revised_assignment
                    else None
                ),
                "classification": classification,
                "original_assignment": (
                    original_assignment
                ),
                "revised_assignment": (
                    revised_assignment
                ),
            }
        )

    return {
        "planning_horizon": "monthly",
        "planning_period_days": 30,
        "count": len(changes),
        "changes": changes,
        "summary": metrics,
        "synthetic_data": True,
    }
@app.post("/api/v1/scenario-sandbox/run")
def run_scenario_sandbox(
    request: PriorityFreightSandboxRequest,
) -> dict[str, Any]:
    try:
        return run_priority_freight_sandbox(
            event_type=request.event_type,
            train_id=request.train_id,
            corridor_entry=(
                request.corridor_entry.isoformat()
            ),
            corridor_exit=(
                request.corridor_exit.isoformat()
            ),
            direction=request.direction,
            priority=request.priority,
            maximum_permissible_delay_minutes=(
                request.maximum_permissible_delay_minutes
            ),
            description=request.description,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Scenario replanning failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc