import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.youtube import playlists


@pytest.mark.parametrize('url,playlist_id', [
    ('https://www.youtube.com/playlist?list=PL123', 'PL123'),
    ('https://youtube.com/watch?v=abcdefghijk&list=PL123&t=5', 'PL123'),
    ('https://youtu.be/abcdefghijk?list=PL123', 'PL123'),
    ('http://m.youtube.com/playlist/?list=UU123', 'UU123'),
])
def test_normalize_playlist_url(url, playlist_id):
    assert playlists.normalize_playlist_url(url) == (playlist_id, f'https://www.youtube.com/playlist?list={playlist_id}')


@pytest.mark.parametrize('url', [
    'https://evil.test/playlist?list=PL123', 'https://youtube.com.evil.test/playlist?list=PL123',
    'https://user:password@youtube.com/playlist?list=PL123', 'https://youtube.com:999/playlist?list=PL123',
    'https://youtube.com/playlist?list=', 'https://youtube.com/playlist?list=PL123&list=PL456',
    'https://youtube.com/playlist?list=%2fetc', 'https://youtube.com/channel/foo?list=PL123',
    'https://youtube.com/playlist?list=PL123\n', 'https://youtube.com/playlist',
    'https://youtube.com:invalid/playlist?list=PL123', 'https://youtu.be/no?list=PL123',
])
def test_reject_invalid_playlist_urls(url):
    with pytest.raises(ValueError): playlists.normalize_playlist_url(url)


def stub_downloader(monkeypatch, info, *, warning=None):
    calls = []
    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            calls.append(options)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert url == 'https://www.youtube.com/playlist?list=PL123'
            assert download is False
            if warning: self.options['logger'].warning(warning)
            return info
    monkeypatch.setattr(playlists, 'YoutubeDL', FakeDownloader)
    return calls


def test_flat_snapshot_preserves_unknown_metadata_and_restricted_entries(monkeypatch):
    info = {'_type': 'playlist', 'id': 'PL123', 'title': 'Series', 'playlist_count': 4,
            'entries': [
                {'id': 'abcdefghijk', 'title': 'One', 'duration': 12, 'thumbnails': [{'url': 'https://img.test/x'}]},
                {'id': 'lmnopqrstuv', 'title': '[Private video]', 'availability': None},
                {'id': 'zyxwvutsrqp', 'title': None, 'duration': None},
                {'id': 'abcdefghijk', 'title': 'duplicate'},
            ]}
    calls = stub_downloader(monkeypatch, info)
    result = playlists._fetch_playlist_sync('https://youtube.com/playlist?list=PL123')
    assert len(result.entries) == 4
    assert [e.unavailable for e in result.entries] == [False, True, False, False]
    assert result.entries[1].title is None
    assert result.entries[2].video_id == 'zyxwvutsrqp' and result.entries[2].title is None
    assert calls[0]['playlistend'] == 201 and calls[0]['cachedir'] is False
    assert calls[0]['skip_download'] and not calls[0]['writesubtitles']


@pytest.mark.parametrize('info,exception', [
    (None, playlists.PlaylistFetchError),
    ({'_type': 'url', 'id': 'PL123'}, playlists.PlaylistFetchError),
    ({'_type': 'playlist', 'id': 'other'}, playlists.PlaylistFetchError),
    ({'_type': 'playlist', 'id': 'PL123', 'playlist_count': 20000}, playlists.PlaylistLimitError),
    ({'_type': 'playlist', 'id': 'PL123', 'entries': [{'id': 'abcdefghijk'}] * 201}, playlists.PlaylistLimitError),
    ({'_type': 'playlist', 'id': 'PL123', 'playlist_count': 2, 'entries': [{'id': 'abcdefghijk'}]}, playlists.PlaylistFetchError),
    ({'_type': 'playlist', 'id': 'PL123', 'entries': [None]}, playlists.PlaylistFetchError),
    ({'_type': 'playlist', 'id': 'PL123', 'entries': [{'id': 'abcdefghijk'}], 'requested_entries': [2]}, playlists.PlaylistFetchError),
])
def test_incomplete_and_oversized_snapshot_rejected(monkeypatch, info, exception):
    stub_downloader(monkeypatch, info)
    with pytest.raises(exception): playlists._fetch_playlist_sync('https://youtube.com/playlist?list=PL123')


def test_nonfatal_upstream_warning_is_not_partial_success(monkeypatch):
    stub_downloader(monkeypatch, {'_type': 'playlist', 'id': 'PL123', 'entries': []}, warning='hidden videos')
    with pytest.raises(playlists.PlaylistFetchError):
        playlists._fetch_playlist_sync('https://youtube.com/playlist?list=PL123')


def test_empty_snapshot(monkeypatch):
    stub_downloader(monkeypatch, {'_type': 'playlist', 'id': 'PL123', 'playlist_count': None, 'entries': []})
    assert playlists._fetch_playlist_sync('https://youtube.com/playlist?list=PL123').entries == []


@pytest.mark.parametrize('cancel', [True, False])
def test_stopped_extractor_is_killed_and_reaped(monkeypatch, cancel):
    async def run():
        started = asyncio.Event()
        class Process:
            returncode = None
            killed = False
            calls = 0
            async def communicate(self):
                self.calls += 1
                if self.calls == 1:
                    started.set()
                    await asyncio.Event().wait()
                self.returncode = -9
                return b'', None
            def kill(self): self.killed = True
        process = Process()
        async def spawn(*args, **kwargs):
            assert args[:3] == (playlists.sys.executable, '-m', 'app.services.youtube.playlists')
            return process
        monkeypatch.setattr(playlists.asyncio, 'create_subprocess_exec', spawn)
        if not cancel:
            original_wait_for = asyncio.wait_for
            async def quick_timeout(coro, timeout):
                return await original_wait_for(coro, timeout=0.01)
            monkeypatch.setattr(playlists.asyncio, 'wait_for', quick_timeout)
        task = asyncio.create_task(playlists.fetch_playlist('https://youtube.com/playlist?list=PL123'))
        await started.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError): await task
        assert process.killed and process.returncode == -9 and process.calls == 2
    asyncio.run(run())


@pytest.mark.parametrize('output,exception', [
    (b'{"error":"limit"}', playlists.PlaylistLimitError),
    (b'{"error":"fetch"}', playlists.PlaylistFetchError),
    (b'not json', playlists.PlaylistFetchError),
    (b'null', playlists.PlaylistFetchError),
    (b'[]', playlists.PlaylistFetchError),
])
def test_worker_errors_are_safe(monkeypatch, output, exception):
    async def communicate(): return output, None
    async def spawn(*args, **kwargs): return SimpleNamespace(returncode=0, communicate=communicate)
    monkeypatch.setattr(playlists.asyncio, 'create_subprocess_exec', spawn)
    with pytest.raises(exception):
        asyncio.run(playlists.fetch_playlist('https://youtube.com/playlist?list=PL123'))
