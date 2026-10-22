"""Temporary SQLite integration coverage for the source-based publication contract."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, func, select, text

from app.core.config import Settings
from app.core.enums import SubtitleSource, VideoStatus
from app.db.models import (LearningTranscriptSegment, RawTranscriptCue, TranscriptChunkLayout,
                           TranscriptChunkSegment, TranscriptMark, TranscriptRevision, Video)
from app.main import create_app
from app.services.processing.caption_store import CaptionStore
from app.services.source_learning import publish_source_learning
from app.services.transcript.source_learning import parse_source_vtt

BACKEND = Path(__file__).resolve().parents[1]
VTT = (b'WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n'
       b'Hello<00:00:01.500> there<00:00:02.000> friend\n\n'
       b'00:00:04.000 --> 00:00:07.000\nAgain<00:00:04.500> today\n')


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "api.db"}')
    config = Config(str(BACKEND / 'alembic.ini'))
    command.upgrade(config, 'head')
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path))) as client:
        factory = client.app.state.session_factory
        with factory() as session:
            video = Video(youtube_video_id='abcdefghijk', youtube_url='https://youtu.be/abcdefghijk',
                          status=VideoStatus.READY, subtitle_source=SubtitleSource.YOUTUBE_AUTO)
            session.add(video)
            session.flush()
            revision = TranscriptRevision(video_id=video.id, origin='generated', revision_number=1)
            session.add(revision)
            session.flush()
            segment = LearningTranscriptSegment(video_id=video.id, revision_id=revision.id,
                sequence_index=0, text='Old learning text', start_seconds=0, end_seconds=7,
                source_ref_type='cue', source_refs={'cue_ids': []}, normalization_version=2)
            session.add(segment)
            session.flush()
            layout = TranscriptChunkLayout(video_id=video.id, revision_id=revision.id,
                                           content_sha256='a' * 64)
            session.add(layout)
            session.flush()
            session.add(TranscriptChunkSegment(layout_id=layout.id, segment_id=segment.id,
                                               boundary_offsets=[3]))
            session.add(TranscriptMark(video_id=video.id, revision_id=revision.id, segment_id=segment.id,
                start_offset=0, end_offset=3, selected_text='Old'))
            session.add_all(RawTranscriptCue(video_id=video.id, sequence_index=cue.sequence_index,
                start_seconds=cue.start_seconds, end_seconds=cue.end_seconds, text=cue.text,
                source_type=SubtitleSource.YOUTUBE_AUTO) for cue in parse_source_vtt(VTT))
            video.current_revision_id = revision.id
            session.commit()
            video_id = video.id
        path = CaptionStore(tmp_path).save(video_id, VTT)
        yield client, video_id, factory, path, config


def _endpoint(video_id, suffix):
    return f'/api/videos/{video_id}/transcript/{suffix}'


def _result(client, video_id, first='Hello / there friend.', second='Again / today.'):
    response = client.get(_endpoint(video_id, 'learning-source'))
    assert response.status_code == 200, response.text
    source = response.json()
    return json.dumps(dict(format='learning-result-v2', source_video_id=source['source_video_id'],
        source_digest=source['source_digest'], segments=[
            dict(first_unit_id='u000001', last_unit_id='u000003', text=first, translation_zh='你好，朋友。'),
            dict(first_unit_id='u000004', last_unit_id='u000005', text=second, translation_zh='今天再来。')]))


def _payload(client, video_id, result):
    response = client.post(_endpoint(video_id, 'source-learning/preview'), json={'result': result})
    assert response.status_code == 200, response.text
    preview = response.json()
    return dict(result=result, expected_revision_id=preview['base_revision_id'],
                preview_digest=preview['preview_digest'])


def _snapshot(factory, legacy_columns=False):
    tables = ('videos', 'raw_transcript_cues', 'learning_transcript_segments',
              'transcript_revisions', 'transcript_marks', 'transcript_chunk_layouts',
              'transcript_chunk_segments')
    with factory() as session:
        result = {}
        for table in tables:
            excluded = {'note'} | ({'subtitle_preference', 'translation_zh'} if legacy_columns else set())
            columns = ', '.join(row[1] for row in session.execute(text(f'PRAGMA table_info({table})'))
                                if row[1] not in excluded)
            result[table] = session.execute(text(f'SELECT {columns} FROM {table} ORDER BY id')).all()
        return result


def test_read_preview_publish_history_marks_and_exports(setup):
    client, video_id, factory, path, _ = setup
    before = _snapshot(factory)
    source = client.get(_endpoint(video_id, 'learning-source'))
    assert source.headers['cache-control'] == 'no-store'
    assert set(source.json()) == {'format', 'source_video_id', 'source_digest', 'extractor_version', 'units', 'source_type', 'processing_mode'}
    assert set(source.json()['units'][0]) == {'id', 'text', 'start_ms', 'time_basis'}
    result = _result(client, video_id)
    preview = client.post(_endpoint(video_id, 'source-learning/preview'), json={'result': result}).json()
    assert [(item['start'], item['end']) for item in preview['segments']] == [(1, 4), (4, 7)]
    assert preview['segments'][0]['source_text'] == 'Hello there friend'
    assert preview['segments'][0]['chunks'] == ['Hello', 'there friend.']
    assert preview['segments'][0]['end_basis'] == 'next_sentence_start'
    assert preview['summary']['chunk_count'] == 4
    assert {w['code'] for w in preview['warnings']} == {'CUE_START_TIMING'}
    assert _snapshot(factory) == before
    payload = _payload(client, video_id, result)
    saved = client.post(_endpoint(video_id, 'source-learning'), json=payload)
    assert saved.status_code == 200, saved.text
    transcript, chunks = saved.json()['transcript'], saved.json()['chunk_layout']
    assert transcript['origin'] == 'source_aligned' and transcript['normalization_version'] is None
    assert transcript['revision_id'] == chunks['revision_id'] == chunks['layout']['revision_id']
    assert client.post(_endpoint(video_id, 'source-learning'), json=payload).json() == saved.json()
    with factory() as session:
        rows = session.scalars(select(LearningTranscriptSegment).where(
            LearningTranscriptSegment.revision_id == transcript['revision_id'])
            .order_by(LearningTranscriptSegment.sequence_index)).all()
        cue_ids = set(session.scalars(select(RawTranscriptCue.id)))
        for row in rows:
            assert row.source_ref_type == 'source_units' and row.normalization_run_id is None
            assert row.source_refs['source_digest'] == preview['source_digest']
            assert {unit['cue_id'] for unit in row.source_refs['units']} <= cue_ids
            assert all(unit['raw_vtt_sha256'] is None for unit in row.source_refs['units'])
    marks = client.get(f'/api/videos/{video_id}/marks').json()['items']
    assert len(marks) == 1 and not marks[0]['is_current'] and marks[0]['segment_text'] == 'Old learning text'
    history = client.get(_endpoint(video_id, 'revisions')).json()['items']
    assert [item['origin'] for item in history] == ['source_aligned', 'generated']
    old_id = history[-1]['id']
    assert client.get(_endpoint(video_id, f'revisions/{old_id}')).json()['segments'][0]['text'] == 'Old learning text'
    exported = client.get(_endpoint(video_id, 'learning-export.srt'))
    assert exported.text == '1\n00:00:01,000 --> 00:00:04,000\nHello there friend.\n\n2\n00:00:04,000 --> 00:00:07,000\nAgain today.\n'
    assert exported.headers['cache-control'] == 'no-store'
    assert '-learning.srt' in exported.headers['content-disposition']
    assert client.get(_endpoint(video_id, 'export.srt')).status_code == 200
    assert path.read_bytes() == VTT
    after = _snapshot(factory)
    assert after['raw_transcript_cues'] == before['raw_transcript_cues']
    assert after['transcript_marks'] == before['transcript_marks']


def test_file_recovery_uses_only_file_locators_and_source_changes_expire_result(setup):
    client, video_id, factory, path, _ = setup
    # Reproduce the legacy dropped first cue without editing Raw in the service.
    with factory() as session:
        session.execute(text('DELETE FROM raw_transcript_cues WHERE sequence_index=0'))
        session.commit()
    before = _snapshot(factory)
    result = _result(client, video_id)
    payload = _payload(client, video_id, result)
    saved = client.post(_endpoint(video_id, 'source-learning'), json=payload).json()
    revision_id = saved['transcript']['revision_id']
    with factory() as session:
        rows = session.scalars(select(LearningTranscriptSegment).where(
            LearningTranscriptSegment.revision_id == revision_id)).all()
        for row in rows:
            assert all(u['cue_id'] is None and len(u['raw_vtt_sha256']) == 64
                       for u in row.source_refs['units'])
    assert _snapshot(factory)['raw_transcript_cues'] == before['raw_transcript_cues']
    path.write_bytes(VTT + b'\nNOTE source changed\n')
    stale = client.post(_endpoint(video_id, 'source-learning'), json=payload)
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'LEARNING_SOURCE_MISMATCH'
    # Same time/text/layout with different source evidence must create a revision.
    next_payload = _payload(client, video_id, _result(client, video_id))
    fresh = client.post(_endpoint(video_id, 'source-learning'), json=next_payload).json()
    assert fresh['transcript']['revision_id'] != revision_id
    assert [s['text'] for s in fresh['transcript']['segments']] == [s['text'] for s in saved['transcript']['segments']]


@pytest.mark.parametrize('fault', ['transcript_revisions', 'learning_transcript_segments',
                                 'transcript_chunk_layouts', 'transcript_chunk_segments', 'pointer'])
def test_failure_at_each_publish_stage_rolls_back(setup, fault):
    client, video_id, factory, _, _ = setup
    payload = _payload(client, video_id, _result(client, video_id))
    before = _snapshot(factory)
    engine = factory.kw['bind']
    def fail(_connection, _cursor, statement, _params, _context, _many):
        if (statement.startswith(f'INSERT INTO {fault} ')
                or fault == 'pointer' and statement.startswith('UPDATE videos SET current_revision_id=?')):
            raise RuntimeError('injected publication failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            publish_source_learning(factory, video_id, client.app.state.data_dir, **payload)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    assert _snapshot(factory) == before


@pytest.mark.parametrize('identical', [True, False])
def test_concurrent_confirmation_converges_or_conflicts(setup, identical):
    client, video_id, factory, _, _ = setup
    result = _result(client, video_id)
    first = _payload(client, video_id, result)
    second = first if identical else _payload(client, video_id, _result(client, video_id, second='Today again.'))
    barrier = Barrier(3)
    def submit(payload):
        barrier.wait()
        return client.post(_endpoint(video_id, 'source-learning'), json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, payload) for payload in [first, second]]
        barrier.wait()
        responses = [f.result() for f in futures]
    if identical:
        assert all(r.status_code == 200 for r in responses)
        assert responses[0].json() == responses[1].json()
    else:
        assert sorted(r.status_code for r in responses) == [200, 409]
        assert next(r for r in responses if r.status_code == 409).json()['error']['code'] == 'TRANSCRIPT_REVISION_CONFLICT'
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptRevision)) == 2
        assert session.scalar(select(func.count()).select_from(TranscriptChunkLayout)) == 2


@pytest.mark.parametrize('change,code,status', [
    ('json', 'INVALID_LEARNING_RESULT', 422), ('time_field', 'INVALID_LEARNING_RESULT', 422),
    ('missing_unit', 'INVALID_SOURCE_RANGE', 422), ('video', 'LEARNING_SOURCE_MISMATCH', 409),
    ('digest', 'LEARNING_SOURCE_MISMATCH', 409), ('huge', 'LEARNING_RESULT_TOO_LARGE', 413),
    ('chunks', 'INVALID_LEARNING_RESULT', 422),
])
def test_invalid_preview_and_publish_never_write(setup, change, code, status):
    client, video_id, factory, _, _ = setup
    original = _result(client, video_id)
    payload = _payload(client, video_id, original)
    result = json.loads(original)
    if change == 'time_field':
        result['segments'][0]['start'] = 1
    elif change == 'missing_unit':
        result['segments'][0]['last_unit_id'] = 'u000002'
    elif change == 'video':
        result['source_video_id'] = 'wrongvideo1'
    elif change == 'digest':
        result['source_digest'] = '0' * 64
    elif change == 'chunks':
        result['segments'][0]['text'] = 'Hello /  / friend'
    content = '{' if change == 'json' else 'x' * (1024 * 1024 + 1) if change == 'huge' else json.dumps(result)
    before = _snapshot(factory)
    for suffix, request in [('source-learning/preview', {'result': content}),
                            ('source-learning', {**payload, 'result': content})]:
        response = client.post(_endpoint(video_id, suffix), json=request)
        assert response.status_code == status, response.text
        assert response.json()['error']['code'] == code
    assert _snapshot(factory) == before


def test_changed_preview_and_current_publication_conflict(setup):
    client, video_id, factory, _, _ = setup
    payload = _payload(client, video_id, _result(client, video_id))
    before = _snapshot(factory)
    changed = {**payload, 'result': _result(client, video_id, second='Another day.')}
    response = client.post(_endpoint(video_id, 'source-learning'), json=changed)
    assert response.status_code == 409 and response.json()['error']['code'] == 'SOURCE_LEARNING_PREVIEW_MISMATCH'
    assert _snapshot(factory) == before
    newer = _payload(client, video_id, _result(client, video_id, first='New / wording.'))
    published = client.post(_endpoint(video_id, 'source-learning'), json=newer)
    assert published.status_code == 200
    stale = client.post(_endpoint(video_id, 'source-learning'), json=payload)
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'TRANSCRIPT_REVISION_CONFLICT'


@pytest.mark.parametrize('fault,code,status', [
    ('missing', 'SOURCE_TIMING_UNAVAILABLE', 409), ('symlink', 'SOURCE_TIMING_UNAVAILABLE', 409),
    ('stt', 'SOURCE_TIMING_UNAVAILABLE', 409),
    ('no_inline', 'SOURCE_TIMING_UNAVAILABLE', 409), ('malformed', 'INVALID_SOURCE_EVIDENCE', 422),
    ('too_large', 'LEARNING_SOURCE_TOO_LARGE', 413),
])
def test_unavailable_evidence_is_safe_and_readonly(setup, fault, code, status):
    client, video_id, factory, path, _ = setup
    if fault == 'missing':
        path.unlink()
    elif fault == 'symlink':
        outside = path.parent.parent / 'other.vtt'
        outside.write_bytes(VTT)
        path.unlink()
        path.symlink_to(outside)
    elif fault in {'manual', 'stt'}:
        with factory() as session:
            session.get(Video, video_id).subtitle_source = SubtitleSource(f'youtube_{fault}' if fault == 'manual' else fault)
            session.commit()
    else:
        path.write_bytes({'no_inline': b'WEBVTT\n\n00:00:01.000 --> 00:00:07.000\nHello friend\n',
                          'malformed': b'not WebVTT', 'too_large': b'x' * (5 * 1024 * 1024 + 1)}[fault])
    before = _snapshot(factory)
    response = client.get(_endpoint(video_id, 'learning-source'))
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert str(path) not in response.text
    assert _snapshot(factory) == before


@pytest.mark.parametrize('state,code', [(VideoStatus.PROCESSING, 'TRANSCRIPT_NOT_READY'),
                                      (VideoStatus.FAILED, 'TRANSCRIPT_UNAVAILABLE')])
def test_not_ready_and_missing_video_errors(setup, state, code):
    client, video_id, factory, _, _ = setup
    with factory() as session:
        session.get(Video, video_id).status = state
        session.commit()
    for suffix in ['learning-source', 'learning-export.srt']:
        assert client.get(_endpoint(video_id, suffix)).json()['error']['code'] == code
        assert client.get(_endpoint('missing', suffix)).status_code == 404
    for suffix in ['source-learning/preview', 'source-learning']:
        payload = {'result': '{}'}
        if suffix == 'source-learning':
            payload.update(expected_revision_id='x', preview_digest='x')
        assert client.post(_endpoint(video_id, suffix), json=payload).json()['error']['code'] == code
        assert client.post(_endpoint('missing', suffix), json=payload).status_code == 404


def test_upgrade_and_downgrade_preserve_populated_historical_relations(setup):
    client, video_id, factory, _, config = setup
    before = _snapshot(factory, legacy_columns=True)
    command.downgrade(config, '007_add_chunk_layouts')
    assert _snapshot(factory, legacy_columns=True) == before
    command.upgrade(config, 'head')
    assert _snapshot(factory, legacy_columns=True) == before
    command.check(config)
    with factory() as session:
        assert session.execute(text('PRAGMA foreign_key_check')).all() == []
        assert session.scalar(text('PRAGMA integrity_check')) == 'ok'


def test_downgrade_rejects_source_data_without_deleting_it(setup):
    client, video_id, factory, _, config = setup
    payload = _payload(client, video_id, _result(client, video_id))
    assert client.post(_endpoint(video_id, 'source-learning'), json=payload).status_code == 200
    # Exercise the 008 source guard separately from the newer 011 translation guard.
    with factory() as session:
        for segment in session.scalars(select(LearningTranscriptSegment)):
            segment.translation_zh = None
        session.commit()
    before = _snapshot(factory, legacy_columns=True)
    with pytest.raises(RuntimeError, match='source-aligned'):
        command.downgrade(config, '007_add_chunk_layouts')
    assert _snapshot(factory, legacy_columns=True) == before


def test_lexical_changes_are_previewed_without_claiming_audio_alignment(setup):
    client, video_id, factory, _, _ = setup
    before = _snapshot(factory)
    result = _result(client, video_id, first='Hi / there, dear friend.')
    response = client.post(_endpoint(video_id, 'source-learning/preview'), json={'result': result})
    assert response.status_code == 200
    warning = next(w for w in response.json()['warnings'] if w['code'] == 'TEXT_CHANGED')
    assert warning['sequence_index'] == 0 and warning['start'] == 1
    assert response.json()['segments'][0]['source_text'] == 'Hello there friend'
    assert _snapshot(factory) == before


@pytest.mark.parametrize('suffix,payload', [
    ('source-learning/preview', {'result': '{}', 'srt': 'unexpected'}),
    ('source-learning/preview', {'result': {}}),
    ('source-learning', {'result': '{}'}),
])
def test_exchange_request_shape_errors(setup, suffix, payload):
    client, video_id, factory, _, _ = setup
    before = _snapshot(factory)
    response = client.post(_endpoint(video_id, suffix), json=payload)
    assert response.status_code == 422 and response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert _snapshot(factory) == before


def _bilingual_result(client, video_id):
    data = json.loads(_result(client, video_id))
    data['format'] = 'learning-result-v2'
    for item in data['segments']:
        item['translation_zh'] = '这是一句中文。'
    return json.dumps(data, ensure_ascii=False)


@pytest.fixture
def manual_setup(setup):
    client, video_id, factory, path, config = setup
    content = (b'WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n<v Speaker><i>Hello</i> &amp;\nworld.\n\n'
               b'00:00:04.000 --> 00:00:07.000\nHello &amp; world.\n')
    with factory() as session:
        session.get(Video, video_id).subtitle_source = SubtitleSource.YOUTUBE_MANUAL
        rows = session.scalars(select(RawTranscriptCue).order_by(RawTranscriptCue.sequence_index)).all()
        for row, cue in zip(rows, parse_source_vtt(content), strict=True):
            row.source_type = SubtitleSource.YOUTUBE_MANUAL
            row.text, row.start_seconds, row.end_seconds = cue.text, cue.start_seconds, cue.end_seconds
        session.commit()
    path.write_bytes(content)
    source = client.get(_endpoint(video_id, 'learning-source')).json()
    result = json.dumps(dict(format='learning-result-v2', source_video_id=source['source_video_id'],
        source_digest=source['source_digest'], segments=[
            dict(first_unit_id=u['id'], last_unit_id=u['id'], text='Hello / & world.', translation_zh='你好，世界。')
            for u in source['units']]), ensure_ascii=False)
    return setup, source, result


def test_manual_publish_preserves_original_cues_and_old_anchors(manual_setup):
    (client, video_id, factory, path, _), source, result = manual_setup
    before = _snapshot(factory)
    assert source['format'] == 'learning-source-v2'
    assert (source['source_type'], source['processing_mode']) == ('youtube_manual', 'manual_cues')
    preview = client.post(_endpoint(video_id, 'source-learning/preview'), json={'result': result}).json()
    assert [(s['start'], s['end']) for s in preview['segments']] == [(1, 5), (4, 7)]
    assert [s['text'] for s in preview['segments']] == ['Hello & world.'] * 2
    assert all(s['translation_zh'] == '你好，世界。' for s in preview['segments'])
    assert _snapshot(factory) == before
    payload = _payload(client, video_id, result)
    saved = client.post(_endpoint(video_id, 'source-learning'), json=payload)
    assert saved.status_code == 200, saved.text
    transcript = saved.json()['transcript']
    assert transcript['revision_id'] == saved.json()['chunk_layout']['revision_id']
    assert client.post(_endpoint(video_id, 'source-learning'), json=payload).json() == saved.json()
    assert client.get(_endpoint(video_id, 'revisions/'+transcript['revision_id'])).json() == transcript
    old = client.get(_endpoint(video_id, 'revisions/'+payload['expected_revision_id'])).json()
    assert old['segments'][0]['translation_zh'] is None
    assert '你好' not in client.get(_endpoint(video_id, 'learning-export.srt')).text
    after = _snapshot(factory)
    for name in ('raw_transcript_cues', 'transcript_marks'):
        assert after[name] == before[name]
    with factory() as session:
        row = session.scalar(select(LearningTranscriptSegment).where(
            LearningTranscriptSegment.revision_id == transcript['revision_id']))
        assert row.source_refs['processing_mode'] == 'manual_cues'
        assert row.source_refs['result_format'] == 'learning-result-v2'


@pytest.mark.parametrize('change,code', [('word', 'MANUAL_TRANSCRIPT_CHANGED'),
    ('merge', 'INVALID_SOURCE_RANGE'), ('split', 'INVALID_SOURCE_RANGE'),
    ('missing', 'INVALID_SOURCE_RANGE'), ('translation', 'INVALID_LEARNING_RESULT'),
    ('legacy', 'INVALID_LEARNING_RESULT'), ('time', 'INVALID_LEARNING_RESULT')])
def test_manual_invalid_results_never_write(manual_setup, change, code):
    (client, video_id, factory, _, _), _, original = manual_setup
    payload = _payload(client, video_id, original)
    data = json.loads(original)
    if change == 'word':
        data['segments'][0]['text'] = 'Hello / dear world.'
    elif change == 'merge':
        data['segments'][0]['last_unit_id'] = 'u000002'
        data['segments'].pop()
    elif change == 'split':
        data['segments'].insert(0, data['segments'][0].copy())
    elif change == 'missing':
        data['segments'].pop()
    elif change == 'translation':
        del data['segments'][0]['translation_zh']
    elif change == 'legacy':
        data['format'] = 'learning-result-v1'
    elif change == 'time':
        data['segments'][0]['start'] = 1
    result = json.dumps(data)
    before = _snapshot(factory)
    for suffix, body in [('source-learning/preview', {'result': result}),
                         ('source-learning', {**payload, 'result': result})]:
        response = client.post(_endpoint(video_id, suffix), json=body)
        assert response.status_code == 422, response.text
        assert response.json()['error']['code'] == code
    assert _snapshot(factory) == before


def test_translation_edits_invalidate_preview_and_create_distinct_revision(setup):
    client, video_id, factory, _, _ = setup
    original = _bilingual_result(client, video_id)
    payload = _payload(client, video_id, original)
    data = json.loads(original)
    data['segments'][0]['translation_zh'] = '另一种翻译。'
    changed = json.dumps(data)
    before = _snapshot(factory)
    stale = client.post(_endpoint(video_id, 'source-learning'), json={**payload, 'result': changed})
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'SOURCE_LEARNING_PREVIEW_MISMATCH'
    assert _snapshot(factory) == before
    first = client.post(_endpoint(video_id, 'source-learning'), json=payload).json()['transcript']
    second_payload = _payload(client, video_id, changed)
    second = client.post(_endpoint(video_id, 'source-learning'), json=second_payload).json()['transcript']
    assert first['revision_id'] != second['revision_id']
    assert [s['text'] for s in first['segments']] == [s['text'] for s in second['segments']]
    assert second['segments'][0]['translation_zh'] == '另一种翻译。'
    assert client.get(_endpoint(video_id, 'revisions/'+first['revision_id'])).json() == first


@pytest.mark.parametrize('fault', ['transcript_revisions', 'learning_transcript_segments',
                                 'transcript_chunk_layouts', 'transcript_chunk_segments', 'pointer'])
def test_bilingual_failure_at_each_publish_stage_rolls_back(setup, fault):
    client, video_id, factory, _, _ = setup
    payload = _payload(client, video_id, _bilingual_result(client, video_id))
    before = _snapshot(factory)
    engine = factory.kw['bind']
    def fail(_connection, _cursor, statement, _params, _context, _many):
        if (statement.startswith(f'INSERT INTO {fault} ')
                or fault == 'pointer' and statement.startswith('UPDATE videos SET current_revision_id=?')):
            raise RuntimeError('injected bilingual failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected bilingual'):
            publish_source_learning(factory, video_id, client.app.state.data_dir, **payload)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    assert _snapshot(factory) == before


@pytest.mark.parametrize('identical', [True, False])
def test_concurrent_bilingual_confirms_do_not_lose_translation(setup, identical):
    client, video_id, factory, _, _ = setup
    content = _bilingual_result(client, video_id)
    first = _payload(client, video_id, content)
    data = json.loads(content)
    data['segments'][0]['translation_zh'] = '不同译文。'
    second = first if identical else _payload(client, video_id, json.dumps(data))
    barrier = Barrier(3)
    def submit(payload):
        barrier.wait()
        return client.post(_endpoint(video_id, 'source-learning'), json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, payload) for payload in (first, second)]
        barrier.wait()
        responses = [future.result() for future in futures]
    assert sorted(r.status_code for r in responses) == ([200, 200] if identical else [200, 409])
    if identical:
        assert responses[0].json() == responses[1].json()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptRevision)) == 2


def test_011_upgrade_preserves_all_old_columns_and_checks_metadata(setup):
    client, video_id, factory, _, config = setup
    from sqlalchemy.exc import IntegrityError
    command.downgrade(config, '010_saved_answer_history')
    with factory() as session:
        tables = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
        )).scalars().all()
        columns = {table: [row[1] for row in session.execute(text(f'PRAGMA table_info({table})'))]
                   for table in tables}
        before = {table: session.execute(text(
            f'SELECT {", ".join(columns[table])} FROM {table} ORDER BY {", ".join(columns[table])}')).all() for table in tables}
    command.upgrade(config, '013_import_retries')
    with factory() as session:
        after = {table: session.execute(text(
            f'SELECT {", ".join(columns[table])} FROM {table} ORDER BY {", ".join(columns[table])}')).all() for table in tables}
        assert before == after
        assert session.execute(text('PRAGMA foreign_key_check')).all() == []
        assert session.get(Video, video_id).subtitle_preference == 'manual_first'
        assert all(s.translation_zh is None for s in session.scalars(select(LearningTranscriptSegment)))
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE videos SET subtitle_preference = 'invalid'"))
        session.rollback()

    command.upgrade(config, 'head')
    command.check(config)


@pytest.mark.parametrize('data', ['translation', 'preference'])
def test_011_downgrade_refuses_to_discard_new_data(setup, data):
    _, video_id, factory, _, config = setup
    with factory() as session:
        if data == 'translation':
            session.scalar(select(LearningTranscriptSegment)).translation_zh = '保留译文。'
        else:
            session.get(Video, video_id).subtitle_preference = 'auto_only'
        session.commit()
    before = _snapshot(factory)
    with pytest.raises(RuntimeError, match='translations or source preferences'):
        command.downgrade(config, '010_saved_answer_history')
    assert _snapshot(factory) == before
    with factory() as session:
        assert session.scalar(text('SELECT version_num FROM alembic_version')) == '011_bilingual_subtitles'


def test_boundary_continuation_end_is_read_only_then_published_with_locator(setup):
    client, video_id, factory, path, _ = setup
    vtt = (b'WEBVTT\n\n00:00:00.000 --> 00:00:01.990\n'
           b'one<00:00:02.000> two\n\n'
           b'00:00:01.990 --> 00:00:02.000\none two\n\n'
           b'00:00:02.000 --> 00:00:04.000\none two\nthree<00:00:03.000> four\n')
    # Original-file restoration remains distinct from the unchanged DB snapshot.
    path.write_bytes(vtt)
    before = _snapshot(factory)
    source = client.get(_endpoint(video_id, 'learning-source'))
    assert source.status_code == 200, source.text
    data = source.json()
    assert data['units'][1]['start_ms'] == 2000
    assert data['extractor_version'] == 'youtube-vtt-units-v2'
    returned = json.dumps(dict(format='learning-result-v2', source_video_id=data['source_video_id'],
        source_digest=data['source_digest'], segments=[dict(first_unit_id='u000001',
            last_unit_id='u000004', text='One two / three four.', translation_zh='测试译文。')]))
    preview = client.post(_endpoint(video_id, 'source-learning/preview'), json={'result': returned})
    assert preview.status_code == 200, preview.text
    assert preview.json()['segments'][0]['end'] == 4
    assert _snapshot(factory) == before
    assert path.read_bytes() == vtt
    payload = _payload(client, video_id, returned)
    published = client.post(_endpoint(video_id, 'source-learning'), json=payload)
    assert published.status_code == 200, published.text
    with factory() as session:
        segment = session.scalar(select(LearningTranscriptSegment).where(
            LearningTranscriptSegment.revision_id == published.json()['transcript']['revision_id']))
        reference = segment.source_refs['units'][1]
        assert reference['start_ms'] == 2000 and reference['cue_end_ms'] == 4000
        assert reference['cue_sequence_index'] == 0 and reference['end_cue_sequence_index'] == 2
        assert reference['cue_id'] is None
    assert client.post(_endpoint(video_id, 'source-learning'), json=payload).json() == published.json()
    assert path.read_bytes() == vtt


def test_retired_endpoints_and_v1_result_are_unavailable_without_writes(setup):
    client, video_id, factory, *_ = setup
    before = _snapshot(factory)
    retired = ['import', 'import/preview', 'learning-import', 'learning-import/preview',
               'chunk-layout', 'chunk-layout/preview']
    for suffix in retired:
        assert client.post(_endpoint(video_id, suffix), json={'srt': 'old'}).status_code in (404, 405)
    for suffix in ['', '/batches/0/retry']:
        path = f'/api/videos/{video_id}/normalization{suffix}'
        assert client.post(path).status_code == 404
    assert client.get(f'/api/videos/{video_id}/normalization').status_code == 404
    data = json.loads(_result(client, video_id))
    data['format'] = 'learning-result-v1'
    response = client.post(_endpoint(video_id, 'source-learning/preview'), json={'result': json.dumps(data)})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'INVALID_LEARNING_RESULT'
    assert _snapshot(factory) == before
