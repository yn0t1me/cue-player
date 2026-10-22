import asyncio
import threading
from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError

from app.services.youtube import audio


def test_download_requests_one_audio_only_stream_and_reports_actual_file(tmp_path, monkeypatch):
    called = {}
    main_thread = threading.get_ident()

    class FakeYoutubeDL:
        def __init__(self, options):
            called['options'] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, url, download):
            called.update(url=url, download=download, thread=threading.get_ident())
            Path(called['options']['outtmpl'].replace('%(ext)s', 'webm')).write_bytes(b'audio')
            return {'requested_downloads': [{
                'vcodec': 'none', 'acodec': 'opus', 'format_id': '251',
            }]}

    monkeypatch.setattr(audio, 'YoutubeDL', FakeYoutubeDL)
    staging = tmp_path / 'staging'
    staging.mkdir()
    result = asyncio.run(audio.download_audio(
        'https://www.youtube.com/watch?v=BaW_jenozKc', staging / 'source.%(ext)s'))

    assert called['options']['format'] == 'bestaudio'
    assert called['options']['noplaylist'] is True
    assert called['options']['noprogress'] is True
    assert 'postprocessors' not in called['options']
    assert called['download'] is True
    assert called['thread'] != main_thread
    assert result == audio.DownloadedAudio(staging / 'source.webm', 'webm', '251', 'opus')


@pytest.mark.parametrize('selected, message', [
    ({'vcodec': 'vp9', 'acodec': 'opus'}, 'containing video'),
    ({'vcodec': 'none', 'acodec': 'none'}, 'without audio'),
])
def test_download_rejects_non_audio_only_results(tmp_path, monkeypatch, selected, message):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, _url, download):
            Path(self.options['outtmpl'].replace('%(ext)s', 'webm')).write_bytes(b'media')
            return {'requested_downloads': [selected]}

    monkeypatch.setattr(audio, 'YoutubeDL', FakeYoutubeDL)
    tmp_path.joinpath('staging').mkdir()
    with pytest.raises(audio.AudioDownloadError, match=message):
        asyncio.run(audio.download_audio('https://youtube.test/video',
                                         tmp_path / 'staging/source.%(ext)s'))


def test_download_converts_yt_dlp_errors_and_rejects_partial_or_ambiguous_output(
        tmp_path, monkeypatch):
    class FailingYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, _url, download):
            raise DownloadError('private upstream error')

    monkeypatch.setattr(audio, 'YoutubeDL', FailingYoutubeDL)
    with pytest.raises(audio.AudioDownloadError, match='private upstream'):
        asyncio.run(audio.download_audio('https://youtube.test/video',
                                         tmp_path / 'source.%(ext)s'))

    staging = tmp_path / 'staging'
    staging.mkdir()
    (staging / 'source.webm.part').write_bytes(b'partial')
    with pytest.raises(audio.AudioDownloadError, match='exactly one'):
        audio._find_downloaded_file(staging / 'source.%(ext)s')
    (staging / 'source.webm').write_bytes(b'one')
    (staging / 'source.m4a').write_bytes(b'two')
    with pytest.raises(audio.AudioDownloadError, match='exactly one'):
        audio._find_downloaded_file(staging / 'source.%(ext)s')
