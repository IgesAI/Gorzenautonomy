"""Kennedy-O'Hagan Bayesian calibration with GP discrepancy.

Calibrates physics model parameters while explicitly modeling the discrepancy
between model predictions and observations using a Gaussian Process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from scipy.optimize import minimize


@dataclass
class PosteriorDistribution:
    """Posterior distribution for a calibrated parameter."""

    parameter_name: str
    mean: float
    std: float
    samples: np.ndarray | None = None
    credible_interval_90: tuple[float, float] = (0.0, 0.0)
    evidence_ids: list[str] = field(default_factory=list)

    def percentile(self, p: float) -> float:
        if self.samples is not None:
            return float(np.percentile(self.samples, p))
        from scipy.stats import norm
        return float(norm.ppf(p / 100, self.mean, self.std))


@dataclass
class GPDiscrepancy:
    """Gaussian Process model for residual discrepancy."""

    input_dim: int
    length_scales: np.ndarray | None = None
    signal_variance: float = 1.0
    noise_variance: float = 0.01
    X_train: np.ndarray | None = None
    y_train: np.ndarray | None = None
    alpha: np.ndarray | None = None  # pre-computed K^{-1} y

    def _kernel(self, x1: np.ndarray, x2: np.ndarray) -> float:
        if self.length_scales is None:
            self.length_scales = np.ones(self.input_dim)
        diff = (x1 - x2) / self.length_scales
        return self.signal_variance * np.exp(-0.5 * np.sum(diff ** 2))

    def _kernel_matrix(self, X1: np.ndarray, X2: np.ndarray) -> np.ndarray:
        n1, n2 = X1.shape[0], X2.shape[0]
        K = np.zeros((n1, n2))
        for i in range(n1):
            for j in range(n2):
                K[i, j] = self._kernel(X1[i], X2[j])
        return K

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit the GP discrepancy model."""
        self.X_train = X
        self.y_train = y
        self.input_dim = X.shape[1]
        self.length_scales = np.std(X, axis=0) + 1e-6

        K = self._kernel_matrix(X, X) + self.noise_variance * np.eye(len(X))
        try:
            self.alpha = np.linalg.solve(K, y)
        except np.linalg.LinAlgError:
            self.alpha = np.linalg.lstsq(K, y, rcond=None)[0]

    def predict(self, X_new: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Predict mean and variance at new input points."""
        if self.X_train is None or self.alpha is None:
            return np.zeros(X_new.shape[0]), np.ones(X_new.shape[0]) * self.signal_variance

        k_star = self._kernel_matrix(X_new, self.X_train)
        mean = k_star @ self.alpha

        K = self._kernel_matrix(self.X_train, self.X_train) + self.noise_variance * np.eye(len(self.X_train))
        k_ss = np.array([self._kernel(X_new[i], X_new[i]) for i in range(len(X_new))])

        try:
            K_inv = np.linalg.inv(K)
            var = k_ss - np.sum((k_star @ K_inv) * k_star, axis=1)
        except np.linalg.LinAlgError:
            var = np.ones(len(X_new)) * self.signal_variance

        var = np.maximum(var, 1e-8)
        return mean, var


@dataclass
class CalibrationResult:
    """Result of Bayesian calibration."""

    posteriors: dict[str, PosteriorDistribution] = field(default_factory=dict)
    discrepancy_model: GPDiscrepancy | None = None
    log_marginal_likelihood: float = 0.0
    n_observations: int = 0
    config_hash: str = ""
    regime: str = ""


class BayesianCalibrator:
    """Kennedy-O'Hagan Bayesian calibration framework.

    Model: y = eta(x, theta) + delta(x) + epsilon
    where eta is the physics model, delta is GP discrepancy, epsilon is noise.
    """

    def __init__(
        self,
        physics_model: Callable[[np.ndarray, np.ndarray], np.ndarray],
        param_names: list[str],
        param_priors: dict[str, tuple[float, float]],
        n_posterior_samples: int = 500,
    ):
        """
        Args:
            physics_model: f(x_conditions, theta_params) -> predictions
            param_names: names of calibration parameters (theta)
            param_priors: {name: (mean, std)} for prior distributions
            n_posterior_samples: number of posterior samples to draw
        """
        self.physics_model = physics_model
        self.param_names = param_names
        self.param_priors = param_priors
        self.n_samples = n_posterior_samples

    def calibrate(
        self,
        X_obs: np.ndarray,
        y_obs: np.ndarray,
        config_hash: str = "",
        regime: str = "",
    ) -> CalibrationResult:
        """Run Bayesian calibration.

        Args:
            X_obs: observed conditions, shape (n, d_x)
            y_obs: observed outputs, shape (n,)
        """
        n_obs = len(y_obs)
        n_params = len(self.param_names)

        # Initial parameter estimate via MAP (maximum a posteriori)
        theta0 = np.array([self.param_priors[p][0] for p in self.param_names])

        def neg_log_posterior(theta: np.ndarray) -> float:
            # Prior
            log_prior = 0.0
            for i, name in enumerate(self.param_names):
                mu, sigma = self.param_priors[name]
                log_prior -= 0.5 * ((theta[i] - mu) / sigma) ** 2

            # Likelihood
            try:
                pred = self.physics_model(X_obs, theta)
                residuals = y_obs - pred
                sigma_n = np.std(residuals) + 1e-6
                log_lik = -0.5 * np.sum((residuals / sigma_n) ** 2) - n_obs * np.log(sigma_n)
            except Exception:
                return 1e10

            return -(log_prior + log_lik)

        result = minimize(neg_log_posterior, theta0, method="Nelder-Mead",
                          options={"maxiter": 1000})
        theta_map = result.x

        # Approximate posterior via Laplace approximation
        # Hessian approximation for covariance
        eps = 1e-5
        H = np.zeros((n_params, n_params))
        f0 = neg_log_posterior(theta_map)
        for i in range(n_params):
            for j in range(n_params):
                e_i = np.zeros(n_params)
                e_j = np.zeros(n_params)
                e_i[i] = eps
                e_j[j] = eps
                H[i, j] = (
                    neg_log_posterior(theta_map + e_i + e_j)
                    - neg_log_posterior(theta_map + e_i)
                    - neg_log_posterior(theta_map + e_j)
                    + f0
                ) / (eps ** 2)

        try:
            cov = np.linalg.inv(H + np.eye(n_params) * 1e-6)
            cov = (cov + cov.T) / 2
            cov = np.maximum(cov, np.eye(n_params) * 1e-8)
        except np.linalg.LinAlgError:
            cov = np.eye(n_params) * 0.01

        # Draw posterior samples
        try:
            L = np.linalg.cholesky(cov)
            samples = theta_map + (np.random.randn(self.n_samples, n_params) @ L.T)
        except np.linalg.LinAlgError:
            stds = np.sqrt(np.maximum(np.diag(cov), 1e-8))
            samples = theta_map + np.random.randn(self.n_samples, n_params) * stds

        # Build posteriors
        posteriors: dict[str, PosteriorDistribution] = {}
        for i, name in enumerate(self.param_names):
            s = samples[:, i]
            posteriors[name] = PosteriorDistribution(
                parameter_name=name,
                mean=float(np.mean(s)),
                std=float(np.std(s)),
                samples=s,
                credible_interval_90=(float(np.percentile(s, 5)), float(np.percentile(s, 95))),
            )

        # Fit GP discrepancy model on residuals
        pred_map = self.physics_model(X_obs, theta_map)
        residuals = y_obs - pred_map

        gp = GPDiscrepancy(input_dim=X_obs.shape[1])
        gp.fit(X_obs, residuals)

        return CalibrationResult(
            posteriors=posteriors,
            discrepancy_model=gp,
            log_marginal_likelihood=-result.fun,
            n_observations=n_obs,
            config_hash=config_hash,
            regime=regime,
        )
