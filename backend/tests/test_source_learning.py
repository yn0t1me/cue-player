from dataclasses import FrozenInstanceError, replace
import json

import pytest

from app.core.enums import SubtitleSource
from app.services.transcript import source_learning as core
from app.services.transcript.source_learning import (
    SourceLearningError, extract_learning_source, parse_source_vtt,
    rebuild_learning_result,
)
from app.services.transcript.vtt import PersistedRawCueData

VIDEO = 'M7lc1UVf-VE'


def raw(index, start, end, text):
    return PersistedRawCueData(f'private-cue-{index}', index, start, end, text)


def extract(*cues):
    return extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_AUTO, tuple(cues))


@pytest.fixture
def source():
    return extract(raw(0, 0, 2, 'hello<00:00:00.400><c> world</c>'),
                   raw(1, 2.01, 4, 'next<00:00:03.000><c> sentence</c>'))


def result(source, segments=None, **changes):
    data = dict(format='learning-result-v2', source_video_id=source.source_video_id,
                source_digest=source.source_digest, segments=segments or [
                    dict(first_unit_id='u000001', last_unit_id='u000002', text='Hello / world.'),
                    dict(first_unit_id='u000003', last_unit_id='u000004', text='Next sentence.')])
    for item in data['segments']:
        item.setdefault('translation_zh', '测试译文。')
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


def assert_error(code, call):
    with pytest.raises(SourceLearningError) as caught:
        call()
    assert caught.value.code == code


def test_rolling_bridge_keeps_first_word_anchors_and_raw_positions():
    source = extract(
        raw(0, 0, 1, ' \nyou<00:00:00.400><c> know</c>'),
        raw(1, 1, 1.01, 'you know\n '),
        raw(2, 1.01, 2, 'you know\nchange<00:00:01.500><c> much</c>'),
        raw(3, 2, 2.01, 'change much'),
        raw(4, 2.01, 4, 'change much\nnow<00:00:03.000><c> go</c>'))
    assert [(u.text, u.start_ms) for u in source.units] == [
        ('you', 0), ('know', 400), ('change', 1010), ('much', 1500), ('now', 2010), ('go', 3000)]
    assert source.units[0].cue_id == 'private-cue-0'
    assert source.units[2].line_index == 1
    assert source.units[0].char_start == 2
    assert source.units[1].token_index == 1


def test_original_vtt_preserves_whitespace_rows_that_legacy_parser_loses():
    content = (b'WEBVTT\nKind: captions\n\n00:00:04.560 --> 00:00:08.629 align:start\n'
               b' \nyou<00:00:04.720><c> know</c>\n\n'
               b'00:00:08.629 --> 00:00:08.639\nyou know\n \n\n'
               b'00:00:08.639 --> 00:00:10.629\nyou know\na<00:00:08.760><c> few</c>\n')
    cues = parse_source_vtt(content)
    assert len(cues) == 3
    source = extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_AUTO, cues)
    assert [(u.text, u.start_ms) for u in source.units] == [
        ('you', 4560), ('know', 4720), ('a', 8639), ('few', 8760)]
    assert source.units[0].cue_id is None
    assert source.units[0].raw_vtt_sha256 == cues[0].raw_vtt_sha256
    assert source.units[0].cue_sequence_index == 0
    assert source == extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_AUTO, cues)


def test_original_parser_bom_crlf_identifiers_metadata_and_notes():
    text = ('WEBVTT\r\nKind: captions\r\n\r\nNOTE contains --> but is metadata\r\n\r\n'
            'named-cue\r\n00:00:00.000 --> 00:00:02.000 position:10%\r\n'
            'one<00:00:00.100><c> two</c>\r\n')
    source = extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_AUTO,
                                     parse_source_vtt(b'\xef\xbb\xbf' + text.encode()))
    assert [u.text for u in source.units] == ['one', 'two']


@pytest.mark.parametrize('content', [b'not VTT', b'WEBVTT\n',
    b'WEBVTT\n\n00:00:99.000 --> 00:01:40.000\ntext\n',
    b'WEBVTT\n\n00:00:00.000 --> nonsense\ntext\n', b'WEBVTT\n\nstray text\n',
    b'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n\xff'])
