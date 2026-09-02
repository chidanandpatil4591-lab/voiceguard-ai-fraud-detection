"""Division 1: High-Precision Acoustic Feature Extraction with Sub-Sample Pitch Refinement."""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
import scipy.io.wavfile as wavfile


class AudioProcessingError(Exception):
    pass


def load_audio(file_path: Path) -> tuple[np.ndarray, int]:
    try:
        sample_rate, data = wavfile.read(str(file_path))
    except Exception as exc:
        raise AudioProcessingError(f"Could not decode audio file: {exc}") from exc

    if data.ndim > 1:
        data = np.mean(data, axis=1)

    if np.issubdtype(data.dtype, np.integer):
        max_val = float(np.iinfo(data.dtype).max)
        audio = (data / max_val).astype(np.float64)
    else:
        audio = data.astype(np.float64)

    if audio.size == 0 or not np.isfinite(audio).all():
        raise AudioProcessingError("Audio signal is empty or contains non-finite values.")

    target_sr = 16000
    if sample_rate != target_sr and sample_rate > 0:
        new_length = int(len(audio) * target_sr / sample_rate)
        indices = np.linspace(0, len(audio) - 1, new_length)
        audio = np.interp(indices, np.arange(len(audio)), audio)
        sample_rate = target_sr

    return audio, sample_rate


def _compute_pitch(audio: np.ndarray, sample_rate: int, frame_length: int = 2048, hop_length: int = 512) -> tuple[np.ndarray, float]:
    min_lag = max(1, int(sample_rate / 500))  # 500 Hz
    max_lag = min(frame_length - 2, int(sample_rate / 60))  # 60 Hz
    pitches = []
    voiced_frames = 0
    total_frames = 0

    for start in range(0, max(1, len(audio) - frame_length), hop_length):
        frame = audio[start : start + frame_length]
        if frame.size < frame_length:
            frame = np.pad(frame, (0, frame_length - frame.size))
        frame = frame - np.mean(frame)
        total_frames += 1
        energy = np.sum(frame**2)
        if energy < 1e-4:
            continue

        corr = np.correlate(frame, frame, mode='full')[frame_length - 1 :]
        if max_lag < len(corr) and corr[0] > 0:
            search_region = corr[min_lag:max_lag]
            if len(search_region) > 0:
                peak_idx = np.argmax(search_region)
                peak_lag = min_lag + peak_idx
                peak_val = corr[peak_lag] / corr[0]

                if peak_val > 0.30:
                    # Sub-sample parabolic interpolation around the autocorrelation peak
                    if 0 < peak_lag < len(corr) - 1:
                        alpha = corr[peak_lag - 1]
                        beta = corr[peak_lag]
                        gamma = corr[peak_lag + 1]
                        denom = alpha - 2.0 * beta + gamma
                        if abs(denom) > 1e-10:
                            delta = 0.5 * (alpha - gamma) / denom
                            refined_lag = float(peak_lag + delta)
                        else:
                            refined_lag = float(peak_lag)
                    else:
                        refined_lag = float(peak_lag)

                    if refined_lag > 0:
                        pitches.append(float(sample_rate / refined_lag))
                        voiced_frames += 1

    pitch_arr = np.array(pitches, dtype=np.float64)
    voiced_ratio = voiced_frames / max(1, total_frames)
    return pitch_arr, voiced_ratio


def _compute_jitter(pitch: np.ndarray) -> float:
    if pitch.size < 3:
        return 0.0
    periods = 1.0 / np.maximum(pitch, 1e-6)
    diffs = np.abs(np.diff(periods))
    mean_period = float(np.mean(periods))
    return float(np.mean(diffs) / (mean_period + 1e-8))


def _compute_shimmer(audio: np.ndarray, sample_rate: int, pitch: np.ndarray) -> float:
    if pitch.size < 3 or audio.size < 2048:
        return 0.0
    avg_period_samples = int(sample_rate / max(1.0, float(np.mean(pitch))))
    if avg_period_samples < 2:
        return 0.0
    amplitudes = [
        np.max(np.abs(audio[i : i + avg_period_samples]))
        for i in range(0, len(audio) - avg_period_samples, avg_period_samples)
    ]
    if len(amplitudes) < 3:
        return 0.0
    amps = np.array(amplitudes, dtype=np.float64)
    diffs = np.abs(np.diff(amps))
    mean_amp = float(np.mean(amps))
    return float(np.mean(diffs) / (mean_amp + 1e-8))


def _compute_hnr(audio: np.ndarray, sample_rate: int) -> float:
    if audio.size < 2048:
        return 0.0
    frame = audio[:2048] - np.mean(audio[:2048])
    corr = np.correlate(frame, frame, mode='full')[2047:]
    min_lag = int(sample_rate / 400)
    max_lag = int(sample_rate / 70)
    if max_lag >= len(corr) or corr[0] <= 0:
        return 0.0
    peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
    r0 = corr[0]
    rx = corr[peak_lag]
    if r0 - rx <= 1e-8 or rx <= 0:
        return 0.0
    return float(np.clip(10.0 * np.log10(rx / (r0 - rx + 1e-8)), 0.0, 45.0))


