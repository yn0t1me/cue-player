import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


@dataclass(frozen=True, slots=True)
class YouTubeMetadata:
    video_id: str
    title: str
    channel_title: str | None
    duration: float | None
    thumbnail_url: str | None


class MetadataFetchError(Exception):
    """The external metadata result cannot be acquired or trusted."""


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _duration(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    duration = float(value)
    return duration if isfinite(duration) and duration >= 0 else None


def _fetch_metadata_sync(url: str) -> YouTubeMetadata:
    options = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'retries': 1,
        'extractor_retries': 1,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
    except DownloadError as error:
        raise MetadataFetchError(str(error)) from error
    except (OSError, TimeoutError) as error:
        raise MetadataFetchError(str(error)) from error

    if not isinstance(info, Mapping):
        raise MetadataFetchError('yt-dlp returned no video information')
    video_id = _text(info.get('id'))
    title = _text(info.get('title'))
    if video_id is None or title is None:
        raise MetadataFetchError('yt-dlp returned incomplete video information')
    return YouTubeMetadata(
        video_id=video_id,
        title=title,
        channel_title=_text(info.get('channel')) or _text(info.get('uploader')),
        duration=_duration(info.get('duration')),
        thumbnail_url=_text(info.get('thumbnail')),
    )


async def fetch_metadata(url: str) -> YouTubeMetadata:
    return await asyncio.to_thread(_fetch_metadata_sync, url)