def test_original_vtt_rejects_malformed_evidence(content):
    with pytest.raises(SourceLearningError):
        parse_source_vtt(content)


def test_ordinary_multiline_and_real_repeats_are_preserved():
    source = extract(raw(0, 0, 1, 'very<00:00:00.200> very<00:00:00.400> good\nnext line'),
                     raw(1, 1.01, 2, 'good'),
                     raw(2, 2.01, 3, 'short'),
                     raw(3, 3.01, 4, 'short'))
    assert [u.text for u in source.units] == ['very', 'very', 'good', 'next', 'line', 'good', 'short', 'short']
    assert source.units[3].time_basis == 'inline_timestamp'


def test_short_new_cue_is_not_discarded_because_of_duration():
    source = extract(raw(0, 0, 1, 'one<00:00:00.100> two'),
                     raw(1, 1, 1.02, 'new'),
                     raw(2, 1.02, 2, 'different<00:00:01.400> thing'))
    assert [u.text for u in source.units] == ['one', 'two', 'new', 'different', 'thing']


def test_ambiguous_untimed_echo_without_bridge_is_rejected():
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(
        raw(0, 0, 1, 'one<00:00:00.200> two'),
        raw(1, 1.01, 2, 'one two\nnew<00:00:01.400> words')))


def test_overlapping_rolling_prefix_uses_exact_time_anchors():
    source = extract(raw(0, 0, 2, 'one<00:00:00.200> two'),
                     raw(1, 0, 3, 'one<00:00:00.200> two<00:00:02.100> three'))
    assert [(u.text, u.start_ms, u.cue_id) for u in source.units] == [
        ('one', 0, 'private-cue-0'), ('two', 200, 'private-cue-0'), ('three', 2100, 'private-cue-1')]


def test_blank_reset_music_entities_and_censored_token():
    cue = raw(0, 0, 1, '<v Alice>hello &amp;<00:00:00.200><c> [&nbsp;__&nbsp;]</c></v>')
    source = extract(cue, raw(1, 1, 2, ' \n '),
                     raw(2, 2, 3, '[Music]<00:00:02.200> hello'))
    assert [u.text for u in source.units] == ['hello', '&', '[__]', '[Music]', 'hello']
    assert cue.text[source.units[2].char_start:source.units[2].char_end] == '[&nbsp;__&nbsp;]'


def test_equal_internal_markers_share_time_without_interpolation():
    source = extract(raw(0, 0, 2, 'one<00:00:00.500> two<00:00:00.500> three'))
    assert [u.start_ms for u in source.units] == [0, 500, 500]


@pytest.mark.parametrize('text', ['one<00:00:00.900> two<00:00:00.800> three',
    'one<00:00:02.000> two', 'one<00:99:00.000> two',
    'one<00:00:00.20> two', 'one<00:00:00.200', 'one<unknown> two'])
def test_bad_internal_timing_or_markup_is_not_repaired(text):
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(raw(0, 0, 2, text)))


@pytest.mark.parametrize('start,end', [(float('nan'), 2), (0, float('inf')), (-1, 2), (2, 1), (1, 1)])
def test_invalid_raw_ranges_are_rejected(start, end):
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(raw(0, start, end, 'one<00:00:01.500> two')))


def test_raw_order_duplicate_ids_and_new_word_backtracking_are_rejected():
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(raw(1, 0, 2, 'one<00:00:01.000> two')))
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(
        raw(0, 0, 2, 'one<00:00:01.000> two'), replace(raw(1, 2, 3, 'three'), id='private-cue-0')))
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(
        raw(0, 0, 2, 'one<00:00:01.500> two'), raw(1, 1, 3, 'new<00:00:02.000> three')))


@pytest.mark.parametrize('kind', [SubtitleSource.YOUTUBE_MANUAL, SubtitleSource.STT])
def test_unsupported_source_is_explicit(kind):
    assert_error('SOURCE_TIMING_UNAVAILABLE', lambda: extract_learning_source(VIDEO, kind, ()))


