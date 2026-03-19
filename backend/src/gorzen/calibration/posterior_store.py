"""Posterior store: versioned posteriors, GP residuals, credible interval computation.

Manages versioned posterior distributions and GP discrepancy models, keyed
by twin configuration hash, firmware version, and calibration date.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


from gorzen.calibration.bayesian import CalibrationResult, PosteriorDistribution


@dataclass
class PosteriorVersion:
    """A versioned snapshot of calibration posteriors."""

    version_id: str
    config_hash: str
    firmware_version: str
    regime: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    posteriors: dict[str, PosteriorDistribution] = field(default_factory=dict)
    discrepancy_model_path: str | None = None
    n_observations: int = 0
    log_ids: list[str] = field(default_factory=list)


class PosteriorStore:
    """Manages versioned posterior distributions for fleet-scale calibration.

    Stores posteriors indexed by (config_hash, regime) with full version history.
    """

    def __init__(self, storage_path: str = "./storage/posteriors"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, list[PosteriorVersion]] = {}

    def _key(self, config_hash: str, regime: str) -> str:
        return f"{config_hash}:{regime}"

    def store(
        self,
        result: CalibrationResult,
        firmware_version: str = "",
        log_ids: list[str] | None = None,
    ) -> PosteriorVersion:
        """Store a new calibration result as a versioned posterior."""
        key = self._key(result.config_hash, result.regime)
        versions = self._index.get(key, [])
        version_id = f"v{len(versions) + 1}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Serialize posteriors (without numpy arrays for JSON)
        posterior_data = {}
        for name, post in result.posteriors.items():
            posterior_data[name] = {
                "parameter_name": post.parameter_name,
                "mean": post.mean,
                "std": post.std,
                "credible_interval_90": list(post.credible_interval_90),
            }

        version = PosteriorVersion(
            version_id=version_id,
            config_hash=result.config_hash,
            firmware_version=firmware_version,
            regime=result.regime,
            posteriors=result.posteriors,
            n_observations=result.n_observations,
            log_ids=log_ids or [],
        )

        versions.append(version)
        self._index[key] = versions

        # Persist to disk
        version_dir = self.storage_path / key.replace(":", "_")
        version_dir.mkdir(parents=True, exist_ok=True)
        with open(version_dir / f"{version_id}.json", "w") as f:
            json.dump({
                "version_id": version_id,
                "config_hash": result.config_hash,
                "regime": result.regime,
                "firmware_version": firmware_version,
                "n_observations": result.n_observations,
                "posteriors": posterior_data,
                "timestamp": version.timestamp.isoformat(),
            }, f, indent=2)

        return version

    def get_latest(self, config_hash: str, regime: str) -> PosteriorVersion | None:
        """Get the most recent posterior version for a config+regime."""
        key = self._key(config_hash, regime)
        versions = self._index.get(key, [])
        return versions[-1] if versions else None

    def get_history(self, config_hash: str, regime: str) -> list[PosteriorVersion]:
        """Get full version history for a config+regime."""
        key = self._key(config_hash, regime)
        return self._index.get(key, [])

    def compute_credible_intervals(
        self,
        posterior: PosteriorDistribution,
        levels: list[float] = [0.5, 0.9, 0.95],
    ) -> dict[str, tuple[float, float]]:
        """Compute credible intervals at specified levels."""
        intervals: dict[str, tuple[float, float]] = {}
        for level in levels:
            alpha = 1.0 - level
            low = posterior.percentile(alpha / 2 * 100)
            high = posterior.percentile((1 - alpha / 2) * 100)
            intervals[f"{int(level * 100)}%"] = (low, high)
        return intervals

    def get_parameter_trend(
        self,
        config_hash: str,
        regime: str,
        parameter_name: str,
    ) -> list[dict[str, Any]]:
        """Get the evolution of a parameter's posterior over calibration runs."""
        versions = self.get_history(config_hash, regime)
        trend = []
        for v in versions:
            if parameter_name in v.posteriors:
                p = v.posteriors[parameter_name]
                trend.append({
                    "version_id": v.version_id,
                    "timestamp": v.timestamp.isoformat(),
                    "mean": p.mean,
                    "std": p.std,
                    "ci_90": p.credible_interval_90,
                    "n_observations": v.n_observations,
                })
        return trend
