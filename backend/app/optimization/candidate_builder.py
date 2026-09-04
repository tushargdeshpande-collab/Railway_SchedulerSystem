"""
Builds feasible task-to-block assignment candidates.

Only valid assignments are passed to the OR-Tools optimizer,
which keeps the model smaller and easier to explain.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    SYNTHETIC_DATA_DISCLAIMER,
)
from backend.app.schemas.domain import (
    BlockWindow,
    MaintenanceTask,
    TrafficLevel,
)


BASE_DATA_PATH = Path("synthetic_data/generated/base")
MAX_CANDIDATES_PER_TASK = 60

TRAFFIC_COST = {
    TrafficLevel.LOW: 0,
    TrafficLevel.MEDIUM: 1,
    TrafficLevel.HIGH: 3,
    TrafficLevel.PEAK: 6,
}


def load_json(
    filename: str,
) -> list[dict[str, Any]]:
    path = BASE_DATA_PATH / filename

    with path.open("r", encoding="utf-8") as input_file:
        return json.load(input_file)


def load_tasks() -> list[MaintenanceTask]:
    records = load_json(
        "scored_maintenance_tasks.json"
    )

    return [
        MaintenanceTask.model_validate(record)
        for record in records
    ]


def load_blocks() -> list[BlockWindow]:
    records = load_json("block_windows.json")

    return [
        BlockWindow.model_validate(record)
        for record in records
    ]


def preferred_time_penalty(
    task: MaintenanceTask,
    block: BlockWindow,
) -> int:
    if (
        task.preferred_start_time is None
        or task.preferred_end_time is None
    ):
        return 0

    block_start_time = block.start_time.time()
    block_end_time = block.end_time.time()

    overlaps_preference = (
        block_start_time < task.preferred_end_time
        and block_end_time > task.preferred_start_time
    )

    return 0 if overlaps_preference else 2


def get_infeasibility_reasons(
    task: MaintenanceTask,
    block: BlockWindow,
) -> list[str]:
    reasons = []

    if task.corridor_id != block.corridor_id:
        reasons.append("corridor mismatch")

    if task.section_id != block.section_id:
        reasons.append("section mismatch")

    if (
        task.minimum_block_minutes
        > block.available_duration_minutes
    ):
        reasons.append("insufficient block duration")

    if task.department not in block.permitted_departments:
        reasons.append("department not permitted")

    if (
        task.disconnection_type
        not in block.supported_disconnection_types
    ):
        reasons.append(
            "required disconnection unavailable"
        )

    if task.required_team not in block.available_teams:
        reasons.append("required team unavailable")

    missing_equipment = [
        equipment
        for equipment in task.required_equipment
        if equipment not in block.available_equipment
    ]

    if missing_equipment:
        reasons.append("required equipment unavailable")

    if block.start_time.date() < task.detection_date:
        reasons.append("block occurs before defect detection")

    return reasons


def is_feasible(
    task: MaintenanceTask,
    block: BlockWindow,
) -> bool:
    return not get_infeasibility_reasons(
        task,
        block,
    )


def candidate_sort_key(
    task: MaintenanceTask,
    block: BlockWindow,
) -> tuple:
    overdue_delay = 0

    if block.start_time.date() > task.due_date:
        overdue_delay = (
            block.start_time.date() - task.due_date
        ).days

    return (
        TRAFFIC_COST[block.traffic_level],
        overdue_delay,
        preferred_time_penalty(task, block),
        block.start_time,
        -block.available_duration_minutes,
    )


def build_candidates(
    tasks: list[MaintenanceTask],
    blocks: list[BlockWindow],
) -> dict[str, list[str]]:
    blocks_by_section: dict[str, list[BlockWindow]] = {}

    for block in blocks:
        blocks_by_section.setdefault(
            block.section_id,
            [],
        ).append(block)

    candidate_map: dict[str, list[str]] = {}

    for task in tasks:
        section_blocks = blocks_by_section.get(
            task.section_id,
            [],
        )

        feasible_blocks = [
            block
            for block in section_blocks
            if is_feasible(task, block)
        ]

        feasible_blocks.sort(
            key=lambda block: candidate_sort_key(
                task,
                block,
            )
        )

        candidate_map[task.task_id] = [
            block.block_id
            for block in feasible_blocks[
                :MAX_CANDIDATES_PER_TASK
            ]
        ]

    return candidate_map


def collect_rejection_reasons(
    tasks: list[MaintenanceTask],
    blocks: list[BlockWindow],
) -> Counter:
    rejection_counts = Counter()

    blocks_by_section: dict[str, list[BlockWindow]] = {}

    for block in blocks:
        blocks_by_section.setdefault(
            block.section_id,
            [],
        ).append(block)

    for task in tasks:
        section_blocks = blocks_by_section.get(
            task.section_id,
            [],
        )

        for block in section_blocks:
            for reason in get_infeasibility_reasons(
                task,
                block,
            ):
                rejection_counts[reason] += 1

    return rejection_counts


def save_candidate_report(
    tasks: list[MaintenanceTask],
    blocks: list[BlockWindow],
    candidate_map: dict[str, list[str]],
    rejection_counts: Counter,
) -> dict[str, Any]:
    candidate_counts = [
        len(block_ids)
        for block_ids in candidate_map.values()
    ]

    tasks_without_candidates = [
        task_id
        for task_id, block_ids in candidate_map.items()
        if not block_ids
    ]

    report = {
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
        "generated_at": datetime.now().isoformat(),
        "task_count": len(tasks),
        "block_count": len(blocks),
        "maximum_candidates_per_task": (
            MAX_CANDIDATES_PER_TASK
        ),
        "total_candidate_assignments": sum(
            candidate_counts
        ),
        "minimum_candidates_for_a_task": min(
            candidate_counts
        ),
        "maximum_candidates_for_a_task": max(
            candidate_counts
        ),
        "average_candidates_per_task": round(
            sum(candidate_counts)
            / len(candidate_counts),
            2,
        ),
        "tasks_without_candidates": (
            tasks_without_candidates
        ),
        "rejection_reason_counts": dict(
            rejection_counts
        ),
        "candidate_map": candidate_map,
    }

    report_path = (
        BASE_DATA_PATH / "candidate_report.json"
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as report_file:
        json.dump(report, report_file, indent=2)

    return report


def print_report(
    report: dict[str, Any],
) -> None:
    print(SYNTHETIC_DATA_DISCLAIMER)
    print(f"Tasks evaluated: {report['task_count']}")
    print(f"Blocks evaluated: {report['block_count']}")
    print(
        "Feasible candidate assignments: "
        f"{report['total_candidate_assignments']}"
    )
    print(
        "Average candidates per task: "
        f"{report['average_candidates_per_task']}"
    )
    print(
        "Minimum candidates for a task: "
        f"{report['minimum_candidates_for_a_task']}"
    )
    print(
        "Tasks without candidates: "
        f"{len(report['tasks_without_candidates'])}"
    )

    print("Main rejection reasons:")

    sorted_rejections = sorted(
        report["rejection_reason_counts"].items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for reason, count in sorted_rejections:
        print(f"  {reason}: {count}")

    print(
        "Report saved to: "
        f"{BASE_DATA_PATH / 'candidate_report.json'}"
    )


if __name__ == "__main__":
    maintenance_tasks = load_tasks()
    block_windows = load_blocks()

    candidates = build_candidates(
        maintenance_tasks,
        block_windows,
    )

    rejection_reasons = collect_rejection_reasons(
        maintenance_tasks,
        block_windows,
    )

    candidate_report = save_candidate_report(
        maintenance_tasks,
        block_windows,
        candidates,
        rejection_reasons,
    )

    print_report(candidate_report)

    if candidate_report["tasks_without_candidates"]:
        raise SystemExit(
            "Some maintenance tasks have no feasible block candidates"
        )