def test_no_inline_evidence_does_not_claim_precision():
    assert_error('SOURCE_TIMING_UNAVAILABLE', lambda: extract(raw(0, 0, 1, 'plain text')))


def test_source_digest_binds_video_raw_positions_and_algorithm(source, monkeypatch):
    cues = (raw(0, 0, 2, 'hello<00:00:00.400><c> world</c>'),
            raw(1, 2.01, 4, 'next<00:00:03.000><c> sentence</c>'))
    assert extract(*cues) == source
    changed_video = extract_learning_source('abcdefghijk', SubtitleSource.YOUTUBE_AUTO, cues)
    assert changed_video.source_digest != source.source_digest
    assert extract(replace(cues[0], text='Hello<00:00:00.400><c> world</c>'), cues[1]).source_digest != source.source_digest
    assert extract(replace(cues[0], id='changed-private-id'), cues[1]).source_digest != source.source_digest
    monkeypatch.setattr(core, 'EXTRACTOR_VERSION', 'youtube-vtt-units-test-version')
    changed_version = extract(*cues)
    assert changed_version.source_digest != source.source_digest
    assert_error('LEARNING_SOURCE_MISMATCH', lambda: rebuild_learning_result(changed_version, result(source)))


def test_public_source_projection_does_not_leak_local_ids_or_paths(source):
    data = source.public_data()
    assert set(data) == {'format', 'source_video_id', 'source_digest', 'extractor_version', 'units', 'source_type', 'processing_mode'}
    assert set(data['units'][0]) == {'id', 'text', 'start_ms', 'time_basis'}
    assert 'private-cue' not in json.dumps(data)
    data['units'][0]['text'] = 'modified projection'
    assert source.units[0].text == 'hello'
    with pytest.raises(FrozenInstanceError):
        source.units[0].text = 'mutation'


def test_rebuild_uses_source_times_gap_and_unicode_offsets(source):
    rebuilt = rebuild_learning_result(source, result(source))
    first, second = rebuilt.sentences
    assert (first.start_ms, first.end_ms, first.end_basis) == (0, 2000, 'source_cue_end')
    assert (second.start_ms, second.end_ms) == (2010, 4000)
    assert first.text == 'Hello world.' and first.boundary_offsets == (5,)
    assert first.source_text == 'hello world'
    assert not any(w.code == 'TEXT_CHANGED' for w in rebuilt.warnings)
    assert rebuilt.preview_digest('revision-a') != rebuilt.preview_digest('revision-b')
    edited = rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000002', text='你好😀 / world.'),
        dict(first_unit_id='u000003', last_unit_id='u000004', text='Next sentence.')]))
    assert edited.sentences[0].boundary_offsets == (3,)


def test_sentence_split_inside_cue_and_changed_word_count():
    source = extract(raw(0, 0, 4, 'one<00:00:01.000> two<00:00:02.000> three'))
    rebuilt = rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000001', text='A corrected / expression.'),
        dict(first_unit_id='u000002', last_unit_id='u000003', text='Two.')]))
    assert [(s.start_ms, s.end_ms) for s in rebuilt.sentences] == [(0, 1000), (1000, 4000)]
    assert rebuilt.sentences[0].end_basis == 'next_sentence_start'
    assert [w.code for w in rebuilt.warnings].count('TEXT_CHANGED') == 2


def test_lexical_warning_preserves_word_boundaries():
    source = extract(raw(0, 0, 3, 'an<00:00:00.200> ice'))
    rebuilt = rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000002', text='A nice.')]))
    assert any(w.code == 'TEXT_CHANGED' for w in rebuilt.warnings)


def test_shared_timestamp_cannot_be_split_into_fake_sentence_times():
    source = extract(raw(0, 0, 2, 'one<00:00:00.500> two three'))
    assert_error('INVALID_REBUILT_TIMING', lambda: rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000002', text='One two.'),
        dict(first_unit_id='u000003', last_unit_id='u000003', text='Three.')])))


