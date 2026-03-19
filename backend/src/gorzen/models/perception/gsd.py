"""GSD computation, altitude band, pixels-on-target, standoff distance.

ODM-aligned formula: GSD = (sensor_width × altitude) / (focal_length × image_width) [cm/px]
See gorzen.photogrammetry.gsd.calculate_gsd_odm for ODM reference implementation.
"""

from __future__ import annotations

import numpy as np

from gorzen.models.base import ModelOutput, SubsystemModel


class GSDModel(SubsystemModel):
    """Ground Sample Distance and related spatial resolution metrics.

    GSD = (sensor_width * altitude) / (focal_length * image_width_px)
    """

    def parameter_names(self) -> list[str]:
        return [
            "sensor_width_mm", "sensor_height_mm",
            "focal_length_mm", "pixel_width", "pixel_height",
        ]

    def state_names(self) -> list[str]:
        return []

    def output_names(self) -> list[str]:
        return [
            "gsd_h_cm_px", "gsd_w_cm_px", "gsd_cm_px",
            "footprint_w_m", "footprint_h_m",
            "pixels_on_target", "fov_h_deg", "fov_v_deg",
        ]

    def evaluate(self, params: dict[str, float], conditions: dict[str, float]) -> ModelOutput:
        sw_mm = params.get("sensor_width_mm", 13.2)
        sh_mm = params.get("sensor_height_mm", 8.8)
        fl_mm = params.get("focal_length_mm", 24.0)
        px_w = params.get("pixel_width", 4000)
        px_h = params.get("pixel_height", 3000)

        alt = conditions.get("altitude_m", 50.0)
        target_size_m = conditions.get("target_size_m", 1.0)

        # GSD along width and height dimensions
        gsd_w_m = (sw_mm * alt) / (fl_mm * px_w)  # meters/pixel
        gsd_h_m = (sh_mm * alt) / (fl_mm * px_h)

        gsd_w_cm = gsd_w_m * 100.0
        gsd_h_cm = gsd_h_m * 100.0
        gsd_cm = max(gsd_w_cm, gsd_h_cm)  # worst-case per DJI guidance

        # Ground footprint
        footprint_w = gsd_w_m * px_w
        footprint_h = gsd_h_m * px_h

        # Pixels on target
        pot = target_size_m / (gsd_cm / 100.0) if gsd_cm > 0 else 0.0

        # Field of view
        fov_h = 2 * np.degrees(np.arctan(sw_mm / (2 * fl_mm)))
        fov_v = 2 * np.degrees(np.arctan(sh_mm / (2 * fl_mm)))

        return ModelOutput(
            values={
                "gsd_h_cm_px": gsd_h_cm,
                "gsd_w_cm_px": gsd_w_cm,
                "gsd_cm_px": gsd_cm,
                "footprint_w_m": footprint_w,
                "footprint_h_m": footprint_h,
                "pixels_on_target": pot,
                "fov_h_deg": fov_h,
                "fov_v_deg": fov_v,
            },
            units={
                "gsd_h_cm_px": "cm/px", "gsd_w_cm_px": "cm/px",
                "gsd_cm_px": "cm/px",
                "footprint_w_m": "m", "footprint_h_m": "m",
                "pixels_on_target": "px", "fov_h_deg": "deg", "fov_v_deg": "deg",
            },
        )


def compute_altitude_band(
    sensor_width_mm: float,
    sensor_height_mm: float,
    focal_length_mm: float,
    pixel_width: int,
    pixel_height: int,
    min_gsd_cm: float,
    max_gsd_cm: float,
    target_size_m: float = 1.0,
    min_pixels_on_target: float = 10.0,
) -> tuple[float, float]:
    """Compute the altitude band where GSD and POT constraints are satisfied.

    Returns (min_altitude_m, max_altitude_m).
    """
    # Max altitude from GSD constraint: GSD = (sw * h) / (fl * px_w)
    # h_max = max_gsd * fl * px_w / sw
    gsd_scale_w = sensor_width_mm / (focal_length_mm * pixel_width)
    gsd_scale_h = sensor_height_mm / (focal_length_mm * pixel_height)
    gsd_scale = max(gsd_scale_w, gsd_scale_h)

    h_max_gsd = (max_gsd_cm / 100.0) / gsd_scale if gsd_scale > 0 else 999.0
    h_min_gsd = (min_gsd_cm / 100.0) / gsd_scale if gsd_scale > 0 else 1.0

    # Max altitude from POT constraint
    h_max_pot = target_size_m * focal_length_mm * pixel_width / (sensor_width_mm * min_pixels_on_target) if min_pixels_on_target > 0 else 999.0

    h_max = min(h_max_gsd, h_max_pot)
    h_min = max(h_min_gsd, 2.0)

    return (h_min, h_max)


def compute_standoff_distance(
    required_gsd_cm: float,
    focal_length_mm: float,
    sensor_width_mm: float,
    pixel_width: int,
    gimbal_max_pitch_deg: float = 90.0,
    safety_clearance_m: float = 5.0,
) -> float:
    """Compute standoff distance for oblique inspection.

    The standoff is driven by required GSD on target surface + safety clearance.
    """
    gsd_m = required_gsd_cm / 100.0
    slant_range = gsd_m * focal_length_mm * pixel_width / (sensor_width_mm + 1e-9)
    standoff = max(slant_range * np.cos(np.radians(90 - gimbal_max_pitch_deg)), safety_clearance_m)
    return standoff
