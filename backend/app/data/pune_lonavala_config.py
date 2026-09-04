"""
Focused Pune-Lonavala SIH demonstration scenario.

Station names represent selected planning nodes on the corridor.
All train counts, timings, chainages, defects and operational
records are synthetic demonstration data.
"""

from datetime import date, datetime


SCENARIO_NAME = "Pune-Lonavala Dynamic Block Planning"

SCENARIO_DISCLAIMER = (
    "Synthetic Demonstration Data - Station names are used "
    "only to demonstrate the planning workflow. Train timings, "
    "counts, chainages, maintenance tasks and forecasts are not "
    "official Indian Railways operational data."
)

CORRIDOR = {
    "corridor_id": "PL-COR-01",
    "corridor_name": "Pune-Lonavala Demonstration Corridor",
    "route_code": "PLD",
    "tracks": ["PL-UP", "PL-DOWN"],
    "importance": 5,
}

PLANNING_NODES = [
    {
        "station_id": "PL-ST-01",
        "station_name": "Pune",
        "synthetic_km": 0.0,
    },
    {
        "station_id": "PL-ST-02",
        "station_name": "Shivajinagar",
        "synthetic_km": 5.0,
    },
    {
        "station_id": "PL-ST-03",
        "station_name": "Khadki",
        "synthetic_km": 10.0,
    },
    {
        "station_id": "PL-ST-04",
        "station_name": "Pimpri",
        "synthetic_km": 18.0,
    },
    {
        "station_id": "PL-ST-05",
        "station_name": "Chinchwad",
        "synthetic_km": 23.0,
    },
    {
        "station_id": "PL-ST-06",
        "station_name": "Akurdi",
        "synthetic_km": 28.0,
    },
    {
        "station_id": "PL-ST-07",
        "station_name": "Dehu Road",
        "synthetic_km": 36.0,
    },
    {
        "station_id": "PL-ST-08",
        "station_name": "Talegaon",
        "synthetic_km": 49.0,
    },
    {
        "station_id": "PL-ST-09",
        "station_name": "Lonavala",
        "synthetic_km": 64.0,
    },
]


def build_sections() -> list[dict]:
    sections = []

    for index in range(
        len(PLANNING_NODES) - 1
    ):
        start = PLANNING_NODES[index]
        end = PLANNING_NODES[index + 1]

        sections.append(
            {
                "section_id": f"PL-SEC-{index + 1:02d}",
                "corridor_id": CORRIDOR["corridor_id"],
                "section_name": (
                    f"{start['station_name']}-"
                    f"{end['station_name']}"
                ),
                "start_station": start["station_name"],
                "end_station": end["station_name"],
                "start_km": start["synthetic_km"],
                "end_km": end["synthetic_km"],
            }
        )

    return sections


SECTIONS = build_sections()

SYNTHETIC_DAILY_SERVICE_COUNTS = {
    "Suburban": 20,
    "Express": 6,
    "Passenger": 4,
    "Goods": 6,
}

SYNTHETIC_TOTAL_DAILY_SERVICES = sum(
    SYNTHETIC_DAILY_SERVICE_COUNTS.values()
)

WEEKLY_PLANNING_START = date(2026, 9, 1)
WEEKLY_PLANNING_DAYS = 7
MONTHLY_PLANNING_DAYS = 30

PRIORITY_FREIGHT_EVENT = {
    "event_id": "PL-EVENT-001",
    "event_type": "Priority Perishable Goods Movement",
    "train_id": "PL-PRF-001",
    "description": (
        "An additional time-sensitive synthetic goods train "
        "carrying perishable cargo requires corridor access."
    ),
    "operating_date": date(2026, 9, 4),
"corridor_entry": datetime(2026, 9, 4, 1, 20),
"corridor_exit": datetime(2026, 9, 4, 3, 15),
    "direction": "Pune to Lonavala",
    "priority": 10,
    "maximum_permissible_delay_minutes": 0,
    "synthetic_data": True,
}


def validate_configuration() -> None:
    if len(PLANNING_NODES) != 9:
        raise ValueError(
            "Expected nine selected planning nodes"
        )

    if len(SECTIONS) != 8:
        raise ValueError(
            "Expected eight corridor sections"
        )

    section_ids = [
        section["section_id"]
        for section in SECTIONS
    ]

    if len(section_ids) != len(set(section_ids)):
        raise ValueError(
            "Duplicate section identifiers found"
        )

    for section in SECTIONS:
        if (
            section["end_km"]
            <= section["start_km"]
        ):
            raise ValueError(
                f"Invalid synthetic chainage in "
                f"{section['section_id']}"
            )

    if SYNTHETIC_TOTAL_DAILY_SERVICES != 36:
        raise ValueError(
            "Expected 36 synthetic daily services"
        )

    if (
        PRIORITY_FREIGHT_EVENT[
            "corridor_exit"
        ]
        <= PRIORITY_FREIGHT_EVENT[
            "corridor_entry"
        ]
    ):
        raise ValueError(
            "Priority freight exit must be after entry"
        )


if __name__ == "__main__":
    validate_configuration()

    print(SCENARIO_DISCLAIMER)
    print(
        f"Scenario: {SCENARIO_NAME}"
    )
    print(
        f"Selected planning nodes: "
        f"{len(PLANNING_NODES)}"
    )
    print(
        f"Corridor sections: {len(SECTIONS)}"
    )
    print(
        "Synthetic daily services: "
        f"{SYNTHETIC_TOTAL_DAILY_SERVICES}"
    )
    print(
        "Disruption event: "
        f"{PRIORITY_FREIGHT_EVENT['event_type']}"
    )
    print(
        "Pune-Lonavala scenario configuration valid"
    )