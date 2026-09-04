"""
Creates the original optimized Pune-Lonavala weekly maintenance plan
before the unexpected priority freight movement is introduced.
"""

import json
import time
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from backend.app.data.pune_lonavala_config import (
    SCENARIO_DISCLAIMER,
)
from backend.app.optimization.candidate_builder import (
    build_candidates,
)
from backend.app.optimization.scheduler import (
    build_outputs,
    solve_schedule,
)
from backend.app.schemas.domain import (
    BlockWindow,
    MaintenanceTask,
)


SCENARIO_PATH = Path(
    "synthetic_data/scenarios/pune_lonavala/base"
)


def load_json(filename: str) -> Any:
    path = SCENARIO_PATH / filename

    with path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        return json.load(input_file)


def load_inputs() -> tuple[
    list[MaintenanceTask],
    list[BlockWindow],
]:
    tasks = [
        MaintenanceTask.model_validate(record)
        for record in load_json(
            "scored_maintenance_tasks.json"
        )
    ]

    blocks = [
        BlockWindow.model_validate(record)
        for record in load_json(
            "block_windows.json"
        )
    ]

    return tasks, blocks


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


def save_candidate_report(
    candidate_map: dict[str, list[str]],
) -> None:
    candidate_counts = [
        len(block_ids)
        for block_ids in candidate_map.values()
    ]

    report = {
        "disclaimer": SCENARIO_DISCLAIMER,
        "task_count": len(candidate_map),
        "total_candidate_assignments": sum(
            candidate_counts
        ),
        "minimum_candidates_per_task": min(
            candidate_counts
        ),
        "maximum_candidates_per_task": max(
            candidate_counts
        ),
        "average_candidates_per_task": round(
            sum(candidate_counts)
            / len(candidate_counts),
            2,
        ),
        "tasks_without_candidates": [
            task_id
            for task_id, block_ids
            in candidate_map.items()
            if not block_ids
        ],
        "candidate_map": candidate_map,
    }

    save_json(
        "candidate_report.json",
        report,
    )


def print_summary(
    metrics: dict[str, Any],
    candidate_map: dict[str, list[str]],
) -> None:
    print(SCENARIO_DISCLAIMER)

    print(
        f"Route tasks evaluated: "
        f"{len(candidate_map)}"
    )

    print(
        "Feasible route assignments: "
        f"{sum(len(value) for value in candidate_map.values())}"
    )

    print(
        f"Solver status: "
        f"{metrics['solver_status']}"
    )

    print(
        f"Runtime: "
        f"{metrics['solver_runtime_seconds']} seconds"
    )

    print(
        f"Scheduled tasks: "
        f"{metrics['scheduled_tasks']}/"
        f"{metrics['total_tasks']}"
    )

    print(
        f"Critical tasks scheduled: "
        f"{metrics['critical_tasks_scheduled']}"
    )

    print(
        f"High-priority tasks scheduled: "
        f"{metrics['high_tasks_scheduled']}"
    )

    print(
        f"Blocks used: "
        f"{metrics['blocks_used']}"
    )

    print(
        f"Bundled blocks: "
        f"{metrics['bundled_blocks']}"
    )

    print(
        "Tasks coordinated in bundled blocks: "
        f"{metrics['tasks_in_bundled_blocks']}"
    )

    print(
        "Average block utilization: "
        f"{metrics['average_block_utilization_percent']}%"
    )

    print(
        "Estimated synthetic train impact: "
        f"{metrics['estimated_total_train_impact_minutes']} "
        "minutes"
    )

    print(
        f"Files saved to: "
        f"{SCENARIO_PATH.resolve()}"
    )


if __name__ == "__main__":
    (
        maintenance_tasks,
        block_windows,
    ) = load_inputs()

    candidates = build_candidates(
        maintenance_tasks,
        block_windows,
    )

    tasks_without_candidates = [
        task_id
        for task_id, block_ids
        in candidates.items()
        if not block_ids
    ]

    if tasks_without_candidates:
        raise SystemExit(
            "Tasks without feasible blocks: "
            f"{tasks_without_candidates}"
        )

    save_candidate_report(
        candidates
    )

    started_at = time.perf_counter()

    (
        solver,
        status,
        assignment_variables,
    ) = solve_schedule(
        maintenance_tasks,
        block_windows,
        candidates,
    )

    runtime = (
        time.perf_counter()
        - started_at
    )

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        raise SystemExit(
            "No feasible Pune-Lonavala plan found. "
            f"Status: {solver.status_name(status)}"
        )

    (
        optimized_schedule,
        unscheduled_tasks,
        optimization_metrics,
    ) = build_outputs(
        solver,
        status,
        maintenance_tasks,
        block_windows,
        candidates,
        assignment_variables,
        runtime,
    )

    optimization_metrics["disclaimer"] = (
        SCENARIO_DISCLAIMER
    )

    optimization_metrics["scenario"] = (
        "Original Pune-Lonavala weekly plan"
    )

    optimization_metrics[
        "priority_freight_event_included"
    ] = False

    save_json(
        "optimized_schedule.json",
        optimized_schedule,
    )

    save_json(
        "unscheduled_tasks.json",
        unscheduled_tasks,
    )

    save_json(
        "optimization_metrics.json",
        optimization_metrics,
    )

    print_summary(
        optimization_metrics,
        candidates,
    )