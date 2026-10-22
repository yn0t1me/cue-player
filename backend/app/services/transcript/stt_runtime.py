"""Fail-fast checks for the local STT runtime; the import pipeline does not use this yet."""

from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType

from app.core.config import Settings


class STTRuntimeError(RuntimeError):
    """The configured local STT runtime is not ready."""


@dataclass(frozen=True, slots=True)
class STTRuntimeInfo:
    faster_whisper_version: str
    ctranslate2_version: str
    device: str
    compute_type: str
    supported_compute_types: tuple[str, ...]
    model_path: Path


def _load_dependency(name: str) -> ModuleType:
    if find_spec(name) is None:
        raise STTRuntimeError(
            f"Missing STT dependency {name!r}; run the locked backend installation."
        )
    return import_module(name)


def _validate_model_path(path: Path) -> None:
    required = ("config.json", "model.bin", "tokenizer.json")
    missing = [name for name in required if not (path / name).is_file()]
    has_vocabulary = any(path.glob("vocabulary.*"))
    if missing or not has_vocabulary:
        if not has_vocabulary:
            missing.append("vocabulary.*")
        details = ", ".join(missing)
        raise STTRuntimeError(
            f"STT model cache is incomplete at {path}; missing: {details}."
        )


def inspect_stt_runtime(settings: Settings) -> STTRuntimeInfo:
    """Validate packages, configured compute type, and an offline model directory."""
    faster_whisper = _load_dependency("faster_whisper")
    ctranslate2 = _load_dependency("ctranslate2")

    if settings.stt_device == "cuda" and ctranslate2.get_cuda_device_count() < 1:
        raise STTRuntimeError("STT_DEVICE=cuda but CTranslate2 found no CUDA device.")

    supported = tuple(sorted(ctranslate2.get_supported_compute_types(settings.stt_device)))
    if settings.stt_compute_type not in supported:
        raise STTRuntimeError(
            f"STT_COMPUTE_TYPE={settings.stt_compute_type!r} is unavailable on "
            f"{settings.stt_device}; supported: {', '.join(supported)}."
        )

    model_path = settings.stt_model_path
    if model_path is None:  # Kept explicit for type narrowing and defensive callers.
        raise STTRuntimeError("STT_MODEL_PATH could not be resolved.")
    _validate_model_path(model_path)

    return STTRuntimeInfo(
        faster_whisper_version=faster_whisper.__version__,
        ctranslate2_version=ctranslate2.__version__,
        device=settings.stt_device,
        compute_type=settings.stt_compute_type,
        supported_compute_types=supported,
        model_path=model_path,
    )


if __name__ == "__main__":
    info = inspect_stt_runtime(Settings())
    print(f"faster-whisper={info.faster_whisper_version}")
    print(f"ctranslate2={info.ctranslate2_version}")
    print(f"device={info.device}")
    print(f"compute_type={info.compute_type}")
    print(f"supported_compute_types={','.join(info.supported_compute_types)}")
    print(f"model_path={info.model_path}")
