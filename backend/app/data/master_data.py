"""
Synthetic railway master data for the SIH demonstration prototype.

All corridor, section, station, team, equipment and asset information
in this file is fictional and must not be treated as official Indian
Railways operational data.
"""

SYNTHETIC_DATA_DISCLAIMER = (
    "Synthetic Demonstration Data - "
    "Not an official Indian Railways operational dataset."
)


CORRIDORS = [
    {
        "corridor_id": "COR-01",
        "corridor_name": "Gati Northern Corridor",
        "route_code": "GNC",
        "importance": 5,
        "tracks": ["GNC-UP", "GNC-DOWN"],
    },
    {
        "corridor_id": "COR-02",
        "corridor_name": "Gati Eastern Corridor",
        "route_code": "GEC",
        "importance": 4,
        "tracks": ["GEC-UP", "GEC-DOWN"],
    },
    {
        "corridor_id": "COR-03",
        "corridor_name": "Gati Southern Corridor",
        "route_code": "GSC",
        "importance": 4,
        "tracks": ["GSC-UP", "GSC-DOWN"],
    },
    {
        "corridor_id": "COR-04",
        "corridor_name": "Gati Western Corridor",
        "route_code": "GWC",
        "importance": 3,
        "tracks": ["GWC-UP", "GWC-DOWN"],
    },
    {
        "corridor_id": "COR-05",
        "corridor_name": "Gati Freight Corridor",
        "route_code": "GFC",
        "importance": 5,
        "tracks": ["GFC-UP", "GFC-DOWN"],
    },
]


SECTIONS = [
    {
        "section_id": "SEC-01",
        "corridor_id": "COR-01",
        "section_name": "Navgati-Kiranpur",
        "start_station": "Navgati",
        "end_station": "Kiranpur",
        "start_km": 0.0,
        "end_km": 18.0,
    },
    {
        "section_id": "SEC-02",
        "corridor_id": "COR-01",
        "section_name": "Kiranpur-Udaynagar",
        "start_station": "Kiranpur",
        "end_station": "Udaynagar",
        "start_km": 18.0,
        "end_km": 36.5,
    },
    {
        "section_id": "SEC-03",
        "corridor_id": "COR-01",
        "section_name": "Udaynagar-Pragati",
        "start_station": "Udaynagar",
        "end_station": "Pragati",
        "start_km": 36.5,
        "end_km": 55.0,
    },
    {
        "section_id": "SEC-04",
        "corridor_id": "COR-02",
        "section_name": "Aarambh-Tejas",
        "start_station": "Aarambh",
        "end_station": "Tejas",
        "start_km": 0.0,
        "end_km": 16.0,
    },
    {
        "section_id": "SEC-05",
        "corridor_id": "COR-02",
        "section_name": "Tejas-Sankalp",
        "start_station": "Tejas",
        "end_station": "Sankalp",
        "start_km": 16.0,
        "end_km": 34.0,
    },
    {
        "section_id": "SEC-06",
        "corridor_id": "COR-02",
        "section_name": "Sankalp-Nirman",
        "start_station": "Sankalp",
        "end_station": "Nirman",
        "start_km": 34.0,
        "end_km": 52.0,
    },
    {
        "section_id": "SEC-07",
        "corridor_id": "COR-03",
        "section_name": "Shakti-Vikas",
        "start_station": "Shakti",
        "end_station": "Vikas",
        "start_km": 0.0,
        "end_km": 20.0,
    },
    {
        "section_id": "SEC-08",
        "corridor_id": "COR-03",
        "section_name": "Vikas-Sahyog",
        "start_station": "Vikas",
        "end_station": "Sahyog",
        "start_km": 20.0,
        "end_km": 39.5,
    },
    {
        "section_id": "SEC-09",
        "corridor_id": "COR-03",
        "section_name": "Sahyog-Unnati",
        "start_station": "Sahyog",
        "end_station": "Unnati",
        "start_km": 39.5,
        "end_km": 61.0,
    },
    {
        "section_id": "SEC-10",
        "corridor_id": "COR-04",
        "section_name": "Nishant-Dhara",
        "start_station": "Nishant",
        "end_station": "Dhara",
        "start_km": 0.0,
        "end_km": 14.5,
    },
    {
        "section_id": "SEC-11",
        "corridor_id": "COR-04",
        "section_name": "Dhara-Setu",
        "start_station": "Dhara",
        "end_station": "Setu",
        "start_km": 14.5,
        "end_km": 31.0,
    },
    {
        "section_id": "SEC-12",
        "corridor_id": "COR-04",
        "section_name": "Setu-Vistaar",
        "start_station": "Setu",
        "end_station": "Vistaar",
        "start_km": 31.0,
        "end_km": 49.0,
    },
    {
        "section_id": "SEC-13",
        "corridor_id": "COR-05",
        "section_name": "Udyog-Cargo Nagar",
        "start_station": "Udyog",
        "end_station": "Cargo Nagar",
        "start_km": 0.0,
        "end_km": 24.0,
    },
    {
        "section_id": "SEC-14",
        "corridor_id": "COR-05",
        "section_name": "Cargo Nagar-Vahanpur",
        "start_station": "Cargo Nagar",
        "end_station": "Vahanpur",
        "start_km": 24.0,
        "end_km": 47.0,
    },
    {
        "section_id": "SEC-15",
        "corridor_id": "COR-05",
        "section_name": "Vahanpur-Logistics Yard",
        "start_station": "Vahanpur",
        "end_station": "Logistics Yard",
        "start_km": 47.0,
        "end_km": 72.0,
    },
]


