"""ODM-aligned GSD calculation.

Mirrors OpenDroneMap formula for consistency with ODM/PyODM workflows:
  GSD = (sensor_width × flight_height) / (focal_length × image_width)  [cm/px]
  focal_ratio = focal_length / sensor_width
  GSD = ((flight_height_m * 100) / image_width_px) / focal_ratio
"""

from __future__ import annotations


def calculate_gsd_odm(
    sensor_width_mm: float,
    flight_height_m: float,
    focal_length_mm: float,
    image_width_px: int | float,
) -> float | None:
    """Compute GSD in cm/px using ODM formula.

    Args:
        sensor_width_mm: Sensor physical width (mm)
        flight_height_m: Altitude above ground (m)
        focal_length_mm: Lens focal length (mm)
        image_width_px: Image width in pixels

    Returns:
        GSD in cm/px, or None if sensor_width_mm is 0
    """
    if sensor_width_mm == 0:
        return None
    focal_ratio = focal_length_mm / sensor_width_mm
    return ((flight_height_m * 100) / float(image_width_px)) / focal_ratio
