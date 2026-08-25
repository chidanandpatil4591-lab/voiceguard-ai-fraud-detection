"""Audio processing pipeline for VoiceGuard AI.

Handles audio loading, resampling, mono-conversion, and acoustic
feature extraction used by the voice-integrity detector.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import UploadFile

UPLOAD_DIRECTORY = Path(__file__).parent / "uploads"
MAX_AUDIO_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
SUPPORTED_AUDIO_TYPES: dict[str, set[str]] = {
    ".wav": {"audio/wav", "audio/x-wav"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".m4a": {"audio/mp4", "audio/x-m4a"},
    ".flac": {"audio/flac", "audio/x-flac"},
    ".ogg": {"audio/ogg", "application/ogg"},
    ".webm": {"audio/webm", "audio/webm;codecs=opus"},
}


class AudioValidationError(ValueError):
    """Raised when an upload is not an allowed audio recording."""


class AudioProcessingError(ValueError):
    """Raised when an accepted file cannot be decoded or measured."""


# ---------------------------------------------------------------------------
# Validation & upload helpers
# ---------------------------------------------------------------------------

def validate_audio_metadata(filename: str | None, content_type: str | None) -> str:
    if not filename:
        raise AudioValidationError("Please upload an audio file.")

    extension = Path(filename).suffix.lower()
    allowed_types = SUPPORTED_AUDIO_TYPES.get(extension)
    if allowed_types is None:
        raise AudioValidationError(
            f"Unsupported audio format '{extension}'. "
            f"Accepted: {', '.join(SUPPORTED_AUDIO_TYPES)}."
        )

    if content_type:
        # Strip codec suffix for comparison, e.g. "audio/webm;codecs=opus" → "audio/webm"
        bare_type = content_type.lower().split(";")[0].strip()
        if bare_type not in {t.split(";")[0] for t in allowed_types}:
            raise AudioValidationError("The file type does not match its audio format.")

    return extension


async def save_upload_temporarily(upload: UploadFile, extension: str) -> tuple[Path, int]:
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary_file = tempfile.NamedTemporaryFile(
        mode="w+b",
        suffix=extension,
        prefix="voiceguard-",
        dir=UPLOAD_DIRECTORY,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    total_size = 0

    try:
        while chunk := await upload.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > MAX_AUDIO_FILE_SIZE:
                raise AudioValidationError("Audio file is too large (max 25 MB).")
            temporary_file.write(chunk)
        temporary_file.flush()

        if total_size == 0:
            raise AudioValidationError("The audio file is empty.")

        return temporary_path, total_size
    except Exception:
        temporary_file.close()
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        temporary_file.close()


# ---------------------------------------------------------------------------
# Audio loading & normalisation
# ---------------------------------------------------------------------------

def _resample_audio(
    audio: np.ndarray, original_sample_rate: int, target_sample_rate: int
) -> np.ndarray:
    if original_sample_rate == target_sample_rate or audio.size == 0:
        return audio.astype(np.float32, copy=False)

    if original_sample_rate <= 0:
        raise AudioProcessingError("The audio recording contains no usable samples.")

    new_length = max(1, int(round(audio.size * target_sample_rate / original_sample_rate)))
    if new_length == 1:
        return audio[:1].astype(np.float32, copy=False)

    old_positions = np.linspace(0, audio.size - 1, new_length)
    indices = np.floor(old_positions).astype(int)
    next_indices = np.clip(indices + 1, 0, audio.size - 1)
    fraction = old_positions - indices
    resampled = audio[indices] + (audio[next_indices] - audio[indices]) * fraction
    return resampled.astype(np.float32, copy=False)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert multi-channel audio to mono by averaging channels."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        return audio
    # audio.ndim >= 2: average across channel axis (axis=1 for [samples, channels])
    return np.mean(audio, axis=1).astype(np.float32)


def load_audio(file_path: Path, sample_rate: int = 16_000) -> tuple[np.ndarray, int]:
    try:
        audio, loaded_sample_rate = sf.read(file_path, dtype="float32", always_2d=False)
    except Exception as error:
        raise AudioProcessingError("Unable to decode this audio recording.") from error

    audio = _to_mono(audio)
    if audio.size == 0 or not np.isfinite(audio).all():
        raise AudioProcessingError("The audio recording contains no usable samples.")

    if loaded_sample_rate != sample_rate:
        audio = _resample_audio(audio, int(loaded_sample_rate), int(sample_rate))
        loaded_sample_rate = sample_rate

    return audio.astype(np.float32, copy=False), loaded_sample_rate


# ---------------------------------------------------------------------------
# Signal analysis helpers
# ---------------------------------------------------------------------------

def _mel_filterbank(sample_rate: int, n_fft: int, n_mels: int = 40) -> np.ndarray:
    fft_bins = n_fft // 2 + 1
    low_hz, high_hz = 0.0, float(sample_rate / 2)
    mel_low = 2595.0 * np.log10(1.0 + low_hz / 700.0)
    mel_high = 2595.0 * np.log10(1.0 + high_hz / 700.0)
    mel_points = np.linspace(mel_low, mel_high, n_mels + 2)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
    bin_points = np.clip(
        np.floor((n_fft + 1) * hz_points / sample_rate).astype(int), 0, fft_bins - 1
    )
    filters = np.zeros((n_mels, fft_bins), dtype=np.float64)
    for m in range(n_mels):
        left, center, right = bin_points[m], bin_points[m + 1], bin_points[m + 2]
        if center == left or center == right:
            continue
        for k in range(max(0, left), min(fft_bins, right + 1)):
            if k < center:
                filters[m, k] = (k - left) / float(center - left)
            else:
                filters[m, k] = (right - k) / float(right - center)
    return filters


def _dct_ii(values: np.ndarray, num_coefficients: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    n = values.size
    if n == 0:
        return np.zeros(num_coefficients, dtype=np.float64)
    k = np.arange(num_coefficients)[:, None]
    m = np.arange(n)[None, :]
    basis = np.cos(np.pi / n * (m + 0.5) * k)
    outputs = basis @ values
    if num_coefficients > 1:
        outputs = outputs / np.sqrt(n)
    return outputs[:num_coefficients]


def _compute_pitch(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, float]:
    """Estimate pitch (F0) per frame using autocorrelation.

    Returns a (pitches, voiced_ratio) tuple where *pitches* is an array
    of per-frame F0 values in Hz for voiced frames only.
    """
    frame_length = max(256, int(sample_rate * 0.03))
    hop_length = max(64, frame_length // 2)
    pitches: list[float] = []
    total_frames = 0

    for start in range(0, max(1, len(audio) - frame_length), hop_length):
        frame = audio[start : start + frame_length]
        if frame.size < frame_length:
            frame = np.pad(frame, (0, frame_length - frame.size))
        total_frames += 1
        if np.max(np.abs(frame)) < 1e-4:
            continue  # silent frame
        autocorr = np.correlate(frame, frame, mode="full")[len(frame) - 1 :]
        autocorr[:10] = 0.0
        min_lag = int(sample_rate / 500)
        max_lag = int(sample_rate / 65)
        if max_lag <= min_lag:
            continue
        valid = autocorr[min_lag:max_lag]
        if valid.size == 0:
            continue
        lag_index = int(np.argmax(valid)) + min_lag
        if lag_index <= 0:
            continue
        pitch_hz = sample_rate / lag_index
        if 65 <= pitch_hz <= 500:
            pitches.append(float(pitch_hz))

    voiced_ratio = len(pitches) / max(1, total_frames)
    if not pitches:
        return np.array([], dtype=np.float32), 0.0
    return np.asarray(pitches, dtype=np.float32), voiced_ratio


def _compute_jitter(pitches: np.ndarray) -> float:
    """Jitter: mean absolute difference between consecutive pitch periods.

    Expressed as a ratio (dimensionless), also called relative jitter.
    High jitter indicates natural micro-variation; low jitter can suggest
    synthetic/TTS-generated speech.
    """
    if pitches.size < 2:
        return 0.0
    periods = 1.0 / np.maximum(pitches, 1e-6)
    diffs = np.abs(np.diff(periods))
    mean_period = float(np.mean(periods))
    if mean_period < 1e-9:
        return 0.0
    return float(np.mean(diffs) / mean_period)


def _compute_harmonic_to_noise_ratio(audio: np.ndarray, sample_rate: int) -> float:
    """Approximate HNR via autocorrelation peak ratio.

    Voiced human speech typically has HNR > 20 dB.  TTS output can be
    abnormally clean (very high HNR) or exhibit phase artefacts that
    lower it — both directions are informative.
    Returns HNR in dB, clamped to [-10, 40].
    """
    frame_length = max(256, int(sample_rate * 0.025))
    hop_length = frame_length // 2
    hnrs: list[float] = []

    for start in range(0, max(1, len(audio) - frame_length), hop_length):
        frame = audio[start : start + frame_length]
        if frame.size < frame_length:
            frame = np.pad(frame, (0, frame_length - frame.size))
        energy = float(np.sum(frame ** 2))
        if energy < 1e-10:
            continue
        autocorr = np.correlate(frame, frame, mode="full")[len(frame) - 1 :]
        r0 = autocorr[0]
        if r0 < 1e-10:
            continue
        min_lag = max(1, int(sample_rate / 500))
        max_lag = min(len(autocorr) - 1, int(sample_rate / 65))
        if max_lag <= min_lag:
            continue
        rmax = float(np.max(autocorr[min_lag:max_lag]))
        ratio = max(rmax / r0, 1e-6)
        if ratio >= 1.0:
            ratio = 0.9999
        hnr_db = 10.0 * np.log10(ratio / (1.0 - ratio))
        hnrs.append(float(np.clip(hnr_db, -10.0, 40.0)))

    return float(np.mean(hnrs)) if hnrs else 0.0


def _compute_spectral_flatness(power: np.ndarray) -> float:
    """Spectral flatness (Wiener entropy) per frame, averaged.

    Values near 1 indicate noise-like (flat) spectrum; values near 0
    indicate tonal/voiced signal.  Some TTS vocoders leave residual
    flat-spectrum artefacts detectable via this metric.
    """
    eps = 1e-12
    # power shape: (frames, fft_bins)
    geometric_mean = np.exp(np.mean(np.log(power + eps), axis=1))
    arithmetic_mean = np.mean(power, axis=1) + eps
    flatness = geometric_mean / arithmetic_mean
    return float(np.mean(np.clip(flatness, 0.0, 1.0)))


def _compute_shimmer(audio: np.ndarray, sample_rate: int, pitches: np.ndarray) -> float:
    """Shimmer: mean absolute difference between consecutive voiced-frame amplitudes.

    Expressed as a ratio.  Low shimmer in natural-sounding speech can
    indicate over-smoothed TTS amplitude envelopes.
    """
    if pitches.size < 2:
        return 0.0
    frame_length = max(128, int(sample_rate * 0.02))
    hop_length = frame_length // 2
    amplitudes: list[float] = []
    for start in range(0, max(1, len(audio) - frame_length), hop_length):
        frame = audio[start : start + frame_length]
        rms = float(np.sqrt(np.mean(frame ** 2) + 1e-12))
        amplitudes.append(rms)
    if len(amplitudes) < 2:
        return 0.0
    amp = np.asarray(amplitudes)
    diffs = np.abs(np.diff(amp))
    mean_amp = float(np.mean(amp))
    if mean_amp < 1e-9:
        return 0.0
    return float(np.mean(diffs) / mean_amp)


# ---------------------------------------------------------------------------
# Main feature extraction entry point
# ---------------------------------------------------------------------------

def extract_features(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    """Extract a rich set of acoustic features from a mono audio array.

    Returns a flat dict of ``{feature_name: float}`` values, all finite.
    Raises ``AudioProcessingError`` if the audio array is unusable.
    """
    if audio.size == 0 or not np.isfinite(audio).all():
        raise AudioProcessingError("The audio recording contains no usable samples.")

    minimum_length = 2048
    analysis_audio = np.pad(audio, (0, max(0, minimum_length - audio.size)))
    hop_length = 512
    frame_length = minimum_length
    n_fft = frame_length

    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)

    # Build framed windowed signal
    frames = []
    for start in range(0, max(1, analysis_audio.size - hop_length + 1), hop_length):
        frame = analysis_audio[start : start + frame_length]
        if frame.size < frame_length:
            frame = np.pad(frame, (0, frame_length - frame.size))
        frames.append(frame * np.hanning(frame_length))
    if not frames:
        frames = [analysis_audio[:frame_length] * np.hanning(frame_length)]

    frames_array = np.asarray(frames)                        # (F, N)
    spectrum = np.abs(np.fft.rfft(frames_array, axis=-1))   # (F, B)
    power = spectrum ** 2                                    # (F, B)

    # --- Spectral features ---
    total_power = np.maximum(np.sum(power, axis=1), 1e-8)
    spectral_centroid = np.sum(freqs[None, :] * power, axis=1) / total_power
    spectral_bandwidth = np.sqrt(
        np.sum(((freqs[None, :] - spectral_centroid[:, None]) ** 2) * power, axis=1)
        / total_power
    )
    rolloff_thresholds = 0.85 * np.sum(power, axis=1)
    spectral_rolloff = []
    for row, threshold in zip(power, rolloff_thresholds):
        cumulative = np.cumsum(row)
        index = np.searchsorted(cumulative, threshold, side="left")
        spectral_rolloff.append(freqs[min(index, len(freqs) - 1)])
    spectral_rolloff_arr = np.asarray(spectral_rolloff, dtype=np.float64)

    spectral_contrast = (
        np.abs(np.diff(power, axis=0)).mean(axis=1)
        if power.ndim > 1 and power.shape[0] > 1
        else np.array([0.0])
    )

    # Spectral flatness
    spectral_flatness_val = _compute_spectral_flatness(power)

    # --- Spectral flux: frame-to-frame L2 change in spectrum ---
    if spectrum.shape[0] > 1:
        flux = np.sqrt(np.sum(np.diff(spectrum, axis=0) ** 2, axis=1))
        spectral_flux_mean = float(np.mean(flux))
        spectral_flux_std = float(np.std(flux))
    else:
        spectral_flux_mean = 0.0
        spectral_flux_std = 0.0

    # --- Sub-band energy ratios ---
    freq_mask_high = (freqs >= 3000) & (freqs <= 8000)   # 3–8 kHz
    freq_mask_mid = (freqs >= 1000) & (freqs < 3000)      # 1–3 kHz
    freq_mask_low = freqs < 1000                           # 0–1 kHz
    total_energy = np.sum(power) + 1e-12
    sub_band_ratio_high = float(np.sum(power[:, freq_mask_high]) / total_energy)
    sub_band_ratio_mid = float(np.sum(power[:, freq_mask_mid]) / total_energy)
    sub_band_ratio_low = float(np.sum(power[:, freq_mask_low]) / total_energy)

    # --- Energy / RMS ---
    signal_energy = np.square(audio)
    if audio.size > hop_length:
        frame_rms = np.sqrt(
            np.array(
                [
                    np.mean(signal_energy[s : s + hop_length])
                    for s in range(0, max(1, len(audio) - hop_length), hop_length)
                ]
            )
        )
    else:
        frame_rms = np.array([np.sqrt(np.mean(signal_energy))])
    frame_rms = np.maximum(frame_rms, 1e-8)
    silence_threshold = max(float(np.max(frame_rms)) * 0.08, 1e-4)
    silence_ratio = float(np.mean(frame_rms <= silence_threshold))
    active_frames = frame_rms > silence_threshold
    pause_count = int(np.sum(np.diff(active_frames.astype(np.int8)) == -1))

    # RMS modulation index: std/mean
    rms_modulation = float(np.std(frame_rms) / (np.mean(frame_rms) + 1e-8))

    # --- Zero-crossing rate (per-frame std) ---
    zcr_per_frame = np.array(
        [
            float(np.mean(np.abs(np.diff(np.signbit(audio[s : s + hop_length])))))
            for s in range(0, max(1, len(audio) - hop_length), hop_length)
        ]
    )
    zcr_mean = float(np.mean(zcr_per_frame)) if zcr_per_frame.size else 0.0
    zcr_std = float(np.std(zcr_per_frame)) if zcr_per_frame.size > 1 else 0.0

    # --- MFCC ---
    mel_filters = _mel_filterbank(sample_rate, n_fft, n_mels=40)
    frame_magnitude = np.abs(np.fft.rfft(frames_array, axis=-1))
    mel_energy = np.maximum(frame_magnitude @ mel_filters.T, 1e-8)
    log_mel = np.log(mel_energy)
    if log_mel.ndim == 1:
        log_mel = log_mel[None, :]

    mfcc_coeffs = np.array(
        [_dct_ii(frame_log, 13) for frame_log in log_mel], dtype=np.float64
    )

    # MFCC delta: frame-to-frame MFCC change
    if mfcc_coeffs.shape[0] > 1:
        mfcc_delta = np.abs(np.diff(mfcc_coeffs, axis=0))
        mfcc_delta_std = float(np.mean(np.std(mfcc_delta, axis=0)))
        mfcc_delta_mean = float(np.mean(mfcc_delta))
    else:
        mfcc_delta_std = 0.0
        mfcc_delta_mean = 0.0

    # --- Pitch / prosody ---
    pitch, voiced_ratio = _compute_pitch(audio, sample_rate)

    # F0 range
    f0_range = float(np.max(pitch) - np.min(pitch)) if pitch.size >= 2 else 0.0
    f0_range_pct = f0_range / (float(np.mean(pitch)) + 1e-6) if pitch.size >= 2 else 0.0

    # --- Prosody biomarkers ---
    jitter_val = _compute_jitter(pitch)
    shimmer_val = _compute_shimmer(audio, sample_rate, pitch)
    hnr_val = _compute_harmonic_to_noise_ratio(audio, sample_rate)

    # --- Assemble feature dict ---
    features: dict[str, float] = {
        "duration_seconds": float(audio.size / sample_rate),
        "silence_ratio": silence_ratio,
        "pause_count": float(pause_count),
        "peak_amplitude": float(np.max(np.abs(audio))),
        "zero_crossing_rate_mean": zcr_mean,
        "zero_crossing_rate_std": zcr_std,
        "spectral_centroid_mean": float(np.mean(spectral_centroid)),
        "spectral_centroid_std": float(np.std(spectral_centroid)),
        "spectral_bandwidth_mean": float(np.mean(spectral_bandwidth)),
        "spectral_bandwidth_std": float(np.std(spectral_bandwidth)),
        "spectral_rolloff_mean": float(np.mean(spectral_rolloff_arr)),
        "spectral_rolloff_std": float(np.std(spectral_rolloff_arr)),
        "spectral_contrast_mean": float(np.mean(spectral_contrast)),
        "spectral_contrast_std": float(np.std(spectral_contrast)),
        "spectral_flatness": spectral_flatness_val,
        "spectral_flux_mean": spectral_flux_mean,
        "spectral_flux_std": spectral_flux_std,
        "sub_band_ratio_high": sub_band_ratio_high,
        "sub_band_ratio_mid": sub_band_ratio_mid,
        "sub_band_ratio_low": sub_band_ratio_low,
        "mel_mean": float(np.mean(log_mel)),
        "mel_std": float(np.std(log_mel)),
        "rms_energy_mean": float(np.mean(frame_rms)),
        "rms_energy_std": float(np.std(frame_rms)),
        "rms_modulation": rms_modulation,
        "pitch_mean": float(np.mean(pitch)) if pitch.size else 0.0,
        "pitch_std": float(np.std(pitch)) if pitch.size else 0.0,
        "pitch_voiced_ratio": float(voiced_ratio),
        "f0_range": f0_range,
        "f0_range_pct": f0_range_pct,
        "jitter": jitter_val,
        "shimmer": shimmer_val,
        "harmonic_to_noise_ratio": hnr_val,
        "mfcc_delta_std": mfcc_delta_std,
        "mfcc_delta_mean": mfcc_delta_mean,
    }

    # Per-coefficient MFCC stats
    for index in range(13):
        values = mfcc_coeffs[:, index] if mfcc_coeffs.ndim > 1 else mfcc_coeffs[index : index + 1]
        features[f"mfcc_{index + 1}_mean"] = float(np.mean(values))
        features[f"mfcc_{index + 1}_std"] = float(np.std(values))

    return {name: float(np.nan_to_num(value)) for name, value in features.items()}


def process_audio_file(file_path: Path, extension: str, size_bytes: int) -> dict[str, object]:
    audio, sample_rate = load_audio(file_path)
    return {
        "file_extension": extension,
        "size_bytes": size_bytes,
        "sample_rate": sample_rate,
        "features": extract_features(audio, sample_rate),
    }
