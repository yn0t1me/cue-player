import asyncio

import httpx
import pytest

from app.core.enums import SubtitleSource
from app.services.youtube import captions


def candidate(language='en', extension='vtt', url='https://www.youtube.com/api/timedtext?v=test',
              source=SubtitleSource.YOUTUBE_MANUAL):
    return captions.CaptionCandidate(
        source=source, language=language,
        language_name='English', url=url, extension=extension)


def test_discovery_includes_manual_and_automatic_english_tracks_with_sources(monkeypatch):
    monkeypatch.setattr(captions, '_extract_caption_info', lambda _url: {
        'subtitles': {
            'fr': [{'ext': 'vtt', 'url': 'https://youtube.test/fr', 'name': 'French'}],
            'en-US': [
                {'ext': 'srv3', 'url': 'https://youtube.test/en-srv3', 'name': 'English (US)'},
                {'ext': 'vtt', 'url': 'https://youtube.test/en-vtt', 'name': 'English (US)'},
            ],
        },
        'automatic_captions': {
            'en': [
                {'ext': 'srv3', 'url': 'https://youtube.test/auto-srv3', 'name': 'English'},
                {'ext': 'vtt', 'url': 'https://youtube.test/auto-vtt', 'name': 'English'},
            ],
        },
    })
    found = asyncio.run(captions.discover_captions('https://youtube.test/watch'))
    assert [(item.source, item.language, item.extension, item.url) for item in found] == [
        (SubtitleSource.YOUTUBE_MANUAL, 'en-US', 'srv3', 'https://youtube.test/en-srv3'),
        (SubtitleSource.YOUTUBE_MANUAL, 'en-US', 'vtt', 'https://youtube.test/en-vtt'),
        (SubtitleSource.YOUTUBE_AUTO, 'en', 'srv3', 'https://youtube.test/auto-srv3'),
        (SubtitleSource.YOUTUBE_AUTO, 'en', 'vtt', 'https://youtube.test/auto-vtt'),
    ]


def test_selection_prefers_manual_source_before_language_rank():
    choices = [
        candidate('en', source=SubtitleSource.YOUTUBE_AUTO),
        candidate('en-GB'),
        candidate('en-US', source=SubtitleSource.YOUTUBE_AUTO),
    ]
    assert captions.select_best_caption(choices) == choices[1]


def test_selection_falls_back_to_best_automatic_english_vtt():
    choices = [
        candidate('en-GB', source=SubtitleSource.YOUTUBE_AUTO),
        candidate('en-US', source=SubtitleSource.YOUTUBE_AUTO),
        candidate('en', source=SubtitleSource.YOUTUBE_AUTO),
        candidate('en', 'srv3', source=SubtitleSource.YOUTUBE_AUTO),
    ]
    assert captions.select_best_caption(choices) == choices[2]


def test_selection_prefers_plain_english_vtt_and_keeps_discovery_order_stable():
    choices = [candidate('en-GB'), candidate('en-US'), candidate('en'), candidate('en', 'srv3')]
    assert captions.select_best_caption(choices) == choices[2]
    same_rank = [candidate('en'), candidate('en')]
    assert captions.select_best_caption(same_rank) == same_rank[0]


def test_selection_rejects_non_english_non_vtt_and_non_caption_sources():
    assert captions.select_best_caption([
        candidate('fr'),
        candidate('en', 'srv3'),
        candidate('en', source=SubtitleSource.STT),
    ]) is None


def test_translated_and_incomplete_tracks_are_excluded_from_both_sources(monkeypatch):
    monkeypatch.setattr(captions, '_extract_caption_info', lambda _url: {
        'subtitles': {
            'en': [{'ext': 'vtt', 'url': 'https://youtube.test/manual?tlang=en'}],
        },
        'automatic_captions': {
            'en': [
                {'ext': 'vtt', 'url': 'https://youtube.test/auto?tlang=en'},
                {'ext': 'vtt'},
                {'url': 'https://youtube.test/missing-extension'},
            ],
        },
    })
    assert asyncio.run(captions.discover_captions('https://youtube.test/watch')) == []


def test_download_keeps_original_bytes_and_validates_vtt():
    expected = b'\xef\xbb\xbfWEBVTT\n\n00:00.000 --> 00:01.000\nHello\n'
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=expected))

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await captions.download_caption(candidate(), client)

    assert asyncio.run(run()) == expected


@pytest.mark.parametrize('response', [
    httpx.Response(404, text='missing'),
    httpx.Response(200, content=b''),
    httpx.Response(200, content=b'<html>not captions</html>'),
])
def test_download_rejects_http_and_invalid_content(response):
    transport = httpx.MockTransport(lambda _request: response)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            await captions.download_caption(candidate(), client)

    with pytest.raises(captions.CaptionDownloadError):
        asyncio.run(run())


def test_download_rejects_content_over_the_limit(monkeypatch):
    monkeypatch.setattr(captions, 'MAX_CAPTION_BYTES', 8)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=b'WEBVTT\n\ntoo large'))

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            await captions.download_caption(candidate(), client)

    with pytest.raises(captions.CaptionDownloadError, match='too large'):
        asyncio.run(run())
