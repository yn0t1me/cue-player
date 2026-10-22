"""Repository-relative configuration; independent of the process working directory."""

from pathlib import Path
from typing import Literal

from pydantic import (
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    data_dir: Path = Path("data")
    database_url: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    stt_model: str = "base.en"
    stt_device: Literal["cpu", "cuda"] = "cpu"
    stt_compute_type: str = "int8"
    stt_vad_filter: bool = True
    stt_model_path: Path | None = None

    @field_validator("stt_model", "stt_compute_type")
    @classmethod
    def require_nonempty_stt_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Model and compute type values must not be empty")
        return value

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        self.data_dir = (REPO_ROOT / self.data_dir.expanduser()).resolve()
        if self.stt_model_path is None:
            self.stt_model_path = self.data_dir / "cache" / "faster-whisper" / self.stt_model
        else:
            self.stt_model_path = (REPO_ROOT / self.stt_model_path.expanduser()).resolve()
        if self.database_url is None:
            database_path = self.data_dir / "app.db"
        else:
            prefix = "sqlite:///"
            if not self.database_url.startswith(prefix):
                raise ValueError("DATABASE_URL must be a file-based sqlite:/// URL")
            raw_path = self.database_url[len(prefix):]
            if not raw_path or raw_path == ":memory:" or "?" in raw_path or "#" in raw_path:
                raise ValueError("DATABASE_URL requires a file path without query or fragment")
            database_path = (REPO_ROOT / Path(raw_path).expanduser()).resolve()
        self.database_url = f"sqlite:///{database_path}"
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_path(self) -> Path:
        return Path(self.database_url.removeprefix('sqlite:///'))

    def safe_diagnostics(self) -> dict[str, str | Path]:
        """Return the active local configuration without retired cloud fields."""
        return {
            "DATA_DIR": self.data_dir,
            "DATABASE_URL": self.database_url,
            "STT_MODEL": self.stt_model,
            "STT_DEVICE": self.stt_device,
            "STT_COMPUTE_TYPE": self.stt_compute_type,
            "STT_MODEL_PATH": self.stt_model_path,
        }


if __name__ == "__main__":
    settings = Settings()
    for name, value in settings.safe_diagnostics().items():
        print(f"{name}={value}")
