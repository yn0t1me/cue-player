"""Read a bounded playlist snapshot in a cancellable, media-free subprocess."""
import asyncio
from dataclasses import asdict, dataclass
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from yt_dlp import YoutubeDL

from app.services.youtube.metadata import _duration, _text

MAX_PLAYLIST_ITEMS = 200


class PlaylistFetchError(Exception):
    pass


class PlaylistLimitError(PlaylistFetchError):
    pass


@dataclass(frozen=True)
class PlaylistEntry:
    video_id: str | None
    title: str | None
    duration: float | None
    thumbnail_url: str | None
    unavailable: bool = False


@dataclass(frozen=True)
class PlaylistSnapshot:
    playlist_id: str
    url: str
    title: str | None
    entries: list[PlaylistEntry]


def normalize_playlist_url(url: str) -> tuple[str, str]:
    if len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid playlist URL')
    parsed = urlsplit(url.strip())
    hosts = ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be')
    if (parsed.scheme not in ('http', 'https') or parsed.hostname not in hosts
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443 if parsed.scheme == 'https' else 80)):
        raise ValueError('Invalid playlist host')
    path = parsed.path.rstrip('/')
    if parsed.hostname in ('youtu.be', 'www.youtu.be'):
        valid_path = bool(re.fullmatch(r'/[A-Za-z0-9_-]{11}', path))
    else:
        valid_path = path in ('/playlist', '/watch')
    values = parse_qs(parsed.query, keep_blank_values=True).get('list', [])
    if (not valid_path or len(values) != 1
            or not re.fullmatch(r'[A-Za-z0-9_-]{2,200}', values[0])):
        raise ValueError('Invalid playlist identifier')
    return values[0], f'https://www.youtube.com/playlist?list={values[0]}'


class _PlaylistLogger:
    def __init__(self):
        self.incomplete = False

    def debug(self, _message):
        pass

    def warning(self, _message):
        # Nonfatal reload/pagination failures must not turn into partial success.
        self.incomplete = True

    def error(self, _message):
        self.incomplete = True


def _fetch_playlist_sync(url: str) -> PlaylistSnapshot:
    playlist_id, url = normalize_playlist_url(url)
    logger = _PlaylistLogger()
    options = dict(extract_flat='in_playlist', skip_download=True, lazy_playlist=True,
                   playlistend=MAX_PLAYLIST_ITEMS + 1, cachedir=False, quiet=True,
                   logger=logger, socket_timeout=12, retries=0, extractor_retries=0,
                   writesubtitles=False, writeautomaticsub=False, writethumbnail=False,
                   writeinfojson=False)
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
    if not isinstance(info, dict) or info.get('_type') != 'playlist' or info.get('id') != playlist_id:
        raise PlaylistFetchError('Unexpected playlist result')
    total = info.get('playlist_count')
    if isinstance(total, int) and total > MAX_PLAYLIST_ITEMS:
        raise PlaylistLimitError('Playlist limit exceeded')
    entries = []
    for raw in info.get('entries') or []:
        if len(entries) >= MAX_PLAYLIST_ITEMS:
            raise PlaylistLimitError('Playlist limit exceeded')
        if not isinstance(raw, dict):
            raise PlaylistFetchError('Incomplete playlist entry')
        video_id = _text(raw.get('id'))
        if video_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            video_id = None
        title = _text(raw.get('title'))
        unavailable = video_id is None or title in ('[Private video]', '[Deleted video]') or raw.get('availability') in (
            'private', 'premium_only', 'subscriber_only', 'needs_auth')
        thumbnails = raw.get('thumbnails') or []
        thumbnail = next((_text(t.get('url')) for t in reversed(thumbnails)
                          if isinstance(t, dict) and _text(t.get('url'))), None)
        entries.append(PlaylistEntry(video_id, None if unavailable else title,
                                     _duration(raw.get('duration')), thumbnail, unavailable))
    if logger.incomplete or (isinstance(total, int) and total != len(entries)):
        raise PlaylistFetchError('Incomplete playlist snapshot')
    requested = info.get('requested_entries')
    if requested is not None and requested != list(range(1, len(entries) + 1)):
        raise PlaylistFetchError('Playlist position gap')
    return PlaylistSnapshot(playlist_id, url, _text(info.get('title')), entries)


async def fetch_playlist(url: str) -> PlaylistSnapshot:
    """Kill the extractor on timeout/cancellation; no abandoned worker threads."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'app.services.youtube.playlists', url,
        cwd=Path(__file__).resolve().parents[3],
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=45)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    try:
        data = json.loads(output)
        if not isinstance(data, dict):
            raise ValueError('Invalid worker result')
        if data.get('error') == 'limit':
            raise PlaylistLimitError('Playlist limit exceeded')
        if process.returncode or data.get('error'):
            raise PlaylistFetchError('Unable to fetch playlist')
        return PlaylistSnapshot(data['playlist_id'], data['url'], data['title'],
                                [PlaylistEntry(**e) for e in data['entries']])
    except (ValueError, KeyError, TypeError) as error:
        raise PlaylistFetchError('Invalid playlist response') from error


if __name__ == '__main__':
    try:
        print(json.dumps(asdict(_fetch_playlist_sync(sys.argv[1])), ensure_ascii=False))
    except PlaylistLimitError:
        print(json.dumps({'error': 'limit'}))
    except Exception:
        # Upstream diagnostics and URLs never escape into the worker response.
        print(json.dumps({'error': 'fetch'}))
