import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, func, select

from app.core.config import Settings
from app.core.enums import JobStatus, ProcessingStage, SubtitleSource, VideoStatus
from app.core.errors import AppError
from app.db.models import (
    Video, ProcessingJob, RawTranscriptCue, RawTranscriptWord,
    TranscriptRevision, TranscriptNormalizationRun, VideoImportRetryRequest, VideoImportRetryBinding,
)
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.schemas.video_collections import RetryVideoRequest
from app.services.import_retries import retry_video
from app.services.processing.caption_store import CaptionStore
from app.services.processing.video_import import VideoImportPipeline
from app.services.transcript import parse_vtt, persist_raw_cues, persist_stt_transcript, TranscriptionData, TranscriptionSegmentData, TranscriptionWordData

VTT = b'WEBVTT\n\n00:00.000 --> 00:01.000\nHello world.\n'
MANUAL = SubtitleSource.YOUTUBE_MANUAL
STT = SubtitleSource.STT


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "retry.db"}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    settings = Settings(_env_file=None, data_dir=tmp_path)
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    yield settings, factory
    engine.dispose()


@pytest.fixture
def client(database):
    settings, _factory = database
    with TestClient(create_app(settings)) as c:
        c.portal.call(c.app.state.video_import_scheduler.stop)
        yield c


def failed(factory, *, source=None, progress=0, youtube_id='abcdefghijk'):
    with factory() as s:
        v = Video(youtube_video_id=youtube_id, youtube_url=f'https://youtu.be/{youtube_id}',
                  status=VideoStatus.FAILED, subtitle_source=source,
                  subtitle_language='en' if source else None, subtitle_preference='auto_only')
        s.add(v); s.flush()
        j = ProcessingJob(video_id=v.id, stage=ProcessingStage.FAILED, status=JobStatus.FAILED,
                          progress=progress, error_code='TEST_FAILURE', error_message='Original failure',
                          finished_at=datetime.now(UTC))
        s.add(j); s.commit()
        return v.id, j.id


def raw_caption(factory, vid):
    with factory() as s:
        persist_raw_cues(s, vid, parse_vtt(VTT), MANUAL)
        s.commit()


def stt_data():
    return TranscriptionData('en', 1.0, 2.0, 2.0, (TranscriptionSegmentData(
        0, 0.0, 2.0, ' Spoken English.', (
            TranscriptionWordData(' Spoken', 0.1, 0.8, 0.9),
            TranscriptionWordData(' English.', 0.8, 1.8, 0.8)), {'segment_id': 0}),))


def request(jid, key='retry-1'):
    return RetryVideoRequest(expected_job_id=jid, idempotency_key=key)


def count_jobs(factory):
    with factory() as s: return s.scalar(select(func.count()).select_from(ProcessingJob))


def row_snapshot(factory, model, video_id=None):
    with factory() as s:
        query = select(model).order_by(model.id)
        if video_id is not None: query = query.where(model.video_id == video_id)
        return [tuple(getattr(row, c.name) for c in model.__table__.columns) for row in s.scalars(query)]


@pytest.mark.parametrize('source', [MANUAL, STT])
def test_complete_raw_resumes_without_external_work_and_retains_old_evidence(database, source):
    settings, factory = database
    vid, jid = failed(factory, source=source, progress=80)
    if source == MANUAL:
        raw_caption(factory, vid)
        CaptionStore(settings.data_dir).save(vid, VTT)
    else:
        with factory() as s:
            persist_stt_transcript(s, vid, stt_data()); s.commit()
    old_job = row_snapshot(factory, ProcessingJob, vid)[0]
    old_cues = row_snapshot(factory, RawTranscriptCue, vid)
    old_words = row_snapshot(factory, RawTranscriptWord, vid)
    with factory() as s: result, reused = retry_video(s, vid, request(jid), settings.data_dir)
    assert not reused and result.job.stage == 'normalizing' and result.job.progress == 80
    async def forbidden(*args): raise AssertionError('must reuse saved Raw')
    pipeline = VideoImportPipeline(factory, settings.data_dir, forbidden, forbidden, forbidden,
                                   audio_fetcher=forbidden, audio_transcriber=forbidden, settings=settings)
    asyncio.run(pipeline.run(vid, result.job.id))
    with factory() as s:
        assert s.get(Video, vid).status == 'ready'
        assert s.get(ProcessingJob, result.job.id).status == 'completed'
        assert s.get(ProcessingJob, result.job.id).started_at is not None
        assert s.get(Video, vid).subtitle_preference == 'auto_only'
    assert old_job in row_snapshot(factory, ProcessingJob, vid)
    assert row_snapshot(factory, RawTranscriptCue, vid) == old_cues
    assert row_snapshot(factory, RawTranscriptWord, vid) == old_words
    with factory() as s: replay, reused = retry_video(s, vid, request(jid), settings.data_dir)
    assert reused and replay == result and count_jobs(factory) == 2


