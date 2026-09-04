from datetime import date, datetime, time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------

class Department(str, Enum):
    ENGINEERING = "Engineering"
    SIGNAL_TELECOM = "Signal & Telecommunication"
    TRACTION_DISTRIBUTION = "Traction Distribution"


class SourceSystem(str, Enum):
    TMS = "TMS"
    SMMS = "SMMS"
    TDMS = "TDMS"


class PriorityLevel(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class TaskStatus(str, Enum):
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    APPROVED = "Approved"
    COMPLETED = "Completed"
    DEFERRED = "Deferred"
    CANCELLED = "Cancelled"


class TrainType(str, Enum):
    EXPRESS = "Express"
    PASSENGER = "Passenger"
    SUBURBAN = "Suburban"
    GOODS = "Goods"
    SPECIAL = "Special"


class DisconnectionType(str, Enum):
    NONE = "None"
    POWER = "Power"
    SIGNALLING = "Signalling"
    TRACK_POSSESSION = "Track Possession"
    POWER_AND_TRACK = "Power and Track"


class BlockStatus(str, Enum):
    AVAILABLE = "Available"
    PROPOSED = "Proposed"
    APPROVED = "Approved"
    LOCKED = "Locked"
    CANCELLED = "Cancelled"


class TrafficLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    PEAK = "Peak"


# ---------------------------------------------------------------------
# Maintenance task from synthetic TMS, SMMS or TDMS feeds
# ---------------------------------------------------------------------

class MaintenanceTask(BaseModel):
    task_id: str
    source_system: SourceSystem
    department: Department

    asset_id: str
    asset_type: str

    corridor_id: str
    section_id: str
    start_km: float = Field(ge=0)
    end_km: float = Field(gt=0)

    defect_type: str
    defect_severity: int = Field(ge=1, le=5)
    safety_criticality: int = Field(ge=1, le=5)
    failure_probability: float = Field(ge=0, le=1)
    asset_importance: int = Field(ge=1, le=5)
    operational_impact: int = Field(ge=1, le=5)

    detection_date: date
    due_date: date
    overdue_days: int = Field(default=0, ge=0)

    estimated_duration_minutes: int = Field(gt=0)
    minimum_block_minutes: int = Field(gt=0)

    disconnection_type: DisconnectionType

    required_team: str
    required_personnel: int = Field(gt=0)
    required_equipment: List[str] = Field(default_factory=list)

    preferred_start_time: Optional[time] = None
    preferred_end_time: Optional[time] = None

    dependency_task_ids: List[str] = Field(default_factory=list)
    compatible_task_ids: List[str] = Field(default_factory=list)

    weather_sensitive: bool = False
    status: TaskStatus = TaskStatus.PENDING

    priority_score: Optional[float] = Field(default=None, ge=0, le=100)
    priority_level: Optional[PriorityLevel] = None

    synthetic_data: bool = True

    @model_validator(mode="after")
    def validate_task(self):
        if self.end_km <= self.start_km:
            raise ValueError("end_km must be greater than start_km")

        if self.minimum_block_minutes < self.estimated_duration_minutes:
            raise ValueError(
                "minimum_block_minutes cannot be less than "
                "estimated_duration_minutes"
            )

        if self.due_date < self.detection_date:
            raise ValueError("due_date cannot be before detection_date")

        if self.task_id in self.dependency_task_ids:
            raise ValueError("a task cannot depend on itself")

        return self


# ---------------------------------------------------------------------
# Train timetable record
# ---------------------------------------------------------------------

class TrainMovement(BaseModel):
    movement_id: str
    train_id: str
    train_name: str
    train_type: TrainType

    corridor_id: str
    section_id: str

    operating_date: date
    scheduled_entry: datetime
    scheduled_exit: datetime

    priority: int = Field(ge=1, le=10)
    maximum_permissible_delay_minutes: int = Field(ge=0)

    synthetic_data: bool = True

    @model_validator(mode="after")
    def validate_movement(self):
        if self.scheduled_exit <= self.scheduled_entry:
            raise ValueError(
                "scheduled_exit must be after scheduled_entry"
            )

        if self.scheduled_entry.date() != self.operating_date:
            raise ValueError(
                "scheduled_entry date must match operating_date"
            )

        return self


# ---------------------------------------------------------------------
# Synthetic goods-train forecast
# ---------------------------------------------------------------------

class GoodsTrainForecast(BaseModel):
    forecast_id: str
    corridor_id: str
    section_id: str

    forecast_date: date
    window_start: datetime
    window_end: datetime

    expected_train_count: int = Field(ge=0)
    lower_bound: int = Field(ge=0)
    upper_bound: int = Field(ge=0)

    confidence: float = Field(ge=0, le=1)
    expected_occupancy_minutes: int = Field(ge=0)

    synthetic_data: bool = True

    @model_validator(mode="after")
    def validate_forecast(self):
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")

        if not (
            self.lower_bound
            <= self.expected_train_count
            <= self.upper_bound
        ):
            raise ValueError(
                "expected_train_count must fall between bounds"
            )

        return self


# ---------------------------------------------------------------------
# Corridor block availability from synthetic COA/BDMS feeds
# ---------------------------------------------------------------------

class BlockWindow(BaseModel):
    block_id: str
    corridor_id: str
    section_id: str
    track_id: str

    start_time: datetime
    end_time: datetime
    available_duration_minutes: int = Field(gt=0)

    traffic_level: TrafficLevel
    permitted_departments: List[Department]

    disconnection_available: bool
    supported_disconnection_types: List[DisconnectionType] = Field(
        default_factory=list
    )

    available_teams: List[str] = Field(default_factory=list)
    available_equipment: List[str] = Field(default_factory=list)

    status: BlockStatus = BlockStatus.AVAILABLE
    synthetic_data: bool = True

    @model_validator(mode="after")
    def validate_block(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")

        calculated_minutes = int(
            (self.end_time - self.start_time).total_seconds() / 60
        )

        if calculated_minutes != self.available_duration_minutes:
            raise ValueError(
                "available_duration_minutes does not match "
                "start_time and end_time"
            )

        if not self.permitted_departments:
            raise ValueError(
                "at least one department must be permitted"
            )

        return self


# ---------------------------------------------------------------------
# Resource availability
# ---------------------------------------------------------------------

class ResourceAvailability(BaseModel):
    resource_id: str
    resource_type: str
    resource_name: str
    department: Department

    available_from: datetime
    available_until: datetime
    corridor_ids: List[str]

    capacity: int = Field(default=1, gt=0)
    synthetic_data: bool = True

    @model_validator(mode="after")
    def validate_resource(self):
        if self.available_until <= self.available_from:
            raise ValueError(
                "available_until must be after available_from"
            )

        if not self.corridor_ids:
            raise ValueError(
                "resource must be assigned to at least one corridor"
            )

        return self


# ---------------------------------------------------------------------
# Optimizer output
# ---------------------------------------------------------------------

class ScheduledBlock(BaseModel):
    schedule_id: str
    block_id: str

    corridor_id: str
    section_id: str
    track_id: str

    scheduled_start: datetime
    scheduled_end: datetime

    task_ids: List[str]
    departments: List[Department]

    utilization_percent: float = Field(ge=0, le=100)
    estimated_train_impact_minutes: float = Field(ge=0)

    is_bundled: bool
    is_locked: bool = False
    status: BlockStatus = BlockStatus.PROPOSED

    explanation: str
    synthetic_data: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError(
                "scheduled_end must be after scheduled_start"
            )

        if not self.task_ids:
            raise ValueError(
                "a scheduled block must contain at least one task"
            )

        if not self.departments:
            raise ValueError(
                "a scheduled block must contain at least one department"
            )

        if self.is_bundled and len(set(self.departments)) < 2:
            raise ValueError(
                "a bundled block must involve at least two departments"
            )

        return self

