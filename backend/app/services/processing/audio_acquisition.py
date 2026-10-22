import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.services.processing.audio_store import AudioArtifact, AudioStore
from app.services.youtube.audio import DownloadedAudio, download_audio


AudioDownloader = Callable[[str, Path], Awaitable[DownloadedAudio]]


class AudioAcquirer:
    def __init__(self, store: AudioStore, downloader: AudioDownloader | None = None):
        self.store = store
        self.downloader = downloader or download_audio

    async def acquire(self, video_id: str, video_url: str) -> AudioArtifact:
        target = await asyncio.to_thread(self.store.prepare, video_id)
        try:
            downloaded = await self.downloader(video_url, target.output_template)
            return await asyncio.to_thread(
                self.store.finalize, video_id, target, downloaded.path)
        except (asyncio.CancelledError, Exception):
            await asyncio.to_thread(self.store.discard, video_id, target)
            raise