def test_small_interval_and_long_end_hold_have_warnings():
    source = extract(raw(0, 0, 5, 'one<00:00:00.100> two'))
    rebuilt = rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000001', text='One.'),
        dict(first_unit_id='u000002', last_unit_id='u000002', text='Two.')]))
    assert any(w.code == 'VERY_SHORT_SEGMENT' and w.sequence_index == 0 for w in rebuilt.warnings)
    assert any(w.code == 'LONG_END_HOLD' and w.sequence_index == 1 for w in rebuilt.warnings)


@pytest.mark.parametrize('pairs', [('u000000', 'u000002'), ('u000002', 'u000001'),
    ('u000002', 'u000004'), ('u000001', 'u000003'), ('u000001', 'u000001')])
def test_unknown_missing_overlapping_or_out_of_order_ranges_reject_whole_result(source, pairs):
    segments = [dict(first_unit_id=pairs[0], last_unit_id=pairs[1], text='First.'),
                dict(first_unit_id='u000003', last_unit_id='u000004', text='Next.')]
    assert_error('INVALID_SOURCE_RANGE', lambda: rebuild_learning_result(source, result(source, segments)))


def test_missing_tail_and_cross_video_or_digest_are_rejected(source):
    assert_error('INVALID_SOURCE_RANGE', lambda: rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000002', text='First.')])))
    for changes in ({'source_video_id': 'abcdefghijk'}, {'source_digest': 'f' * 64}):
        assert_error('LEARNING_SOURCE_MISMATCH', lambda: rebuild_learning_result(source, result(source, **changes)))


@pytest.mark.parametrize('content', ['{}', '[]', 'not JSON', '```json\n{}\n```',
    '{"format":"x","format":"y"}', '{"x":NaN}', '{"x":Infinity}',
    '{"x":-Infinity}', '{"format":', 'null'])
def test_nonstandard_partial_duplicate_or_wrong_json_is_rejected(source, content):
    assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(source, content))


@pytest.mark.parametrize('text', ['', ' / second', 'first / ', 'first /  / last',
    '\x00', '   '])
def test_invalid_chunks_reject_whole_result(source, text):
    segments = [dict(first_unit_id='u000001', last_unit_id='u000004', text=text)]
    assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(source, result(source, segments)))


def test_ai_time_fields_unknown_fields_and_wrong_types_are_rejected(source):
    data = json.loads(result(source))
    data['segments'][0]['start_ms'] = 999
    assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(source, json.dumps(data)))
    for changes in ({'format': 'learning-source-v1'}, {'source_video_id': []}, {'source_digest': 7}, {'extra': True}):
        assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(source, result(source, **changes)))


def test_bom_whitespace_and_preview_digest_are_deterministic(source):
    content = result(source)
    assert rebuild_learning_result(source, ' \n\ufeff' + content + '\n') == rebuild_learning_result(source, content)
    assert rebuild_learning_result(source, content).preview_digest('a') == rebuild_learning_result(source, content).preview_digest('a')


def test_size_and_unit_limits_are_explicit(source, monkeypatch):
    monkeypatch.setattr(core, 'MAX_RESULT_BYTES', 10)
    assert_error('LEARNING_RESULT_TOO_LARGE', lambda: rebuild_learning_result(source, result(source)))
    monkeypatch.setattr(core, 'MAX_SOURCE_UNITS', 1)
    assert_error('LEARNING_SOURCE_TOO_LARGE', lambda: extract(raw(0, 0, 2, 'one<00:00:01.000> two')))
    monkeypatch.setattr(core, 'MAX_SOURCE_UNITS', 50_000)
    monkeypatch.setattr(core, 'MAX_SOURCE_BYTES', 10)
    assert_error('LEARNING_SOURCE_TOO_LARGE', lambda: extract(raw(0, 0, 2, 'one<00:00:01.000> two')))
    assert_error('LEARNING_SOURCE_TOO_LARGE', lambda: parse_source_vtt(b'WEBVTT\n\nmore than ten bytes'))


