from pathlib import Path

import pytest
from pydantic import (
    ValidationError,
)

from app.core.config import REPO_ROOT, Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in (
        "APP_ENV", "DATA_DIR", "DATABASE_URL", "CORS_ORIGINS",
        "STT_MODEL", "STT_DEVICE", "STT_COMPUTE_TYPE", "STT_VAD_FILTER",
        "STT_MODEL_PATH",
        "LLM_NORMALIZATION_ENABLED", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL", "DEEPSEEK_TIMEOUT_SECONDS", "DEEPSEEK_MAX_OUTPUT_TOKENS",
        "LLM_NORMALIZATION_SINGLE_CALL_MAX_UNITS",
        "LLM_NORMALIZATION_BATCH_SOFT_UNITS", "LLM_NORMALIZATION_BATCH_HARD_UNITS",
        "LLM_NORMALIZATION_LOOKAHEAD_UNITS",
        "LLM_NORMALIZATION_PREVIOUS_CONTEXT_UNITS",
        "LLM_NORMALIZATION_MAX_VIDEO_UNITS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_defaults_are_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.data_dir == REPO_ROOT / "data"
    assert settings.database_url == f"sqlite:///{REPO_ROOT / 'data/app.db'}"
    assert settings.stt_model == "base.en"
    assert settings.stt_device == "cpu"
    assert settings.stt_compute_type == "int8"
    assert settings.stt_vad_filter is True
    assert settings.stt_model_path == REPO_ROOT / "data/cache/faster-whisper/base.en"
    assert not (tmp_path / "data").exists()


def test_root_dotenv_is_selected_even_from_backend(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Path(Settings.model_config["env_file"]) == REPO_ROOT / ".env"


def test_dotenv_environment_precedence_and_relative_paths(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("DATA_DIR=from-file\nAPP_ENV=from-file\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "from-process")
    settings = Settings(_env_file=dotenv)
    assert settings.app_env == "from-process"
    assert settings.data_dir == REPO_ROOT / "from-file"
    assert settings.database_url == f"sqlite:///{REPO_ROOT / 'from-file/app.db'}"


def test_explicit_database_path_uses_repo_root():
    settings = Settings(_env_file=None, data_dir="assets", database_url="sqlite:///data/custom.db")
    assert settings.data_dir == REPO_ROOT / "assets"
    assert settings.database_url == f"sqlite:///{REPO_ROOT / 'data/custom.db'}"


def test_absolute_paths_and_cors(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path,
                        database_url=f"sqlite:///{tmp_path / 'app.db'}",
                        cors_origins="http://localhost:5173, http://127.0.0.1:5173")
    assert settings.data_dir == tmp_path
    assert settings.database_url == f"sqlite:///{tmp_path / 'app.db'}"
    assert settings.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_stt_model_path_follows_data_dir_and_model(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, stt_model="custom-model")
    assert settings.stt_model_path == tmp_path / "cache/faster-whisper/custom-model"


def test_explicit_stt_model_path_uses_repo_root():
    settings = Settings(_env_file=None, stt_model_path="models/whisper")
    assert settings.stt_model_path == REPO_ROOT / "models/whisper"


@pytest.mark.parametrize("field", ["stt_model", "stt_compute_type"])
def test_rejects_empty_stt_values(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: "  "})


@pytest.mark.parametrize("url", ["postgresql://localhost/app", "sqlite://", "sqlite:///:memory:"])
def test_rejects_unsupported_database_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=url)


def test_retired_cloud_fields_are_ignored_and_excluded_from_diagnostics(tmp_path, monkeypatch):
    dotenv = tmp_path / '.env'
    dotenv.write_text(
        'DATA_DIR=local-data\nLLM_NORMALIZATION_ENABLED=true\n'
        'DEEPSEEK_API_KEY=private-test-key\nDEEPSEEK_BASE_URL=http://invalid.test/path\n'
        'DEEPSEEK_TIMEOUT_SECONDS=not-a-number\n'
        'LLM_NORMALIZATION_BATCH_SOFT_UNITS=invalid\n', encoding='utf-8')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'old-model')
    settings = Settings(_env_file=dotenv)
    assert settings.data_dir == REPO_ROOT / 'local-data'
    assert not any(name.startswith(('deepseek_', 'llm_normalization_'))
                   for name in settings.model_dump())
    assert not any(name.startswith(('DEEPSEEK_', 'LLM_NORMALIZATION_'))
                   for name in settings.safe_diagnostics())
    assert 'private-test-key' not in repr(settings)
    assert 'private-test-key' not in repr(settings.safe_diagnostics())
