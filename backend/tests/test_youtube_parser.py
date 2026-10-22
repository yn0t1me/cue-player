import pytest
from app.services.youtube.parser import extract_video_id

VIDEO_ID = 'aB3_dE-fGhI'

@pytest.mark.parametrize('url', [
    f'https://www.youtube.com/watch?v={VIDEO_ID}&t=12&list=abc',
    f'https://youtube.com/watch/?v={VIDEO_ID}',
    f' https://youtu.be/{VIDEO_ID}?si=abc ',
    f'https://www.youtu.be/{VIDEO_ID}/',
    f'https://m.youtube.com/shorts/{VIDEO_ID}',
    f'https://youtube.com/embed/{VIDEO_ID}/?start=5',
    f'http://YouTube.com:80/watch?v={VIDEO_ID}',
    f'https://youtube.com:443/watch?v={VIDEO_ID}#t=8',
])
def test_supported_urls(url):
    assert extract_video_id(url) == VIDEO_ID

@pytest.mark.parametrize('url', [
    '', 'not-a-url', 'youtube.com/watch?v=aB3_dE-fGhI',
    'https://youtube.com.evil.test/watch?v=aB3_dE-fGhI',
    'https://evil.test/?v=aB3_dE-fGhI', 'https://youtube.com@evil.test/watch?v=aB3_dE-fGhI',
    'https://user@youtube.com/watch?v=aB3_dE-fGhI',
    'ftp://youtube.com/watch?v=aB3_dE-fGhI', 'https://youtube.com:8888/watch?v=aB3_dE-fGhI',
    'https://youtube.com/watch', 'https://youtube.com/watch?v=short',
    'https://youtube.com/watch?v=aB3_dE-fGhI&v=aB3_dE-fGhI',
    'https://youtu.be/aB3_dE-fGhI/extra', 'https://youtube.com/playlist?list=aB3_dE-fGhI',
    'https://youtube.com/watch?v=中文中文中文中文中文中',
    'https://youtube.com/watch?v=aB3.dE-fGhI',
    'https://[invalid/watch?v=aB3_dE-fGhI',
])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        extract_video_id(url)