def test_saved_vtt_resumes_parse_without_refetch(database):
    settings, factory = database
    vid, jid = failed(factory, source=MANUAL, progress=35)
    path = CaptionStore(settings.data_dir).save(vid, VTT)
    with factory() as s: result, _ = retry_video(s, vid, request(jid), settings.data_dir)
    assert result.job.stage == 'fetching_captions' and result.job.progress == 35
    async def forbidden(*args): raise AssertionError('must not fetch a new source')
    pipeline = VideoImportPipeline(factory, settings.data_dir, forbidden, forbidden, forbidden, settings=settings)
    asyncio.run(pipeline.run(vid, result.job.id))
    assert path.read_bytes() == VTT
    with factory() as s:
        assert s.get(Video, vid).status == 'ready'
        assert s.get(ProcessingJob, jid).status == 'failed'
        assert s.scalar(select(func.count()).select_from(RawTranscriptCue)) == 1


@pytest.mark.parametrize('progress', [0, 10, 20, 40])
def test_no_source_restarts_first_import(database, progress):
    settings, factory = database
    vid, jid = failed(factory, progress=progress)
    with factory() as s: result, _ = retry_video(s, vid, request(jid), settings.data_dir)
    assert (result.job.stage, result.job.progress) == ('fetching_metadata', 0)


def test_fixed_stt_without_raw_reacquires_audio_and_preserves_unknown_files(database):
    settings, factory = database
    vid, jid = failed(factory, source=STT, progress=40)
    directory = settings.data_dir / 'videos' / vid / 'audio'
    directory.mkdir(parents=True)
    (directory / 'source.webm').write_bytes(b'old temp audio')
    (directory / 'personal.txt').write_text('keep')
    with factory() as s: result, _ = retry_video(s, vid, request(jid), settings.data_dir)
    assert (result.job.stage, result.job.progress) == ('downloading_audio', 20)
    assert not (directory / 'source.webm').exists()
    assert (directory / 'personal.txt').read_text() == 'keep'
    async def forbidden(*args): raise AssertionError('fixed STT must not rediscover captions')
    async def acquire(video_id, url):
        from app.services.processing.audio_store import AudioStore
        store = AudioStore(settings.data_dir)
        target = store.prepare(video_id)
        path = target.directory / 'source.webm'; path.write_bytes(b'new audio')
        return store.finalize(video_id, target, path)
    async def transcribe(path): return stt_data()
    pipeline = VideoImportPipeline(factory, settings.data_dir, forbidden, forbidden, forbidden,
                                   audio_fetcher=acquire, audio_transcriber=transcribe, settings=settings)
    asyncio.run(pipeline.run(vid, result.job.id))
    with factory() as s:
        assert s.get(Video, vid).status == 'ready' and s.get(Video, vid).subtitle_source == 'stt'
        assert s.get(ProcessingJob, jid).status == 'failed'
        assert s.scalar(select(func.count()).select_from(RawTranscriptWord)) == 2
    assert not (directory / 'source.webm').exists()
    assert (directory / 'personal.txt').read_text() == 'keep'


