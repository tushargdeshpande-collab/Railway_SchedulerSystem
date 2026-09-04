"""
Explainable maintenance priority engine.

The priority score is deterministic, ranges from 0 to 100,
and does not rely on an LLM.
"""

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    DEPARTMENT_CONFIG,
    SYNTHETIC_DATA_DISCLAIMER,
)
from backend.app.schemas.domain import (
    MaintenanceTask,
    PriorityLevel,
)


BASE_DATA_PATH = Path("synthetic_data/generated/base")

WEIGHTS = {
    "safety_criticality": 22,
    "deadline_urgency": 16,
    "failure_probability": 16,
    "defect_severity": 14,
    "operational_impact": 12,
    "asset_importance": 8,
    "bundling_opportunity": 6,
    "resource_readiness": 6,
}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_scale_1_to_5(value: int) -> float:
    return clamp((value - 1) / 4)


def calculate_deadline_urgency(
    task: MaintenanceTask,
) -> float:
    if task.overdue_days > 0:
        return clamp(
            0.60 + task.overdue_days / 60
        )

    days_until_due = (
        task.due_date - task.detection_date
    ).days

    if days_until_due <= 7:
        return 0.80
    if days_until_due <= 14:
        return 0.60
    if days_until_due <= 30:
        return 0.35

    return 0.15


def calculate_bundling_opportunity(
    task: MaintenanceTask,
) -> float:
    return clamp(
        len(task.compatible_task_ids) / 3
    )


def calculate_resource_readiness(
    task: MaintenanceTask,
) -> float:
    department_config = DEPARTMENT_CONFIG.get(
        task.department.value
    )

    if not department_config:
        return 0.0

    team_available = (
        task.required_team
        in department_config["teams"]
    )

    known_equipment = set(
        department_config["equipment"]
    )

    if task.required_equipment:
        equipment_coverage = sum(
            equipment in known_equipment
            for equipment in task.required_equipment
        ) / len(task.required_equipment)
    else:
        equipment_coverage = 1.0

    return (
        float(team_available) * 0.60
        + equipment_coverage * 0.40
    )


def classify_priority(
    score: float,
) -> PriorityLevel:
    if score >= 80:
        return PriorityLevel.CRITICAL
    if score >= 65:
        return PriorityLevel.HIGH
    if score >= 45:
        return PriorityLevel.MEDIUM

    return PriorityLevel.LOW


def build_explanation(
    task: MaintenanceTask,
    score: float,
    level: PriorityLevel,
    components: dict[str, float],
) -> str:
    reasons = []

    if task.safety_criticality >= 5:
        reasons.append("it is safety-critical")
    elif task.safety_criticality >= 4:
        reasons.append("it has high safety criticality")

    if task.overdue_days > 0:
        reasons.append(
            f"it is {task.overdue_days} days overdue"
        )
    elif components["deadline_urgency"] >= 9:
        reasons.append("its maintenance deadline is close")

    if task.defect_severity >= 5:
        reasons.append("the defect severity is very high")
    elif task.defect_severity >= 4:
        reasons.append("the defect severity is high")

    if task.failure_probability >= 0.70:
        reasons.append(
            f"its estimated failure probability is "
            f"{task.failure_probability:.0%}"
        )

    if task.operational_impact >= 4:
        reasons.append(
            "it can materially affect railway operations"
        )

    compatible_count = len(
        task.compatible_task_ids
    )

    if compatible_count:
        reasons.append(
            f"it can potentially be bundled with "
            f"{compatible_count} cross-department task"
            f"{'s' if compatible_count != 1 else ''}"
        )

    if not reasons:
        reasons.append(
            "its combined risk and urgency factors "
            "require planned attention"
        )

    if len(reasons) == 1:
        reason_text = reasons[0]
    else:
        reason_text = (
            ", ".join(reasons[:-1])
            + ", and "
            + reasons[-1]
        )

    return (
        f"{task.task_id} received a priority score of "
        f"{score:.1f}/100 ({level.value}) because "
        f"{reason_text}."
    )


def score_task(
    task: MaintenanceTask,
) -> dict[str, Any]:
    normalized_factors = {
        "safety_criticality": (
            normalize_scale_1_to_5(
                task.safety_criticality
            )
        ),
        "deadline_urgency": (
            calculate_deadline_urgency(task)
        ),
        "failure_probability": (
            task.failure_probability
        ),
        "defect_severity": (
            normalize_scale_1_to_5(
                task.defect_severity
            )
        ),
        "operational_impact": (
            normalize_scale_1_to_5(
                task.operational_impact
            )
        ),
        "asset_importance": (
            normalize_scale_1_to_5(
                task.asset_importance
            )
        ),
        "bundling_opportunity": (
            calculate_bundling_opportunity(task)
        ),
        "resource_readiness": (
            calculate_resource_readiness(task)
        ),
    }

    components = {
        factor: round(
            normalized_factors[factor]
            * WEIGHTS[factor],
            2,
        )
        for factor in WEIGHTS
    }

    score = round(sum(components.values()), 2)
    level = classify_priority(score)

    task.priority_score = score
    task.priority_level = level

    explanation = build_explanation(
        task,
        score,
        level,
        components,
    )

    record = task.model_dump(mode="json")
    record["priority_breakdown"] = components
    record["priority_explanation"] = explanation

    return record


def load_tasks() -> list[MaintenanceTask]:
    path = BASE_DATA_PATH / "maintenance_tasks.json"

    with path.open("r", encoding="utf-8") as input_file:
        records = json.load(input_file)

    return [
        MaintenanceTask.model_validate(record)
        for record in records
    ]


def save_scored_tasks(
    scored_records: list[dict[str, Any]],
) -> None:
    json_path = (
        BASE_DATA_PATH
        / "scored_maintenance_tasks.json"
    )

    csv_path = (
        BASE_DATA_PATH
        / "scored_maintenance_tasks.csv"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as json_file:
        json.dump(
            scored_records,
            json_file,
            indent=2,
        )

    csv_records = []

    for record in scored_records:
        csv_record = record.copy()

        for field in [
            "required_equipment",
            "dependency_task_ids",
            "compatible_task_ids",
        ]:
            csv_record[field] = "|".join(
                csv_record[field]
            )

        csv_record["priority_breakdown"] = json.dumps(
            csv_record["priority_breakdown"]
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


def print_summary(
    scored_records: list[dict[str, Any]],
) -> None:
    priority_counts = Counter(
        record["priority_level"]
        for record in scored_records
    )

    print(SYNTHETIC_DATA_DISCLAIMER)
    print(
        f"Maintenance tasks scored: "
        f"{len(scored_records)}"
    )

    for level in PriorityLevel:
        print(
            f"{level.value}: "
            f"{priority_counts.get(level.value, 0)}"
        )

    average_score = sum(
        record["priority_score"]
        for record in scored_records
    ) / len(scored_records)

    print(f"Average priority score: {average_score:.2f}")

    highest_priority = sorted(
        scored_records,
        key=lambda item: item["priority_score"],
        reverse=True,
    )[:5]

    print("Top five priority tasks:")

    for record in highest_priority:
        print(
            f"  {record['task_id']}: "
            f"{record['priority_score']:.1f} "
            f"({record['priority_level']})"
        )
        print(
            f"    {record['priority_explanation']}"
        )


if __name__ == "__main__":
    tasks = load_tasks()

    scored_tasks = [
        score_task(task)
        for task in tasks
    ]

    save_scored_tasks(scored_tasks)
    print_summary(scored_tasks)

    print(
        "Scored files saved to: "
        f"{BASE_DATA_PATH.resolve()}"
    )