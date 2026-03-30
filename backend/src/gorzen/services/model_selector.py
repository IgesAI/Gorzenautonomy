"""VLM / CV model recommendation engine.

Given image quality constraints (GSD, NIIRS, pixels-on-target), operational
mode (edge vs cloud), and mission type, recommends the optimal vision model
and estimates detection performance.

Model accuracy curves are derived from published benchmarks and aerial
inspection literature (e.g., COCO mAP, PowerLine defect detection papers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeploymentMode(str, Enum):
    ONBOARD = "onboard"
    CLOUD = "cloud"
    EITHER = "either"


class DefectClass(str, Enum):
    CRACK = "crack"
    CORROSION = "corrosion"
    VEGETATION = "vegetation"
    THERMAL_ANOMALY = "thermal_anomaly"
    PERSON = "person"
    VEHICLE = "vehicle"
    STRUCTURAL_DAMAGE = "structural_damage"
    GENERIC = "generic"


@dataclass
class ModelSpec:
    """Specification for a vision model."""

    name: str
    family: str
    deployment: DeploymentMode
    input_resolution_px: int
    latency_ms: float
    accuracy_mAP: float
    flops_gflops: float
    memory_mb: float
    supports_defect_classes: list[DefectClass]
    edge_compatible: bool
    description: str


@dataclass
class ModelRecommendation:
    """Recommendation result for a specific mission."""

    primary_model: ModelSpec
    fallback_model: ModelSpec | None
    estimated_detection_probability: float
    estimated_false_positive_rate: float
    deployment_mode: DeploymentMode
    reasoning: str
    constraints_met: dict[str, bool] = field(default_factory=dict)
    performance_notes: list[str] = field(default_factory=list)


# Pre-defined model catalog based on published benchmarks
MODEL_CATALOG: list[ModelSpec] = [
    ModelSpec(
        name="YOLOv8-nano",
        family="YOLO",
        deployment=DeploymentMode.ONBOARD,
        input_resolution_px=640,
        latency_ms=8.0,
        accuracy_mAP=0.37,
        flops_gflops=8.7,
        memory_mb=6.3,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.PERSON,
            DefectClass.VEHICLE, DefectClass.GENERIC,
        ],
        edge_compatible=True,
        description="Ultra-fast edge model for real-time detection on embedded GPU (Jetson Orin Nano).",
    ),
    ModelSpec(
        name="YOLOv8-small",
        family="YOLO",
        deployment=DeploymentMode.ONBOARD,
        input_resolution_px=640,
        latency_ms=15.0,
        accuracy_mAP=0.45,
        flops_gflops=28.6,
        memory_mb=22.5,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.VEGETATION,
            DefectClass.PERSON, DefectClass.VEHICLE, DefectClass.STRUCTURAL_DAMAGE,
            DefectClass.GENERIC,
        ],
        edge_compatible=True,
        description="Balanced edge model with good accuracy for onboard processing (Jetson Orin NX).",
    ),
    ModelSpec(
        name="YOLOv8-large",
        family="YOLO",
        deployment=DeploymentMode.EITHER,
        input_resolution_px=640,
        latency_ms=40.0,
        accuracy_mAP=0.53,
        flops_gflops=165.2,
        memory_mb=87.7,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.VEGETATION,
            DefectClass.THERMAL_ANOMALY, DefectClass.PERSON, DefectClass.VEHICLE,
            DefectClass.STRUCTURAL_DAMAGE, DefectClass.GENERIC,
        ],
        edge_compatible=True,
        description="High-accuracy model usable on powerful edge GPU or cloud.",
    ),
    ModelSpec(
        name="EfficientDet-D2",
        family="EfficientDet",
        deployment=DeploymentMode.ONBOARD,
        input_resolution_px=768,
        latency_ms=25.0,
        accuracy_mAP=0.43,
        flops_gflops=11.0,
        memory_mb=32.0,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.PERSON,
            DefectClass.VEHICLE, DefectClass.GENERIC,
        ],
        edge_compatible=True,
        description="Efficient two-stage detector, good for structured defect detection.",
    ),
    ModelSpec(
        name="Grounding DINO + SAM2",
        family="Foundation",
        deployment=DeploymentMode.CLOUD,
        input_resolution_px=1024,
        latency_ms=350.0,
        accuracy_mAP=0.58,
        flops_gflops=500.0,
        memory_mb=2048.0,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.VEGETATION,
            DefectClass.THERMAL_ANOMALY, DefectClass.PERSON, DefectClass.VEHICLE,
            DefectClass.STRUCTURAL_DAMAGE, DefectClass.GENERIC,
        ],
        edge_compatible=False,
        description="Open-vocabulary detection + segmentation. Zero-shot capable for novel defect types.",
    ),
    ModelSpec(
        name="Florence-2-Large",
        family="VLM",
        deployment=DeploymentMode.CLOUD,
        input_resolution_px=768,
        latency_ms=200.0,
        accuracy_mAP=0.55,
        flops_gflops=300.0,
        memory_mb=1500.0,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.VEGETATION,
            DefectClass.THERMAL_ANOMALY, DefectClass.PERSON, DefectClass.VEHICLE,
            DefectClass.STRUCTURAL_DAMAGE, DefectClass.GENERIC,
        ],
        edge_compatible=False,
        description="Microsoft VLM with strong captioning and grounding for inspection reports.",
    ),
    ModelSpec(
        name="GPT-4o Vision",
        family="VLM",
        deployment=DeploymentMode.CLOUD,
        input_resolution_px=2048,
        latency_ms=2000.0,
        accuracy_mAP=0.62,
        flops_gflops=0.0,  # API-based
        memory_mb=0.0,
        supports_defect_classes=[
            DefectClass.CRACK, DefectClass.CORROSION, DefectClass.VEGETATION,
            DefectClass.THERMAL_ANOMALY, DefectClass.PERSON, DefectClass.VEHICLE,
            DefectClass.STRUCTURAL_DAMAGE, DefectClass.GENERIC,
        ],
        edge_compatible=False,
        description="Highest accuracy VLM via API. Best for detailed inspection reports and rare defects.",
    ),
]


def _estimate_detection_probability(
    model: ModelSpec,
    pixels_on_target: float,
    niirs: float,
    gsd_cm: float,
    defect_class: DefectClass,
) -> float:
    """Estimate P(detection) for a model given image quality metrics.

    Uses empirical curves: detection probability increases with pixels-on-target
    following a logistic function, modulated by NIIRS and model accuracy.
    """
    # Johnson criteria: detection requires ~6 line pairs across target
    # For digital systems: ~12 pixels across the target for detection
    min_pixels = 12.0
    if pixels_on_target < min_pixels:
        pixel_factor = (pixels_on_target / min_pixels) ** 2
    elif pixels_on_target < min_pixels * 4:
        pixel_factor = 0.5 + 0.5 * (pixels_on_target - min_pixels) / (min_pixels * 3)
    else:
        pixel_factor = 1.0

    # NIIRS contribution: detection degrades below NIIRS 5
    niirs_factor = min(1.0, max(0.0, (niirs - 3.0) / 4.0))

    # GSD contribution: fine cracks need very low GSD
    if defect_class == DefectClass.CRACK:
        gsd_factor = min(1.0, 0.5 / (gsd_cm + 0.01))
    else:
        gsd_factor = min(1.0, 3.0 / (gsd_cm + 0.01))

    base_prob = model.accuracy_mAP * pixel_factor * niirs_factor * gsd_factor
    return min(max(base_prob, 0.0), 0.98)


def recommend_model(
    gsd_cm: float,
    niirs: float,
    pixels_on_target: float,
    deployment_mode: DeploymentMode = DeploymentMode.EITHER,
    latency_budget_ms: float = 500.0,
    defect_classes: list[DefectClass] | None = None,
    bandwidth_mbps: float = 10.0,
) -> ModelRecommendation:
    """Recommend the best vision model for the given mission constraints.

    Considers: image quality, deployment mode, latency, defect types, bandwidth.
    """
    target_classes = defect_classes or [DefectClass.GENERIC]

    candidates = []
    for model in MODEL_CATALOG:
        # Filter by deployment compatibility
        if deployment_mode == DeploymentMode.ONBOARD and not model.edge_compatible:
            continue
        if deployment_mode == DeploymentMode.CLOUD and model.deployment == DeploymentMode.ONBOARD:
            pass  # onboard models can run in cloud too

        # Filter by latency
        if model.latency_ms > latency_budget_ms:
            continue

        # Check defect class support
        supported = all(dc in model.supports_defect_classes for dc in target_classes)
        if not supported:
            continue

        # Score the model
        det_prob = _estimate_detection_probability(
            model, pixels_on_target, niirs, gsd_cm, target_classes[0],
        )

        candidates.append((model, det_prob))

    if not candidates:
        # Fall back to the most capable cloud model
        fallback = MODEL_CATALOG[-1]
        det_prob = _estimate_detection_probability(
            fallback, pixels_on_target, niirs, gsd_cm,
            target_classes[0] if target_classes else DefectClass.GENERIC,
        )
        return ModelRecommendation(
            primary_model=fallback,
            fallback_model=None,
            estimated_detection_probability=det_prob,
            estimated_false_positive_rate=0.05,
            deployment_mode=DeploymentMode.CLOUD,
            reasoning="No model met all constraints; defaulting to highest-accuracy cloud VLM.",
            constraints_met={"latency": False, "deployment": False},
        )

    # Sort by detection probability (descending)
    candidates.sort(key=lambda x: x[1], reverse=True)
    primary = candidates[0]
    fallback = candidates[1] if len(candidates) > 1 else None

    # Determine effective deployment mode
    effective_mode = deployment_mode
    if effective_mode == DeploymentMode.EITHER:
        effective_mode = primary[0].deployment

    reasoning_parts = [
        f"Selected {primary[0].name} ({primary[0].family})",
        f"with estimated {primary[1]:.0%} detection probability",
        f"at {primary[0].latency_ms:.0f}ms latency.",
    ]
    if gsd_cm < 0.5:
        reasoning_parts.append("Fine GSD enables crack-level detection.")
    if niirs >= 7.0:
        reasoning_parts.append("High NIIRS supports detailed feature identification.")
    if deployment_mode == DeploymentMode.ONBOARD:
        reasoning_parts.append("Edge deployment selected for real-time in-flight processing.")

    notes = []
    if pixels_on_target < 20:
        notes.append("Low pixels-on-target may limit detection accuracy; consider lower altitude.")
    if bandwidth_mbps < 5 and effective_mode == DeploymentMode.CLOUD:
        notes.append("Limited bandwidth may increase cloud inference latency.")

    return ModelRecommendation(
        primary_model=primary[0],
        fallback_model=fallback[0] if fallback else None,
        estimated_detection_probability=primary[1],
        estimated_false_positive_rate=max(0.01, 1.0 - primary[0].accuracy_mAP) * 0.3,
        deployment_mode=effective_mode,
        reasoning=" ".join(reasoning_parts),
        constraints_met={
            "latency": primary[0].latency_ms <= latency_budget_ms,
            "deployment": True,
            "defect_coverage": True,
        },
        performance_notes=notes,
    )