@pytest.mark.parametrize('case', [
    'raw_without_checkpoint', 'raw_gap', 'raw_wrong_source', 'raw_vtt_mismatch',
    'orphan_words', 'missing_raw_after_80', 'missing_vtt', 'invalid_vtt',
    'orphan_vtt', 'source_without_language', 'orphan_revision', 'orphan_run',
    'symlink_vtt', 'cross_cue_word', 'word_gap',
])
def test_inconsistent_evidence_rejected_without_new_job_or_raw_mutation(database, case):
    settings, factory = database
    progress = 80 if case.startswith('raw_') or case in ('cross_cue_word', 'word_gap', 'missing_raw_after_80') else 35
    source = MANUAL if case != 'orphan_vtt' else None
    vid, jid = failed(factory, source=source, progress=progress)
    if case.startswith('raw_') or case in ('cross_cue_word', 'word_gap'):
        raw_caption(factory, vid)
    if case in ('invalid_vtt', 'source_without_language', 'orphan_vtt', 'symlink_vtt'):
        CaptionStore(settings.data_dir).save(vid, b'bad' if case == 'invalid_vtt' else VTT)
    with factory() as s:
        if case == 'raw_without_checkpoint': s.get(ProcessingJob, jid).progress = 35
        if case == 'raw_gap': s.scalar(select(RawTranscriptCue)).sequence_index = 1
        if case == 'raw_wrong_source': s.scalar(select(RawTranscriptCue)).source_type = STT
        if case == 'raw_vtt_mismatch': CaptionStore(settings.data_dir).save(vid, VTT.replace(b'Hello', b'Changed'))
        if case in ('orphan_words', 'cross_cue_word', 'word_gap'):
            s.add(RawTranscriptWord(video_id=vid, cue_id=None, sequence_index=1 if case == 'word_gap' else 0,
                                    text='word', start_seconds=0, end_seconds=1, confidence=1))
        if case == 'source_without_language': s.get(Video, vid).subtitle_language = None
        if case == 'orphan_revision': s.add(TranscriptRevision(video_id=vid, origin='generated', revision_number=1))
        if case == 'orphan_run': s.add(TranscriptNormalizationRun(video_id=vid, job_id=jid, method='deterministic',
                                    normalization_version=2, input_unit_count=1))
        s.commit()
    if case == 'symlink_vtt':
        path = CaptionStore(settings.data_dir).path_for(vid)
        path.unlink(); target = settings.data_dir / 'outside.vtt'; target.write_bytes(VTT); path.symlink_to(target)
    before = row_snapshot(factory, RawTranscriptCue, vid), row_snapshot(factory, RawTranscriptWord, vid)
    with factory() as s:
        with pytest.raises(AppError) as caught: retry_video(s, vid, request(jid), settings.data_dir)
    assert caught.value.code == 'RETRY_EVIDENCE_CONFLICT'
    assert count_jobs(factory) == 1
    assert before == (row_snapshot(factory, RawTranscriptCue, vid), row_snapshot(factory, RawTranscriptWord, vid))


@pytest.mark.parametrize('case', ['ready', 'active', 'stale', 'published'])
def test_nonfailed_or_current_publication_cannot_retry(client, database, case):
    _settings, factory = database
    vid, jid = failed(factory)
    with factory() as s:
        if case == 'ready': s.get(Video, vid).status = 'ready'
        if case == 'active': s.add(ProcessingJob(video_id=vid, stage='fetching_metadata', status='pending',
                                  created_at=datetime.now(UTC) - timedelta(days=1)))
        if case == 'published':
            revision = TranscriptRevision(video_id=vid, origin='generated', revision_number=1)
            s.add(revision); s.flush(); s.get(Video, vid).current_revision_id = revision.id
        s.commit()
    response = client.post(f'/api/videos/{vid}/retry', json=request('stale' if case == 'stale' else jid).model_dump())
    assert response.status_code == 409
    assert count_jobs(factory) == (2 if case == 'active' else 1)


def test_concurrent_same_key_creates_one_new_job_and_replays(client, database):
    _settings, factory = database
    vid, jid = failed(factory)
    payload = request(jid).model_dump()
    barrier = Barrier(2)
    def post():
        barrier.wait(); r = client.post(f'/api/videos/{vid}/retry', json=payload)
        return r.status_code, r.json()
    with ThreadPoolExecutor(2) as pool:
        results = [pool.submit(post) for _ in range(2)]
        results = [f.result(timeout=15) for f in results]
    assert sorted(r[0] for r in results) == [200, 202]
    assert results[0][1] == results[1][1] and count_jobs(factory) == 2
    conflict = client.post(f'/api/videos/{vid}/retry', json=payload | {'expected_job_id': 'different'})
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(VideoImportRetryRequest)) == 1