def test_segment_limit_rejects_before_partial_rebuild(source, monkeypatch):
    monkeypatch.setattr(core, 'MAX_RESULT_SEGMENTS', 1)
    assert_error('LEARNING_RESULT_TOO_LARGE', lambda: rebuild_learning_result(source, result(source)))


def test_no_header_separator_is_rejected_instead_of_dropping_the_first_cue():
    content = (b'WEBVTT\n00:00:00.000 --> 00:00:01.000\none\n\n'
               b'00:00:01.000 --> 00:00:02.000\ntwo<00:00:01.200> three\n')
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: parse_source_vtt(content))


def test_extreme_raw_time_is_a_typed_error():
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(raw(0, 1e308, 1e308, 'text')))


def test_display_formatting_inside_a_word_does_not_split_source_units():
    source = extract(raw(0, 0, 2, 'hel<b>lo</b><00:00:00.200><c> world</c>'))
    assert [(u.text, u.start_ms) for u in source.units] == [('hello', 0), ('world', 200)]
    assert source.units[0].char_end == len('hel<b>lo')


def test_bilingual_auto_result_keeps_timing_and_binds_translation(source):
    data = json.loads(result(source))
    data['format'] = 'learning-result-v2'
    for item in data['segments']:
        item['translation_zh'] = '你好，世界。'
    first = rebuild_learning_result(source, json.dumps(data))
    assert [(s.start_ms, s.end_ms) for s in first.sentences] == [(0, 2000), (2010, 4000)]
    assert first.sentences[0].translation_zh == '你好，世界。'
    data['segments'][0]['translation_zh'] = '世界，你好。'
    second = rebuild_learning_result(source, json.dumps(data))
    assert second.preview_digest('rev') != first.preview_digest('rev')
    assert second.sentences[0].text == first.sentences[0].text


@pytest.mark.parametrize('translation', [None, '', ' \n\t\u3000', 123, [], {}, 'bad\x00', '\ud800'])
def test_bilingual_requires_valid_nonempty_translation(source, translation):
    data = json.loads(result(source))
    data['format'] = 'learning-result-v2'
    for item in data['segments']:
        item['translation_zh'] = translation
    assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(source, json.dumps(data)))


def test_manual_cues_preserve_repeats_multiline_tags_and_overlapping_times():
    cues = (raw(0, 1, 5, '<v Person><i>Hello</i> &amp;\nworld.'),
            raw(1, 4, 7, 'Hello &amp; world.'), raw(2, 7, 8, '   '),
            raw(3, 8, 9, 'and/or 😀 fine.'))
    source = extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_MANUAL, cues)
    assert source.processing_mode == 'manual_cues'
    assert source.extractor_version == 'youtube-manual-cues-v1'
    assert [u.text for u in source.units] == ['Hello & world.', 'Hello & world.', 'and/or 😀 fine.']
    data = dict(format='learning-result-v2', source_video_id=VIDEO, source_digest=source.source_digest,
                segments=[dict(first_unit_id=u.id, last_unit_id=u.id, text=u.text.replace(' ', ' / ', 1),
                               translation_zh='你好。') for u in source.units])
    rebuilt = rebuild_learning_result(source, json.dumps(data))
    assert [(s.start_ms, s.end_ms) for s in rebuilt.sentences] == [(1000, 5000), (4000, 7000), (8000, 9000)]
    assert all(s.end_basis == 'source_cue_end' for s in rebuilt.sentences)
    assert rebuilt.sentences[-1].boundary_offsets == (6,)
    assert source.units[-1].cue_sequence_index == 3
    data['format'] = 'learning-result-v1'
    assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(source, json.dumps(data)))


def test_manual_censor_markers_and_adjacent_markup_preserve_original_text():
    source = extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_MANUAL,
        (raw(0, 0, 2, 'hel<b>lo</b> [ __ ] &amp;\nworld.'),))
    assert source.units[0].text == 'hello [ __ ] & world.'