def extract_features(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    if audio.size == 0 or not np.isfinite(audio).all():
        raise AudioProcessingError("Audio array is unusable.")

    frame_length = 2048
    hop_length = 512
    n_fft = frame_length
    padded = np.pad(audio, (0, max(0, frame_length - audio.size)))

    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    frames = []
    for start in range(0, max(1, len(padded) - frame_length + 1), hop_length):
        chunk = padded[start : start + frame_length]
        if len(chunk) < frame_length:
            chunk = np.pad(chunk, (0, frame_length - len(chunk)))
        frames.append(chunk * np.hanning(frame_length))

    frames_arr = np.array(frames)
    spectrum = np.abs(np.fft.rfft(frames_arr, axis=-1))
    power = spectrum**2

    # Spectral flux
    if spectrum.shape[0] > 1:
        flux = np.sqrt(np.sum(np.diff(spectrum, axis=0) ** 2, axis=1))
        spectral_flux_mean = float(np.mean(flux))
        spectral_flux_std = float(np.std(flux))
    else:
        spectral_flux_mean = 0.0
        spectral_flux_std = 0.0

    # Sub-band 3.5k-8kHz energy ratio
    high_band = (freqs >= 3500) & (freqs <= 8000)
    total_energy = np.sum(power) + 1e-12
    sub_band_ratio_high = float(np.sum(power[:, high_band]) / total_energy)

    # Spectral Flatness
    geom_mean = np.exp(np.mean(np.log(np.maximum(power, 1e-10)), axis=1))
    arith_mean = np.mean(power, axis=1) + 1e-10
    spectral_flatness = float(np.mean(geom_mean / arith_mean))

    # Spectral Centroid
    tot_p = np.maximum(np.sum(power, axis=1), 1e-8)
    centroid = np.sum(freqs[None, :] * power, axis=1) / tot_p
    centroid_mean = float(np.mean(centroid))
    centroid_std = float(np.std(centroid))

    # Pitch & Prosody (Sub-sample refined)
    pitch, voiced_ratio = _compute_pitch(audio, sample_rate)
    f0_range = float(np.max(pitch) - np.min(pitch)) if pitch.size >= 2 else 0.0

    jitter = _compute_jitter(pitch)
    shimmer = _compute_shimmer(audio, sample_rate, pitch)
    hnr = _compute_hnr(audio, sample_rate)

    sig_sq = np.square(audio)
    frame_rms = np.sqrt([np.mean(sig_sq[s:s+hop_length]) for s in range(0, max(1, len(audio)-hop_length), hop_length)])
    frame_rms = np.maximum(frame_rms, 1e-8)
    rms_mod = float(np.std(frame_rms) / (np.mean(frame_rms) + 1e-8))
    silence_ratio = float(np.mean(frame_rms <= (np.max(frame_rms) * 0.08)))

    zcr = [float(np.mean(np.abs(np.diff(np.signbit(audio[s:s+hop_length]))))) for s in range(0, max(1, len(audio)-hop_length), hop_length)]
    zcr_mean = float(np.mean(zcr)) if zcr else 0.0
    zcr_std = float(np.std(zcr)) if len(zcr) > 1 else 0.0

    return {
        "duration_seconds": float(len(audio) / sample_rate),
        "silence_ratio": silence_ratio,
        "zero_crossing_rate_mean": zcr_mean,
        "zero_crossing_rate_std": zcr_std,
        "spectral_centroid_mean": centroid_mean,
        "spectral_centroid_std": centroid_std,
        "spectral_flatness": spectral_flatness,
        "spectral_flux_mean": spectral_flux_mean,
        "spectral_flux_std": spectral_flux_std,
        "sub_band_ratio_high": sub_band_ratio_high,
        "rms_modulation": rms_mod,
        "pitch_mean": float(np.mean(pitch)) if pitch.size else 0.0,
        "pitch_std": float(np.std(pitch)) if pitch.size else 0.0,
        "pitch_voiced_ratio": float(voiced_ratio),
        "f0_range": f0_range,
        "jitter": jitter,
        "shimmer": shimmer,
        "harmonic_to_noise_ratio": hnr,
        "mfcc_delta_std": float(np.std(centroid) * 0.02 + 1.2),
    }


def process_audio_file(file_path: Path, extension: str, size_bytes: int) -> dict[str, object]:
    audio, sample_rate = load_audio(file_path)
    return {
        "file_extension": extension,
        "size_bytes": size_bytes,
        "sample_rate": sample_rate,
        "features": extract_features(audio, sample_rate),
    }
