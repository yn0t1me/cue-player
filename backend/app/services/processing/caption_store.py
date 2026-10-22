from pathlib import Path
from uuid import UUID


class CaptionStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def path_for(self, video_id: str) -> Path:
        try:
            valid_id = str(UUID(video_id)) == video_id
        except ValueError:
            valid_id = False
        if not valid_id:
            raise ValueError('Invalid internal video id')
        return self.data_dir / 'videos' / video_id / 'raw' / 'caption.vtt'

    def save(self, video_id: str, content: bytes) -> Path:
        destination = self.path_for(video_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.vtt.tmp')
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def load(self, video_id: str) -> bytes:
        return self.path_for(video_id).read_bytes()