def test_manual_literal_spaced_slash_can_be_returned_unchanged():
    source = extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_MANUAL,
        (raw(0, 0, 2, 'Yes / no.'),))
    data = dict(format='learning-result-v2', source_video_id=VIDEO, source_digest=source.source_digest,
        segments=[dict(first_unit_id='u000001', last_unit_id='u000001',
                       text='Yes / no.', translation_zh='是或否。')])
    sentence = rebuild_learning_result(source, json.dumps(data)).sentences[0]
    assert sentence.text == 'Yes / no.'
    assert sentence.boundary_offsets == ()


@pytest.mark.parametrize('changed', ['hello world.', 'Hello world!', 'Hello brave world.', 'Hello.', '你好，世界。'])
def test_manual_word_punctuation_case_or_language_changes_are_rejected(changed):
    source = extract_learning_source(VIDEO, SubtitleSource.YOUTUBE_MANUAL, (raw(0, 0, 2, 'Hello world.'),))
    data = dict(format='learning-result-v2', source_video_id=VIDEO, source_digest=source.source_digest,
                segments=[dict(first_unit_id='u000001', last_unit_id='u000001', text=changed, translation_zh='你好。')])
    assert_error('MANUAL_TRANSCRIPT_CHANGED', lambda: rebuild_learning_result(source, json.dumps(data)))


def boundary_rollover_cues():
    return (raw(0, 0, 1.99, 'one<00:00:02.000> two'),
            raw(1, 1.99, 2, 'one two'),
            raw(2, 2, 4, 'one two\nthree<00:00:03.000> four'))


def test_tiny_boundary_overrun_requires_proven_rolling_continuation():
    cues = boundary_rollover_cues()
    source = extract(*cues)
    assert [(u.text, u.start_ms) for u in source.units] == [
        ('one', 0), ('two', 2000), ('three', 2000), ('four', 3000)]
    # The original word anchor and locator stay intact. Only its display end
    # comes from the proven continuation, with its own explicit locator.
    unit = source.units[1]
    assert unit.cue_id == cues[0].id
    assert unit.cue_end_ms == 4000
    assert unit.end_cue_sequence_index == 2
    assert cues[0].end_seconds == 1.99 and '<00:00:02.000>' in cues[0].text
    rebuilt = rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000003', text='One two three.'),
        dict(first_unit_id='u000004', last_unit_id='u000004', text='Four.')]))
    assert [(s.start_ms, s.end_ms) for s in rebuilt.sentences] == [(0, 3000), (3000, 4000)]
    # Shared source times still cannot be split into invented positive intervals.
    assert_error('INVALID_REBUILT_TIMING', lambda: rebuild_learning_result(source, result(source, [
        dict(first_unit_id='u000001', last_unit_id='u000002', text='One two.'),
        dict(first_unit_id='u000003', last_unit_id='u000004', text='Three four.')])) )


@pytest.mark.parametrize('change', ['large', 'missing', 'different_echo', 'gap', 'no_extension', 'timed_prefix', 'backwards'])
def test_boundary_overrun_is_not_a_general_timestamp_tolerance(change):
    first, bridge, next_cue = boundary_rollover_cues()
    if change == 'large': first = replace(first, end_seconds=1.98); bridge = replace(bridge, start_seconds=1.98)
    if change == 'missing':
        assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(first)); return
    if change == 'different_echo': bridge = replace(bridge, text='one wrong')
    if change == 'gap': next_cue = replace(next_cue, start_seconds=2.001)
    if change == 'no_extension': next_cue = replace(next_cue, text='one two')
    if change == 'timed_prefix': next_cue = replace(next_cue, text='one<00:00:02.100> two\nthree')
    if change == 'backwards': first = replace(first, text='one<00:00:02.000> two<00:00:01.900> bad')
    assert_error('INVALID_SOURCE_EVIDENCE', lambda: extract(first, bridge, next_cue))


def test_retired_v1_result_is_rejected(source):
    assert_error('INVALID_LEARNING_RESULT', lambda: rebuild_learning_result(
        source, result(source, format='learning-result-v1')))