DEPARTMENT_CONFIG = {
    "Engineering": {
        "source_system": "TMS",
        "teams": [
            "ENG-Team-01",
            "ENG-Team-02",
            "ENG-Team-03",
        ],
        "equipment": [
            "Rail Grinder",
            "Inspection Trolley",
            "Tamping Machine",
            "Ultrasonic Rail Tester",
        ],
        "assets": [
            "Rail",
            "Points and Crossings",
            "Sleepers",
            "Ballast",
            "Bridge Component",
        ],
        "defects": [
            "Rail surface defect",
            "Track geometry deviation",
            "Worn crossing",
            "Damaged sleeper",
            "Insufficient ballast",
        ],
    },
    "Signal & Telecommunication": {
        "source_system": "SMMS",
        "teams": [
            "SNT-Team-01",
            "SNT-Team-02",
            "SNT-Team-03",
        ],
        "equipment": [
            "Signal Tester",
            "Cable Fault Locator",
            "Axle Counter Tester",
            "Track Circuit Meter",
        ],
        "assets": [
            "Signal",
            "Track Circuit",
            "Axle Counter",
            "Point Machine",
            "Communication Cable",
        ],
        "defects": [
            "Intermittent signal failure",
            "Track circuit instability",
            "Axle counter mismatch",
            "Point machine response delay",
            "Communication link degradation",
        ],
    },
    "Traction Distribution": {
        "source_system": "TDMS",
        "teams": [
            "TRD-Team-01",
            "TRD-Team-02",
            "TRD-Team-03",
        ],
        "equipment": [
            "OHE Inspection Vehicle",
            "Insulation Tester",
            "Contact Wire Gauge",
            "Tower Wagon",
        ],
        "assets": [
            "Overhead Equipment",
            "Contact Wire",
            "Insulator",
            "Feeder",
            "Sectioning Equipment",
        ],
        "defects": [
            "Contact wire wear",
            "Insulator degradation",
            "Feeder voltage anomaly",
            "OHE alignment deviation",
            "Sectioning equipment fault",
        ],
    },
}


def validate_master_data() -> None:
    corridor_ids = [item["corridor_id"] for item in CORRIDORS]
    section_ids = [item["section_id"] for item in SECTIONS]

    if len(corridor_ids) != len(set(corridor_ids)):
        raise ValueError("Duplicate corridor IDs found")

    if len(section_ids) != len(set(section_ids)):
        raise ValueError("Duplicate section IDs found")

    if len(CORRIDORS) != 5:
        raise ValueError("Expected exactly 5 synthetic corridors")

    if len(SECTIONS) != 15:
        raise ValueError("Expected exactly 15 synthetic sections")

    for section in SECTIONS:
        if section["corridor_id"] not in corridor_ids:
            raise ValueError(
                f"Unknown corridor in section {section['section_id']}"
            )

        if section["end_km"] <= section["start_km"]:
            raise ValueError(
                f"Invalid kilometre range in {section['section_id']}"
            )

    expected_departments = {
        "Engineering",
        "Signal & Telecommunication",
        "Traction Distribution",
    }

    if set(DEPARTMENT_CONFIG) != expected_departments:
        raise ValueError("Department configuration is incomplete")


if __name__ == "__main__":
    validate_master_data()

    print(SYNTHETIC_DATA_DISCLAIMER)
    print(f"Corridors: {len(CORRIDORS)}")
    print(f"Sections: {len(SECTIONS)}")
    print(f"Departments: {len(DEPARTMENT_CONFIG)}")
    print("Master data validation successful")