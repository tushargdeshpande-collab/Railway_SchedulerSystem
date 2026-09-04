"""
Generates synthetic goods-train forecasts for every railway section
over the 30-day planning period.

This is fictional demonstration data.
"""

import csv
import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.app.data.master_data import (
    SECTIONS,
    SYNTHETIC_DATA_DISCLAIMER,
    validate_master_data,
)
from backend.app.schemas.domain import GoodsTrainForecast


RANDOM_SEED = 126
START_DATE = date(2026, 9, 1)
PLANNING_DAYS = 30

FORECAST_WINDOWS = [
    (0, 6),
    (6, 12),
    (12, 18),
    (18, 24),
]


def window_datetime(
    forecast_date: date,
    hour_value: int,
) -> datetime:
    if hour_value == 24:
        return datetime.combine(
            forecast_date + timedelta(days=1),
            time.min,
        )

    return datetime.combine(
        forecast_date,
        time(hour=hour_value),
    )


def generate_goods_forecasts(
    start_date: date = START_DATE,
    planning_days: int = PLANNING_DAYS,
    seed: int = RANDOM_SEED,
) -> list[GoodsTrainForecast]:
    validate_master_data()
    rng = random.Random(seed)

    forecasts: list[GoodsTrainForecast] = []
    forecast_number = 1

    for day_offset in range(planning_days):
        forecast_date = start_date + timedelta(days=day_offset)

        for section in SECTIONS:
            is_freight_corridor = (
                section["corridor_id"] == "COR-05"
            )

            for start_hour, end_hour in FORECAST_WINDOWS:
                if is_freight_corridor:
                    expected_count = rng.randint(3, 7)
                else:
                    expected_count = rng.randint(0, 4)

                uncertainty = rng.choice([1, 1, 2])

                lower_bound = max(
                    0,
                    expected_count - uncertainty,
                )
                upper_bound = expected_count + uncertainty

                average_occupancy = rng.randint(18, 28)
                expected_occupancy = (
                    expected_count * average_occupancy
                )

                confidence = round(
                    rng.uniform(0.72, 0.94),
                    2,
                )

                forecast = GoodsTrainForecast(
                    forecast_id=(
                        f"FORECAST-{forecast_number:06d}"
                    ),
                    corridor_id=section["corridor_id"],
                    section_id=section["section_id"],
                    forecast_date=forecast_date,
                    window_start=window_datetime(
                        forecast_date,
                        start_hour,
                    ),
                    window_end=window_datetime(
                        forecast_date,
                        end_hour,
                    ),
                    expected_train_count=expected_count,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    confidence=confidence,
                    expected_occupancy_minutes=(
                        expected_occupancy
                    ),
                )

                forecasts.append(forecast)
                forecast_number += 1

    return forecasts


def serialise_forecast(
    forecast: GoodsTrainForecast,
) -> dict[str, Any]:
    return forecast.model_dump(mode="json")


def save_forecasts(
    forecasts: list[GoodsTrainForecast],
    output_directory: Path,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    records = [
        serialise_forecast(forecast)
        for forecast in forecasts
    ]

    json_path = output_directory / "goods_forecasts.json"
    csv_path = output_directory / "goods_forecasts.csv"
    metadata_path = output_directory / "goods_forecast_metadata.json"

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=2)

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=records[0].keys(),
        )
        writer.writeheader()
        writer.writerows(records)

    metadata = {
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
        "random_seed": RANDOM_SEED,
        "planning_start": START_DATE.isoformat(),
        "planning_days": PLANNING_DAYS,
        "forecast_windows_per_day": len(FORECAST_WINDOWS),
        "record_count": len(forecasts),
    }

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(metadata, metadata_file, indent=2)


def print_summary(
    forecasts: list[GoodsTrainForecast],
) -> None:
    print(SYNTHETIC_DATA_DISCLAIMER)
    print(f"Goods forecasts generated: {len(forecasts)}")
    print(f"Planning period: {PLANNING_DAYS} days")

    total_expected_trains = sum(
        forecast.expected_train_count
        for forecast in forecasts
    )

    freight_corridor_trains = sum(
        forecast.expected_train_count
        for forecast in forecasts
        if forecast.corridor_id == "COR-05"
    )

    average_confidence = sum(
        forecast.confidence
        for forecast in forecasts
    ) / len(forecasts)

    print(
        "Total forecast goods movements: "
        f"{total_expected_trains}"
    )
    print(
        "Forecast movements on freight corridor: "
        f"{freight_corridor_trains}"
    )
    print(
        f"Average forecast confidence: "
        f"{average_confidence:.2%}"
    )


if __name__ == "__main__":
    generated_forecasts = generate_goods_forecasts()

    output_path = Path(
        "synthetic_data/generated/base"
    )

    save_forecasts(
        generated_forecasts,
        output_path,
    )

    print_summary(generated_forecasts)
    print(f"Files saved to: {output_path.resolve()}")