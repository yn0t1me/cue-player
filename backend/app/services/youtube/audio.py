import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


@dataclass(frozen=True, slots=True)
class DownloadedAudio:
    path: Path
    extension: str
    format_id: str | None
    audio_codec: str | None


class AudioDownloadError(Exception):
    pass


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _selected_format(info: Mapping[str, Any]) -> Mapping[str, Any]:
    requested = info.get('requested_downloads')
    if isinstance(requested, Sequence) and not isinstance(requested, (str, bytes)):
        entries = [item for item in requested if isinstance(item, Mapping)]
        if len(entries) == 1:
            return entries[0]
    return info


def _find_downloaded_file(output_template: Path) -> Path:
    directory = output_template.parent
    completed = [
        path for path in directory.glob('source.*')
        if path.is_file() and not path.is_symlink()
        and not path.name.endswith(('.part', '.ytdl'))
    ]
    if len(completed) != 1:
        raise AudioDownloadError('yt-dlp did not produce exactly one completed audio file')
    return completed[0]


def _download_audio(video_url: str, output_template: Path) -> DownloadedAudio:
    options = {
        'format': 'bestaudio',
        'outtmpl': str(output_template),
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'retries': 1,
        'extractor_retries': 1,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(video_url, download=True)
    except (DownloadError, OSError, TimeoutError) as error:
        raise AudioDownloadError(str(error)) from error
    if not isinstance(info, Mapping):
        raise AudioDownloadError('yt-dlp returned no audio information')

    selected = _selected_format(info)
    if _text(selected.get('vcodec')) != 'none':
        raise AudioDownloadError('yt-dlp selected a format containing video')
    audio_codec = _text(selected.get('acodec'))
    if audio_codec is None or audio_codec == 'none':
        raise AudioDownloadError('yt-dlp selected a format without audio')

    path = _find_downloaded_file(output_template)
    extension = path.suffix.removeprefix('.').lower()
    if not extension:
        raise AudioDownloadError('downloaded audio had no file extension')
    return DownloadedAudio(
        path=path,
        extension=extension,
        format_id=_text(selected.get('format_id')),
        audio_codec=audio_codec,
    )


async def download_audio(video_url: str, output_template: Path) -> DownloadedAudio:
    return await asyncio.to_thread(_download_audio, video_url, output_template)
