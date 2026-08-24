from pathlib import Path
import tempfile

from fastapi import UploadFile
import librosa
import numpy as np

UPLOAD_DIRECTORY = Path(__file__).parent / "uploads"
MAX_AUDIO_FILE_SIZE = 25 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = {
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


def validate_audio_metadata(filename: str | None, content_type: str | None) -> str:
    if not filename:
        raise AudioValidationError("Please upload an audio file.")

    extension = Path(filename).suffix.lower()
    allowed_types = SUPPORTED_AUDIO_TYPES.get(extension)
    if allowed_types is None:
        raise AudioValidationError("Unsupported audio format.")

    if content_type and content_type.lower() not in allowed_types:
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
                raise AudioValidationError("Audio file is too large.")
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


def load_audio(file_path: Path, sample_rate: int = 16_000) -> tuple[np.ndarray, int]:
    try:
        audio, loaded_sample_rate = librosa.load(
            file_path,
            sr=sample_rate,
            mono=True,
            duration=120,
        )
    except Exception as error:
        raise AudioProcessingError("Unable to decode this audio recording.") from error

    if audio.size == 0 or not np.isfinite(audio).all():
        raise AudioProcessingError("The audio recording contains no usable samples.")

    return audio.astype(np.float32, copy=False), loaded_sample_rate


def _safe_statistics(values: np.ndarray, prefix: str) -> dict[str, float]:
    finite_values = np.asarray(values, dtype=np.float64)
    finite_values = finite_values[np.isfinite(finite_values)]
    if finite_values.size == 0:
        return {f"{prefix}_mean": 0.0, f"{prefix}_std": 0.0}
    return {
        f"{prefix}_mean": float(np.mean(finite_values)),
        f"{prefix}_std": float(np.std(finite_values)),
    }


def extract_features(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    if audio.size == 0 or not np.isfinite(audio).all():
        raise AudioProcessingError("The audio recording contains no usable samples.")

    minimum_length = 2048
    analysis_audio = np.pad(audio, (0, max(0, minimum_length - audio.size)))
    hop_length = 512

    mfcc = librosa.feature.mfcc(y=analysis_audio, sr=sample_rate, n_mfcc=13, n_fft=minimum_length, hop_length=hop_length)
    mel_spectrogram = librosa.feature.melspectrogram(y=analysis_audio, sr=sample_rate, n_fft=minimum_length, hop_length=hop_length, n_mels=40)
    log_mel = librosa.power_to_db(mel_spectrogram, ref=np.max)
    spectral_contrast = librosa.feature.spectral_contrast(y=analysis_audio, sr=sample_rate, n_fft=minimum_length, hop_length=hop_length)
    spectral_centroid = librosa.feature.spectral_centroid(y=analysis_audio, sr=sample_rate, n_fft=minimum_length, hop_length=hop_length)
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=analysis_audio, sr=sample_rate, n_fft=minimum_length, hop_length=hop_length)
    spectral_rolloff = librosa.feature.spectral_rolloff(y=analysis_audio, sr=sample_rate, n_fft=minimum_length, hop_length=hop_length)
    zero_crossing_rate = librosa.feature.zero_crossing_rate(analysis_audio, hop_length=hop_length)
    rms_energy = librosa.feature.rms(y=analysis_audio, frame_length=minimum_length, hop_length=hop_length)

    pitch_audio = np.pad(analysis_audio, (0, max(0, sample_rate - analysis_audio.size)))
    try:
        pitch = librosa.yin(pitch_audio, fmin=65, fmax=500, sr=sample_rate, frame_length=minimum_length, hop_length=hop_length)
    except Exception:
        pitch = np.array([], dtype=np.float32)

    frame_rms = rms_energy[0]
    silence_threshold = max(float(np.max(frame_rms)) * 0.08, 1e-4)
    silence_ratio = float(np.mean(frame_rms <= silence_threshold))
    active_frames = frame_rms > silence_threshold
    pause_count = int(np.sum(np.diff(active_frames.astype(np.int8)) == -1))

    features: dict[str, float] = {
        "duration_seconds": float(audio.size / sample_rate),
        "silence_ratio": silence_ratio,
        "pause_count": float(pause_count),
        "peak_amplitude": float(np.max(np.abs(audio))),
    }
    for index, values in enumerate(mfcc):
        features.update(_safe_statistics(values, f"mfcc_{index + 1}"))
    for name, values in (
        ("mel", log_mel),
        ("spectral_contrast", spectral_contrast),
        ("spectral_centroid", spectral_centroid),
        ("spectral_bandwidth", spectral_bandwidth),
        ("spectral_rolloff", spectral_rolloff),
        ("zero_crossing_rate", zero_crossing_rate),
        ("rms_energy", rms_energy),
    ):
        features.update(_safe_statistics(values, name))
    features.update(_safe_statistics(pitch, "pitch"))
    features["pitch_voiced_ratio"] = float(np.mean(np.isfinite(pitch))) if pitch.size else 0.0

    return {name: float(np.nan_to_num(value)) for name, value in features.items()}


def process_audio_file(file_path: Path, extension: str, size_bytes: int) -> dict[str, object]:
    audio, sample_rate = load_audio(file_path)
    return {
        "file_extension": extension,
        "size_bytes": size_bytes,
        "sample_rate": sample_rate,
        "features": extract_features(audio, sample_rate),
    }
