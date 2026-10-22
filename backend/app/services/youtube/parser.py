import re
from urllib.parse import parse_qs, urlsplit


def extract_video_id(url: str) -> str:
    """Parse supported public YouTube URL shapes without performing network I/O."""
    url = url.strip()
    if any(ord(char) < 32 for char in url):
        raise ValueError('Invalid URL characters')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or parsed.username is not None or parsed.password is not None:
        raise ValueError('Expected a public HTTP(S) YouTube URL')
    if parsed.port not in (None, 443 if parsed.scheme == 'https' else 80):
        raise ValueError('Non-standard port')
    path = parsed.path.removesuffix('/')
    if parsed.hostname in ('youtu.be', 'www.youtu.be'):
        identifier = path.removeprefix('/')
    elif parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if path == '/watch':
            identifiers = parse_qs(parsed.query, keep_blank_values=True).get('v', [])
            if len(identifiers) != 1:
                raise ValueError('Expected one video identifier')
            identifier = identifiers[0]
        elif path.startswith(('/shorts/', '/embed/')):
            identifier = path.split('/', 2)[2]
        else:
            raise ValueError('Unsupported YouTube URL path')
    else:
        raise ValueError('Unsupported YouTube hostname')
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier) is None:
        raise ValueError('Invalid YouTube video identifier')
    return identifier
