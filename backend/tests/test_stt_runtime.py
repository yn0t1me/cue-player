from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.transcript import stt_runtime
from app.services.transcript.stt_runtime import STTRuntimeError, inspect_stt_runtime


def make_model_dir(path: Path) -> Path:
    path.mkdir()
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        (path / name).touch()
    return path


def test_runtime_reports_locked_cpu_capabilities(tmp_path):
    model_path = make_model_dir(tmp_path / "model")
    info = inspect_stt_runtime(Settings(_env_file=None, stt_model_path=model_path))

    assert info.faster_whisper_version
    assert info.ctranslate2_version
    assert info.device == "cpu"
    assert info.compute_type == "int8"
    assert "int8" in info.supported_compute_types
    assert info.model_path == model_path


def test_runtime_rejects_missing_dependency(monkeypatch):
    original_find_spec = stt_runtime.find_spec
    monkeypatch.setattr(
        stt_runtime,
        "find_spec",
        lambda name: None if name == "faster_whisper" else original_find_spec(name),
    )

    with pytest.raises(STTRuntimeError, match="Missing STT dependency 'faster_whisper'"):
        inspect_stt_runtime(Settings(_env_file=None))


def test_runtime_rejects_incomplete_model_cache(tmp_path):
    model_path = tmp_path / "incomplete"
    model_path.mkdir()

    with pytest.raises(STTRuntimeError, match="model cache is incomplete"):
        inspect_stt_runtime(Settings(_env_file=None, stt_model_path=model_path))


def test_runtime_rejects_unsupported_compute_type(tmp_path):
    model_path = make_model_dir(tmp_path / "model")

    with pytest.raises(STTRuntimeError, match="is unavailable on cpu"):
        inspect_stt_runtime(Settings(
            _env_file=None,
            stt_model_path=model_path,
            stt_compute_type="not-a-compute-type",
        ))