def test_retry_and_idempotency_record_roll_back_together(database):
    settings, factory = database
    vid, jid = failed(factory)
    engine = factory.kw['bind']
    def fail(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith('INSERT INTO video_import_retry_requests'): raise RuntimeError('late write failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with factory() as s:
            with pytest.raises(RuntimeError): retry_video(s, vid, request(jid), settings.data_dir)
    finally: event.remove(engine, 'before_cursor_execute', fail)
    with factory() as s:
        assert s.get(Video, vid).status == 'failed'
        assert s.scalar(select(func.count()).select_from(VideoImportRetryRequest)) == 0
    assert count_jobs(factory) == 1


def test_retry_endpoint_strict_fields_and_missing_video(client):
    assert client.post('/api/videos/missing/retry', json=request('missing').model_dump()).status_code == 404
    for payload in ({}, {'expected_job_id': 'x', 'idempotency_key': 'k', 'source': 'stt'},
                    {'expected_job_id': '', 'idempotency_key': 'k'}):
        assert client.post('/api/videos/missing/retry', json=payload).status_code == 422


def test_new_attempt_is_latest_even_if_old_timestamp_is_in_future(database):
    settings, factory = database
    vid, jid = failed(factory)
    with factory() as s:
        s.get(ProcessingJob, jid).created_at = datetime.now(UTC) + timedelta(days=1)
        s.commit()
    with factory() as s: result, _ = retry_video(s, vid, request(jid), settings.data_dir)
    from app.repositories.videos import VideoRepository
    with factory() as s: assert VideoRepository(s).get_latest_job(vid).id == result.job.id


def test_retry_migration_refuses_loss_of_accepted_requests(client, database):
    settings, factory = database
    vid, jid = failed(factory)
    assert client.post(f'/api/videos/{vid}/retry', json=request(jid).model_dump()).status_code == 202
    with pytest.raises(RuntimeError, match='Cannot downgrade'):
        command.downgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), '012_video_collections')
    with factory() as s: assert s.scalar(select(func.count()).select_from(VideoImportRetryRequest)) == 1


def test_batch_retry_record_failure_rolls_back_all_attempts_and_bindings(client, database):
    _settings, factory = database
    p = client.post('/api/video-import-previews', json={'input_kind': 'multiple', 'urls': [
        'https://youtu.be/abcdefghijk', 'https://youtu.be/lmnopqrstuv']}).json()
    b = client.post('/api/video-import-batches', json={'preview_id': p['id'],
        'selected_item_ids': [i['id'] for i in p['items']], 'target': {'kind': 'none'},
        'idempotency_key': 'batch-before-retry'}).json()
    with factory() as s:
        for item in b['items']:
            s.get(Video, item['video']['id']).status = 'failed'
            s.get(ProcessingJob, item['job']['id']).status = 'failed'
            s.get(ProcessingJob, item['job']['id']).stage = 'failed'
        s.commit()
    payload = {'item_ids': [i['id'] for i in b['items']],
               'expected_job_ids': {i['id']: i['job']['id'] for i in b['items']}, 'idempotency_key': 'atomic-retry'}
    engine = client.app.state.session_factory.kw['bind']
    def fail(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith('INSERT INTO video_import_retry_requests'): raise RuntimeError('retry record failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='retry record failure'):
            client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload)
    finally: event.remove(engine, 'before_cursor_execute', fail)
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(ProcessingJob)) == 2
        assert s.scalar(select(func.count()).select_from(VideoImportRetryBinding)) == 0
        assert all(v.status == 'failed' for v in s.scalars(select(Video)))
    response = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload)
    assert response.status_code == 202
    assert [i['status'] for i in response.json()['items']] == ['accepted', 'accepted']
    assert count_jobs(factory) == 4
