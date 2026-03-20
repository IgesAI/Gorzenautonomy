"""NIIRS task-level interpretation lookup table.

Maps NIIRS rating (0-9) to the identification tasks achievable at
each level, per NGA/IRARS criteria.

References:
- Imagery Resolution Assessments and Reporting Standards (IRARS) Committee
- NGA Standard 0018, "National Imagery Interpretability Rating Scale"
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NIIRSLevel:
    """Description and capabilities for a NIIRS rating level."""
    level: int
    category: str
    description: str
    tasks: list[str]
    min_gsd_cm: float  # approximate GSD threshold
    typical_altitude_m: float  # typical drone altitude to achieve


NIIRS_TABLE: list[NIIRSLevel] = [
    NIIRSLevel(
        level=0, category="Unusable",
        description="Interpretability precluded by obscuration, degradation, or very poor resolution",
        tasks=["No useful information extractable"],
        min_gsd_cm=999.0, typical_altitude_m=999.0,
    ),
    NIIRSLevel(
        level=1, category="Very Poor",
        description="Detect large area installations (airports, harbors)",
        tasks=[
            "Detect large area land use (urban vs rural)",
            "Detect coastline and major water bodies",
        ],
        min_gsd_cm=900.0, typical_altitude_m=500.0,
    ),
    NIIRSLevel(
        level=2, category="Poor",
        description="Detect large buildings, highway patterns",
        tasks=[
            "Detect large buildings (hospitals, factories)",
            "Identify road/highway patterns",
            "Detect large aircraft at airfields",
        ],
        min_gsd_cm=450.0, typical_altitude_m=400.0,
    ),
    NIIRSLevel(
        level=3, category="Fair",
        description="Identify large facility types, count large structures",
        tasks=[
            "Identify large facility types (power plants, stadiums)",
            "Detect individual rail cars",
            "Detect medium-sized vehicles in open areas",
        ],
        min_gsd_cm=200.0, typical_altitude_m=300.0,
    ),
    NIIRSLevel(
        level=4, category="Moderate",
        description="Identify individual buildings, count vehicles",
        tasks=[
            "Identify individual buildings within a complex",
            "Count vehicles in parking areas",
            "Detect small boats at piers",
            "Identify tree types (deciduous vs coniferous)",
        ],
        min_gsd_cm=100.0, typical_altitude_m=200.0,
    ),
    NIIRSLevel(
        level=5, category="Good",
        description="Identify vehicle types, distinguish equipment",
        tasks=[
            "Identify automobiles as sedans or trucks",
            "Identify rail cars by type (flat, box, tanker)",
            "Detect antenna dishes on rooftops",
            "Identify individual utility poles",
        ],
        min_gsd_cm=40.0, typical_altitude_m=120.0,
    ),
    NIIRSLevel(
        level=6, category="Very Good",
        description="Identify make/model of vehicles, read large signs",
        tasks=[
            "Identify vehicle make and model",
            "Identify personnel and distinguish from objects",
            "Read large signs and billboards",
            "Identify equipment components (e.g., solar panels)",
            "Detect cracks in pavement or structures",
        ],
        min_gsd_cm=15.0, typical_altitude_m=60.0,
    ),
    NIIRSLevel(
        level=7, category="Excellent",
        description="Identify small objects, read license plates",
        tasks=[
            "Identify specific vehicle license plates",
            "Identify individual facial features at close range",
            "Read small signs and placards",
            "Detect wire/cable runs between poles",
            "Identify bolt patterns on structures",
        ],
        min_gsd_cm=6.0, typical_altitude_m=25.0,
    ),
    NIIRSLevel(
        level=8, category="Outstanding",
        description="Identify small hardware, read fine text",
        tasks=[
            "Identify small hardware on equipment (hinges, latches)",
            "Detect individual rivets on structures",
            "Read serial numbers on equipment",
            "Identify insulator types on power lines",
        ],
        min_gsd_cm=2.5, typical_altitude_m=12.0,
    ),
    NIIRSLevel(
        level=9, category="Exceptional",
        description="Identify sub-centimeter features, thread patterns",
        tasks=[
            "Identify wire gauge and connector types",
            "Read fine print and labels",
            "Detect hairline cracks in materials",
            "Identify corrosion patterns and surface defects",
        ],
        min_gsd_cm=1.0, typical_altitude_m=5.0,
    ),
]


def get_niirs_level(niirs: float) -> NIIRSLevel:
    """Get the NIIRS level description for a given rating."""
    level = max(0, min(9, int(niirs)))
    return NIIRS_TABLE[level]


def get_achievable_tasks(niirs: float) -> list[str]:
    """Get all tasks achievable at the given NIIRS level and below."""
    level = max(0, min(9, int(niirs)))
    tasks: list[str] = []
    for entry in NIIRS_TABLE[:level + 1]:
        tasks.extend(entry.tasks)
    return tasks


def get_niirs_for_task(task_keyword: str) -> int | None:
    """Find the minimum NIIRS level needed for a task containing the keyword."""
    task_keyword = task_keyword.lower()
    for entry in NIIRS_TABLE:
        for task in entry.tasks:
            if task_keyword in task.lower():
                return entry.level
    return None


def get_all_levels_summary() -> list[dict]:
    """Return all NIIRS levels as serializable dicts for the API."""
    return [
        {
            "level": n.level,
            "category": n.category,
            "description": n.description,
            "tasks": n.tasks,
            "min_gsd_cm": n.min_gsd_cm,
            "typical_altitude_m": n.typical_altitude_m,
        }
        for n in NIIRS_TABLE
    ]
