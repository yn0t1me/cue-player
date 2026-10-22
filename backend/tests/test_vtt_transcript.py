from io import BytesIO

import pytest
import webvtt

from app.services.transcript import VTTParseError, parse_vtt


def test_parse_vtt_preserves_order_milliseconds_raw_text_and_source_payload():
    content = (
        b'WEBVTT\n\nfirst-cue\n00:00:01.250 --> 00:00:03.500 position:10%\n'
        b'<v Alice>Hello</v>\nsecond line\n\n'
        b'00:00:02.900 --> 00:00:04.001\nHello again\n'
    )
    cues = parse_vtt(content)
    assert [(cue.sequence_index, cue.start_seconds, cue.end_seconds) for cue in cues] == [
        (0, 1.25, 3.5), (1, 2.9, 4.001)]
    assert cues[0].text == '<v Alice>Hello</v>\nsecond line'
    assert cues[0].source_payload == {
        'identifier': 'first-cue', 'start': '00:00:01.250', 'end': '00:00:03.500',
        'lines': ['<v Alice>Hello</v>', 'second line'],
    }
    assert cues[1].source_payload['identifier'] is None


@pytest.mark.parametrize('content', [b'not webvtt', b'WEBVTT\n'])
def test_parse_vtt_rejects_invalid_or_empty_content(content):
    with pytest.raises(VTTParseError):
        parse_vtt(content)


def test_parser_does_not_use_library_helper_that_drops_milliseconds():
    content = b'WEBVTT\n\n00:00:01.250 --> 00:00:02.750\nText\n'
    caption = next(iter(webvtt.from_buffer(BytesIO(content))))
    assert caption.start_in_seconds == 1
    assert parse_vtt(content)[0].start_seconds == 1.25
