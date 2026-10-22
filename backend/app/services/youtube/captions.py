import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.enums import SubtitlePreference, SubtitleSource

MAX_CAPTION_BYTES = 5 * 1024 * 1024
ENGLISH_CODE = re.compile(r'^en(?:[-_][a-z0-9]+)*$', re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CaptionCandidate:
    source: SubtitleSource
    language: str
    language_name: str | None
    url: str
    extension: str


class CaptionDiscoveryError(Exception):
    pass


class CaptionDownloadError(Exception):
    pass


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _is_english(language: str) -> bool:
    return ENGLISH_CODE.fullmatch(language) is not None


def _is_translation(url: str) -> bool:
    return 'tlang' in parse_qs(urlparse(url).query, keep_blank_values=True)


def _extract_caption_info(video_url: str) -> Mapping[str, Any]:
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
            info = downloader.extract_info(video_url, download=False)
    except (DownloadError, OSError, TimeoutError) as error:
        raise CaptionDiscoveryError(str(error)) from error
    if not isinstance(info, Mapping):
        raise CaptionDiscoveryError('yt-dlp returned no caption information')
    return info


async def discover_captions(video_url: str) -> list[CaptionCandidate]:
    info = await asyncio.to_thread(_extract_caption_info, video_url)
    candidates = []
    for collection_name, source in (
        ('subtitles', SubtitleSource.YOUTUBE_MANUAL),
        ('automatic_captions', SubtitleSource.YOUTUBE_AUTO),
    ):
        tracks = info.get(collection_name)
        if not isinstance(tracks, Mapping):
            continue
        for language, formats in tracks.items():
            if (not isinstance(language, str) or not _is_english(language)
                    or not isinstance(formats, Sequence)):
                continue
            for item in formats:
                if not isinstance(item, Mapping):
                    continue
                url = _text(item.get('url'))
                extension = _text(item.get('ext'))
                if url is None or extension is None or _is_translation(url):
                    continue
                candidates.append(CaptionCandidate(
                    source=source,
                    language=language,
                    language_name=_text(item.get('name')),
                    url=url,
                    extension=extension.lower(),
                ))
    return candidates


def _language_rank(language: str) -> tuple[int, str]:
    normalized = language.lower().replace('_', '-')
    preferred = {'en': 0, 'en-orig': 1, 'en-us': 2, 'en-gb': 3}
    return preferred.get(normalized, 4), normalized


def select_best_caption(
    candidates: Sequence[CaptionCandidate],
    preference: SubtitlePreference = SubtitlePreference.MANUAL_FIRST,
) -> CaptionCandidate | None:
    preference = SubtitlePreference(preference)
    source_rank = {
        SubtitleSource.YOUTUBE_MANUAL: 0,
        SubtitleSource.YOUTUBE_AUTO: 1,
    }
    eligible = [
        (index, candidate) for index, candidate in enumerate(candidates)
        if candidate.source in source_rank
        and (preference != SubtitlePreference.AUTO_ONLY
             or candidate.source == SubtitleSource.YOUTUBE_AUTO)
        and _is_english(candidate.language)
        and candidate.extension.lower() == 'vtt'
        and not _is_translation(candidate.url)
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda item: (
        source_rank[item[1].source], *_language_rank(item[1].language), item[0]
    ))[1]


async def download_caption(candidate: CaptionCandidate,
                           client: httpx.AsyncClient | None = None) -> bytes:
    owns_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(20, connect=10))
    try:
        async with client.stream('GET', candidate.url) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_CAPTION_BYTES:
                    raise CaptionDownloadError('caption response was too large')
    except httpx.HTTPError as error:
        raise CaptionDownloadError(str(error)) from error
    finally:
        if owns_client:
            await client.aclose()
    if not content:
        raise CaptionDownloadError('caption response was empty')
    content = bytes(content)
    header = content.lstrip(b'\xef\xbb\xbf \t\r\n')
    if not header.startswith(b'WEBVTT'):
        raise CaptionDownloadError('caption response was not WebVTT')
    return content
