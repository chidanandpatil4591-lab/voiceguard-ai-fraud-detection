"""Train the local demonstration spoofing classifier.

This creates a reproducible model artifact from controlled acoustic feature
distributions. Replace this training source with labelled ASVspoof data for
production use.
"""

from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = (
    "jitter", "shimmer", "harmonic_to_noise_ratio", "f0_range",
    "spectral_flux_norm", "mfcc_delta_std", "rms_modulation",
    "sub_band_ratio_high", "spectral_flatness", "silence_ratio",
)


def _samples(rng: np.random.Generator, center: list[float], scale: list[float]) -> np.ndarray:
    values = rng.normal(center, scale, size=(2400, len(FEATURE_NAMES)))
    values[:, 0] = np.clip(values[:, 0], 0.0001, 0.08)
    values[:, 1] = np.clip(values[:, 1], 0.0001, 0.20)
    values[:, 2] = np.clip(values[:, 2], -10, 40)
    values[:, 3] = np.clip(values[:, 3], 0, 500)
    values[:, 4:] = np.clip(values[:, 4:], 0, None)
    return values


def train() -> None:
    rng = np.random.default_rng(20260902)
    human = _samples(
        rng,
        [0.010, 0.035, 18, 145, 0.30, 4.2, 0.30, 0.10, 0.14, 0.12],
        [0.004, 0.012, 5, 65, 0.12, 1.8, 0.12, 0.035, 0.08, 0.08],
    )
    synthetic = _samples(
        rng,
        [0.0015, 0.006, 33, 25, 0.045, 0.65, 0.06, 0.30, 0.48, 0.12],
        [0.001, 0.004, 4, 18, 0.025, 0.35, 0.04, 0.06, 0.12, 0.08],
    )
    features = np.vstack((human, synthetic))
    labels = np.concatenate((np.zeros(len(human)), np.ones(len(synthetic))))
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.7, max_iter=2000, random_state=20260902),
    )
    model.fit(features, labels)
    output = Path(__file__).parent / "models" / "spoofing_demo_v1.joblib"
    output.parent.mkdir(exist_ok=True)
    joblib.dump({"model": model, "feature_names": FEATURE_NAMES, "version": "trained-demo-v1"}, output)
    print(f"saved {output}")


if __name__ == "__main__":
    train()