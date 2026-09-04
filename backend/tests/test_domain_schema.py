from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.schemas.domain import (
    BlockWindow,
    Department,
    DisconnectionType,
    MaintenanceTask,
    SourceSystem,
    TrafficLevel,
    TrainMovement,
    TrainType,
)


def sample_task() -> MaintenanceTask:
    return MaintenanceTask(
        task_id="TASK-0001",
        source_system=SourceSystem.TMS,
        department=Department.ENGINEERING,
        asset_id="ASSET-001",
        asset_type="Rail",
        corridor_id="COR-01",
        section_id="SEC-01",
        start_km=10.0,
        end_km=12.0,
        defect_type="Rail surface defect",
        defect_severity=4,
        safety_criticality=5,
        failure_probability=0.72,
        asset_importance=5,
        operational_impact=4,
        detection_date=date(2026, 8, 1),
        due_date=date(2026, 8, 10),
        overdue_days=17,
        estimated_duration_minutes=90,
        minimum_block_minutes=120,
        disconnection_type=DisconnectionType.TRACK_POSSESSION,
        required_team="Engineering-Team-01",
        required_personnel=6,
        required_equipment=["Inspection Trolley", "Rail Grinder"],
    )


def test_valid_maintenance_task():
    task = sample_task()

    assert task.task_id == "TASK-0001"
    assert task.synthetic_data is True
    assert task.department == Department.ENGINEERING


def test_end_km_must_be_greater_than_start_km():
    task_data = sample_task().model_dump()
    task_data["end_km"] = 8.0

    with pytest.raises(ValidationError):
        MaintenanceTask(**task_data)


def test_block_cannot_be_shorter_than_task_duration():
    task_data = sample_task().model_dump()
    task_data["minimum_block_minutes"] = 60

    with pytest.raises(ValidationError):
        MaintenanceTask(**task_data)


def test_probability_must_be_between_zero_and_one():
    task_data = sample_task().model_dump()
    task_data["failure_probability"] = 1.5

    with pytest.raises(ValidationError):
        MaintenanceTask(**task_data)


def test_valid_train_movement():
    entry = datetime(2026, 8, 28, 10, 0)
    exit_time = entry + timedelta(minutes=20)

    movement = TrainMovement(
        movement_id="MOVE-0001",
        train_id="TRAIN-001",
        train_name="Synthetic Express 001",
        train_type=TrainType.EXPRESS,
        corridor_id="COR-01",
        section_id="SEC-01",
        operating_date=entry.date(),
        scheduled_entry=entry,
        scheduled_exit=exit_time,
        priority=9,
        maximum_permissible_delay_minutes=5,
    )

    assert movement.scheduled_exit > movement.scheduled_entry
    assert movement.synthetic_data is True


def test_invalid_train_time_order():
    entry = datetime(2026, 8, 28, 10, 0)

    with pytest.raises(ValidationError):
        TrainMovement(
            movement_id="MOVE-0002",
            train_id="TRAIN-002",
            train_name="Synthetic Passenger 002",
            train_type=TrainType.PASSENGER,
            corridor_id="COR-01",
            section_id="SEC-01",
            operating_date=entry.date(),
            scheduled_entry=entry,
            scheduled_exit=entry - timedelta(minutes=10),
            priority=5,
            maximum_permissible_delay_minutes=10,
        )


def test_valid_block_window():
    start = datetime(2026, 8, 28, 1, 0)
    end = start + timedelta(minutes=180)

    block = BlockWindow(
        block_id="BLOCK-0001",
        corridor_id="COR-01",
        section_id="SEC-01",
        track_id="TRACK-01",
        start_time=start,
        end_time=end,
        available_duration_minutes=180,
        traffic_level=TrafficLevel.LOW,
        permitted_departments=[
            Department.ENGINEERING,
            Department.SIGNAL_TELECOM,
        ],
        disconnection_available=True,
        supported_disconnection_types=[
            DisconnectionType.TRACK_POSSESSION,
            DisconnectionType.SIGNALLING,
        ],
        available_teams=[
            "Engineering-Team-01",
            "S&T-Team-01",
        ],
        available_equipment=[
            "Inspection Trolley",
            "Signal Tester",
        ],
    )

    assert block.available_duration_minutes == 180
    assert len(block.permitted_departments) == 2


def test_block_duration_must_match_timestamps():
    start = datetime(2026, 8, 28, 1, 0)
    end = start + timedelta(minutes=180)

    with pytest.raises(ValidationError):
        BlockWindow(
            block_id="BLOCK-0002",
            corridor_id="COR-01",
            section_id="SEC-01",
            track_id="TRACK-01",
            start_time=start,
            end_time=end,
            available_duration_minutes=120,
            traffic_level=TrafficLevel.LOW,
            permitted_departments=[Department.ENGINEERING],
            disconnection_available=True,
            supported_disconnection_types=[
                DisconnectionType.TRACK_POSSESSION
            ],
        )
