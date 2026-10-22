import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4


SAFE_EXTENSION = re.compile(r'^[a-z0-9]+$')
STAGING_PREFIX = '.download-'
MANAGED_AUDIO_PREFIX = 'source.'


@dataclass(frozen=True, slots=True)
class AudioDownloadTarget:
    video_id: str
    token: str
    directory: Path
    output_template: Path


@dataclass(frozen=True, slots=True)
class AudioArtifact:
    path: Path
    extension: str
    size_bytes: int


class AudioStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()

    @staticmethod
    def _uuid(value: str, label: str) -> str:
        try:
            valid = str(UUID(value)) == value
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            raise ValueError(f'Invalid {label}')
        return value

    def _videos_root(self) -> Path:
        return self.data_dir / 'videos'

    def _contained(self, path: Path) -> Path:
        resolved = path.resolve()
        videos_root = self._videos_root()
        if videos_root.resolve() != videos_root or resolved != path:
            raise ValueError('Audio path contains a symbolic link')
        if not resolved.is_relative_to(videos_root):
            raise ValueError('Audio path escapes the videos directory')
        return resolved

    def audio_dir_for(self, video_id: str) -> Path:
        video_id = self._uuid(video_id, 'internal video id')
        return self._contained(self._videos_root() / video_id / 'audio')

    def prepare(self, video_id: str) -> AudioDownloadTarget:
        video_id = self._uuid(video_id, 'internal video id')
        token = str(uuid4())
        audio_dir = self.audio_dir_for(video_id)
        audio_dir.mkdir(parents=True, exist_ok=True)
        directory = self._contained(audio_dir / f'{STAGING_PREFIX}{token}')
        directory.mkdir()
        return AudioDownloadTarget(
            video_id=video_id,
            token=token,
            directory=directory,
            output_template=directory / 'source.%(ext)s',
        )

    def _validate_target(self, video_id: str, target: AudioDownloadTarget) -> Path:
        video_id = self._uuid(video_id, 'internal video id')
        token = self._uuid(target.token, 'audio download token')
        expected = self.audio_dir_for(video_id) / f'{STAGING_PREFIX}{token}'
        if target.video_id != video_id or target.directory != expected:
            raise ValueError('Audio download target does not belong to this video')
        if target.output_template != expected / 'source.%(ext)s':
            raise ValueError('Invalid audio output template')
        return self._contained(expected)

    def finalize(self, video_id: str, target: AudioDownloadTarget,
                 downloaded_path: Path) -> AudioArtifact:
        directory = self._validate_target(video_id, target)
        path = downloaded_path.resolve()
        if path.parent != directory or downloaded_path.is_symlink():
            raise ValueError('Downloaded audio is outside its staging directory')
        if not path.name.startswith(MANAGED_AUDIO_PREFIX):
            raise ValueError('Downloaded audio has an unexpected name')
        extension = path.name.removeprefix(MANAGED_AUDIO_PREFIX).lower()
        if not SAFE_EXTENSION.fullmatch(extension):
            raise ValueError('Downloaded audio has an unsafe extension')
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        if size <= 0:
            raise ValueError('Downloaded audio is empty')
        with path.open('rb') as stream:
            if not stream.read(1):
                raise ValueError('Downloaded audio is unreadable')

        audio_dir = self.audio_dir_for(video_id)
        destination = audio_dir / f'{MANAGED_AUDIO_PREFIX}{extension}'
        path.replace(destination)
        shutil.rmtree(directory, ignore_errors=True)
        for old_path in audio_dir.glob(f'{MANAGED_AUDIO_PREFIX}*'):
            if old_path != destination and old_path.is_file() and not old_path.is_symlink():
                old_path.unlink()
        return AudioArtifact(path=destination, extension=extension, size_bytes=size)

    def load(self, video_id: str) -> AudioArtifact:
        audio_dir = self.audio_dir_for(video_id)
        if not audio_dir.is_dir() or audio_dir.is_symlink():
            raise FileNotFoundError(audio_dir)
        candidates = []
        for path in audio_dir.glob(f'{MANAGED_AUDIO_PREFIX}*'):
            extension = path.name.removeprefix(MANAGED_AUDIO_PREFIX).lower()
            if (SAFE_EXTENSION.fullmatch(extension) and path.is_file()
                    and not path.is_symlink()):
                candidates.append((path, extension))
        if not candidates:
            raise FileNotFoundError('Managed audio artifact does not exist')
        if len(candidates) != 1:
            raise ValueError('Multiple managed audio artifacts exist')
        path, extension = candidates[0]
        size = path.stat().st_size
        if size <= 0:
            raise ValueError('Managed audio artifact is empty')
        with path.open('rb') as stream:
            if not stream.read(1):
                raise ValueError('Managed audio artifact is unreadable')
        return AudioArtifact(path=path, extension=extension, size_bytes=size)

    def discard(self, video_id: str, target: AudioDownloadTarget) -> None:
        directory = self._validate_target(video_id, target)
        if directory.is_dir() and not directory.is_symlink():
            shutil.rmtree(directory)
        self._remove_empty_audio_dir(video_id)

    def cleanup(self, video_id: str) -> None:
        audio_dir = self.audio_dir_for(video_id)
        if not audio_dir.is_dir() or audio_dir.is_symlink():
            return
        for path in audio_dir.iterdir():
            if path.name.startswith(STAGING_PREFIX) and self._valid_staging_name(path.name):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
            elif path.name.startswith(MANAGED_AUDIO_PREFIX):
                extension = path.name.removeprefix(MANAGED_AUDIO_PREFIX).lower()
                if SAFE_EXTENSION.fullmatch(extension) and path.is_file() and not path.is_symlink():
                    path.unlink()
        self._remove_empty_audio_dir(video_id)

    def cleanup_stale_staging(self) -> int:
        videos_root = self._videos_root()
        if not videos_root.is_dir() or videos_root.is_symlink():
            return 0
        removed = 0
        for video_dir in videos_root.iterdir():
            try:
                video_id = self._uuid(video_dir.name, 'internal video id')
                audio_dir = self.audio_dir_for(video_id)
            except ValueError:
                continue
            if not audio_dir.is_dir() or audio_dir.is_symlink():
                continue
            for path in audio_dir.iterdir():
                if (self._valid_staging_name(path.name) and path.is_dir()
                        and not path.is_symlink()):
                    shutil.rmtree(path)
                    removed += 1
            self._remove_empty_audio_dir(video_id)
        return removed

    @staticmethod
    def _valid_staging_name(name: str) -> bool:
        if not name.startswith(STAGING_PREFIX):
            return False
        try:
            return str(UUID(name.removeprefix(STAGING_PREFIX))) == name.removeprefix(STAGING_PREFIX)
        except ValueError:
            return False

    def _remove_empty_audio_dir(self, video_id: str) -> None:
        audio_dir = self.audio_dir_for(video_id)
        try:
            audio_dir.rmdir()
        except (FileNotFoundError, OSError):
            pass
