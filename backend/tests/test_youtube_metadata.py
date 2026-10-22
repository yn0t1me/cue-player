import asyncio
from threading import get_ident

import pytest

from app.services.youtube import metadata


def test_fetch_metadata_moves_extraction_off_the_event_loop(monkeypatch):
    caller_thread = get_ident()

    def extract(url):
        assert url == 'https://www.youtube.com/watch?v=aB3_dE-fGhI'
        assert get_ident() != caller_thread
        return metadata.YouTubeMetadata(
            video_id='aB3_dE-fGhI', title='A useful lesson', channel_title='Teacher',
            duration=92.5, thumbnail_url='https://img.test/lesson.jpg')

    monkeypatch.setattr(metadata, '_fetch_metadata_sync', extract)
    result = asyncio.run(metadata.fetch_metadata('https://www.youtube.com/watch?v=aB3_dE-fGhI'))
    assert result.title == 'A useful lesson'


def test_sync_metadata_maps_only_the_domain_fields(monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, options):
            assert options['skip_download'] is True
            assert options['noplaylist'] is True
            assert options['socket_timeout'] == 15

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            assert download is False
            return {
                'id': 'aB3_dE-fGhI', 'title': '  Lesson title  ', 'channel': 'Channel',
                'duration': 61, 'thumbnail': 'https://img.test/thumb.jpg',
                'formats': [object()],
            }

    monkeypatch.setattr(metadata, 'YoutubeDL', FakeYoutubeDL)
    result = metadata._fetch_metadata_sync('https://www.youtube.com/watch?v=aB3_dE-fGhI')
    assert result == metadata.YouTubeMetadata(
        video_id='aB3_dE-fGhI', title='Lesson title', channel_title='Channel',
        duration=61.0, thumbnail_url='https://img.test/thumb.jpg')


@pytest.mark.parametrize('info', [None, {}, {'id': 'aB3_dE-fGhI'}, {'title': 'Missing id'}])
def test_sync_metadata_rejects_incomplete_results(monkeypatch, info):
    class FakeYoutubeDL:
        def __init__(self, _options): pass
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def extract_info(self, _url, download): return info

    monkeypatch.setattr(metadata, 'YoutubeDL', FakeYoutubeDL)
    with pytest.raises(metadata.MetadataFetchError):
        metadata._fetch_metadata_sync('https://www.youtube.com/watch?v=aB3_dE-fGhI')
