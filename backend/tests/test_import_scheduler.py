import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.enums import SubtitleSource
from app.db.models import Video, ProcessingJob
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.services.videos import save_new_video
from app.services.youtube.captions import CaptionCandidate
from app.services.youtube.metadata import MetadataFetchError, YouTubeMetadata
from app.services.youtube.parser import extract_video_id
from test_import_retries import failed, raw_caption, VTT

IDS = ['abcdefghijk', 'lmnopqrstuv', 'zyxwvutsrqp', '0123456789a', 'ABCDEFGHIJK']


class Control:
    def __init__(self):
        self.gate = asyncio.Event(); self.gate.set()
        self.entered = asyncio.Event()
        self.started = []
        self.fail_ids = set()
        self.active = 0
        self.maximum = 0
        self.completed = []

    async def metadata(self, url):
        identifier = extract_video_id(url)
        self.started.append(identifier)
        self.entered.set()
        await self.gate.wait()
        if identifier in self.fail_ids: raise MetadataFetchError('controlled failure')
        return YouTubeMetadata(identifier, 'Lesson ' + identifier, 'Test', 2, None)

    async def captions(self, url):
        return [CaptionCandidate(SubtitleSource.YOUTUBE_AUTO, 'en', 'English', 'https://test/caption', 'vtt')]

    async def download(self, candidate): return VTT

    def track(self, client):
        pipeline = client.app.state.video_import_pipeline
        run = pipeline.run
        async def tracked(*args):
            self.active += 1; self.maximum = max(self.maximum, self.active)
            try: await run(*args)
            finally:
                self.active -= 1; self.completed.append(args[1])
        pipeline.run = tracked


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "scheduler.db"}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    settings = Settings(_env_file=None, data_dir=tmp_path)
    control = Control()
    return settings, control


@pytest.fixture
def client(setup):
    settings, control = setup
    with TestClient(create_app(settings, control.metadata, control.captions, control.download)) as c:
        control.track(c)
        yield c


def submit_batch(client, ids, key='batch-1'):
    p = client.post('/api/video-import-previews', json={'input_kind': 'multiple',
                    'urls': [f'https://youtu.be/{i}' for i in ids]}).json()
    response = client.post('/api/video-import-batches', json={'preview_id': p['id'],
        'selected_item_ids': [i['id'] for i in p['items']], 'idempotency_key': key,
        'target': {'kind': 'new', 'name': 'Series'}})
    assert response.status_code == 202, response.text
    return response.json()


def settled(client): client.portal.call(client.app.state.video_import_scheduler.wait_idle)


def batch(client, identifier): return client.get('/api/video-import-batches/' + identifier).json()


def test_single_batch_retry_and_unnotified_work_share_one_consumer(client, setup):
    _settings, control = setup
    client.portal.call(control.gate.clear)
    first = client.post('/api/videos', json={'url': 'https://youtu.be/' + IDS[0]})
    assert first.status_code == 202  # Returns while metadata is deliberately blocked.
    client.portal.call(control.entered.wait)
    b = submit_batch(client, IDS[1:3])
    factory = client.app.state.session_factory
    with factory() as s:
        save_new_video(s, IDS[3], 'manual_first'); s.commit()  # No wake notification.
    vid, jid = failed(factory, youtube_id=IDS[4])
    retried = client.post(f'/api/videos/{vid}/retry', json={'expected_job_id': jid, 'idempotency_key': 'retry'})
    assert retried.status_code == 202
    assert control.started == [IDS[0]] and control.maximum == 1
    assert batch(client, b['id'])['counts']['waiting'] == 2
    client.portal.call(control.gate.set)
    settled(client)
    assert len(control.completed) == 5 and control.maximum == 1
    assert set(control.started) == set(IDS)
    assert batch(client, b['id'])['counts']['ready'] == 2
    with factory() as s:
        assert s.get(ProcessingJob, jid).status == 'failed'
        assert s.get(Video, vid).status == 'ready'


def test_periodic_scan_recovers_a_lost_wake_without_http_request(client, setup):
    _settings, control = setup
    scheduler = client.app.state.video_import_scheduler
    scheduler.poll_interval = 0.02
    async def lost_wake(): pass
    scheduler.wake = lost_wake
    b = submit_batch(client, IDS[:2])
    # No further HTTP requests drive processing. Persistence is enough for the scan.
    settled(client)
    assert len(control.completed) == 2 and control.maximum == 1
    assert batch(client, b['id'])['status'] == 'completed'


def test_partial_failure_batch_retry_and_idempotent_replay(client, setup):
    _settings, control = setup
    control.fail_ids.add(IDS[1])
    b = submit_batch(client, IDS[:3])
    settled(client)
    state = batch(client, b['id'])
    assert state['counts']['ready'] == 2 and state['counts']['failed'] == 1
    assert state['status'] == 'completed_with_errors'
    items = state['items']
    old_job = items[1]['job']['id']
    control.fail_ids.clear()
    payload = {'item_ids': [i['id'] for i in items],
               'expected_job_ids': {i['id']: i['job']['id'] for i in items}, 'idempotency_key': 'batch-retry'}
    response = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload)
    assert response.status_code == 202, response.text
    assert [i['status'] for i in response.json()['items']] == ['skipped', 'accepted', 'skipped']
    settled(client)
    current = batch(client, b['id'])
    assert current['counts']['ready'] == 3
    assert current['items'][1]['job']['id'] != old_job
    replay = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload)
    assert replay.status_code == 200 and replay.json() == response.json()
    assert control.started.count(IDS[1]) == 2 and control.started.count(IDS[0]) == 1
    with client.app.state.session_factory() as s:
        assert s.get(ProcessingJob, old_job).status == 'failed'
        assert s.scalar(select(func.count()).select_from(ProcessingJob)) == 4


def test_one_evidence_conflict_does_not_block_other_retry(client, setup):
    _settings, control = setup
    control.fail_ids.update(IDS[:2])
    b = submit_batch(client, IDS[:2]); settled(client)
    state = batch(client, b['id'])
    with client.app.state.session_factory() as s:
        # An orphan source file makes only this item unsafe to restart.
        vid = state['items'][0]['video']['id']
        from app.services.processing.caption_store import CaptionStore
        CaptionStore(client.app.state.data_dir).save(vid, VTT)
    control.fail_ids.clear()
    payload = {'item_ids': [i['id'] for i in state['items']],
               'expected_job_ids': {i['id']: i['job']['id'] for i in state['items']}, 'idempotency_key': 'mixed'}
    result = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload)
    assert result.status_code == 202
    assert [i['status'] for i in result.json()['items']] == ['rejected', 'accepted']
    assert result.json()['items'][0]['error']['code'] == 'RETRY_EVIDENCE_CONFLICT'
    settled(client)
    assert batch(client, b['id'])['counts']['ready'] == 1


def test_concurrent_different_retry_keys_do_not_duplicate_attempts(client, setup):
    _settings, control = setup
    control.fail_ids.add(IDS[0])
    b = submit_batch(client, IDS[:1]); settled(client)
    item = batch(client, b['id'])['items'][0]
    control.fail_ids.clear()
    barrier = Barrier(2)
    def retry(key):
        barrier.wait()
        return client.post(f'/api/videos/{item["video"]["id"]}/retry', json={
            'expected_job_id': item['job']['id'], 'idempotency_key': key}).status_code
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(retry, key) for key in ('one', 'two')]
        assert sorted(f.result(timeout=15) for f in futures) == [202, 409]
    settled(client)
    with client.app.state.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(ProcessingJob)) == 2
    # Single-video retry doesn't rewrite historical batch bindings.
    old = batch(client, b['id'])
    assert old['counts']['failed'] == 1 and old['items'][0]['video']['status'] == 'ready'


def test_shutdown_fails_active_and_restart_only_resumes_waiting(setup):
    settings, control = setup
    with TestClient(create_app(settings, control.metadata, control.captions, control.download)) as c:
        control.gate.clear()
        first = c.post('/api/videos', json={'url': 'https://youtu.be/' + IDS[0]}).json()
        c.portal.call(control.entered.wait)
        b = submit_batch(c, IDS[1:3])
    new = Control()
    with TestClient(create_app(settings, new.metadata, new.captions, new.download)) as c:
        settled(c)
        original = c.get('/api/videos/' + first['video']['id']).json()
        assert original['status'] == 'failed' and original['processing']['error_code'] == 'PROCESS_INTERRUPTED'
        assert batch(c, b['id'])['counts']['ready'] == 2
        assert set(new.started) == set(IDS[1:3])
        with c.app.state.session_factory() as s:
            assert s.scalar(select(func.count()).select_from(ProcessingJob)) == 3


def test_hard_restart_narrow_normalization_recovery_and_old_failure_protection(setup):
    settings, control = setup
    engine = create_db_engine(settings); factory = create_session_factory(engine)
    normal_vid, normal_jid = failed(factory, source=SubtitleSource.YOUTUBE_MANUAL, progress=80, youtube_id=IDS[0])
    raw_caption(factory, normal_vid)
    interrupted_vid, interrupted_jid = failed(factory, youtube_id=IDS[1])
    old_vid, old_jid = failed(factory, youtube_id=IDS[2])
    with factory() as s:
        v, j = save_new_video(s, IDS[3], 'manual_first')
        pending_vid = v.id
        s.get(Video, normal_vid).status = 'processing'
        s.get(ProcessingJob, normal_jid).status = 'running'
        s.get(ProcessingJob, normal_jid).stage = 'normalizing'
        s.get(Video, interrupted_vid).status = 'processing'
        s.get(ProcessingJob, interrupted_jid).status = 'running'
        s.get(ProcessingJob, interrupted_jid).stage = 'transcribing'
        s.get(ProcessingJob, interrupted_jid).progress = 40
        s.commit()
    audio_dir = settings.data_dir / 'videos' / interrupted_vid / 'audio'
    audio_dir.mkdir(parents=True); (audio_dir / 'source.webm').write_bytes(b'temporary')
    before = None
    with factory() as s: before = s.get(ProcessingJob, old_jid).error_message
    with TestClient(create_app(settings, control.metadata, control.captions, control.download)) as c:
        settled(c)
        with c.app.state.session_factory() as s:
            assert s.get(Video, normal_vid).status == s.get(Video, pending_vid).status == 'ready'
            assert s.get(ProcessingJob, normal_jid).status == 'completed'
            assert s.get(ProcessingJob, interrupted_jid).error_code == 'PROCESS_INTERRUPTED'
            assert s.get(ProcessingJob, old_jid).error_message == before
            assert s.get(Video, old_vid).status == 'failed'
            assert s.scalar(select(func.count()).select_from(ProcessingJob)) == 4
        assert not audio_dir.exists()
        assert control.started == [IDS[3]]
    engine.dispose()


def test_reused_batch_retry_pins_only_selected_batch_attempt(client, setup):
    _settings, control = setup
    control.fail_ids.add(IDS[0])
    a = submit_batch(client, IDS[:1]); settled(client)
    b = submit_batch(client, IDS[:1], key='reuse'); settled(client)
    item_b = batch(client, b['id'])['items'][0]
    assert item_b['disposition'] == 'reused'
    retry_payload = {'item_ids': [item_b['id']], 'expected_job_ids': {item_b['id']: item_b['job']['id']}, 'idempotency_key': 'pin'}
    result = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=retry_payload)
    assert result.status_code == 202 and result.json()['items'][0]['status'] == 'accepted'
    settled(client)  # Still fails, so a later attempt can be made through the video endpoint.
    pinned = batch(client, b['id'])['items'][0]['job']['id']
    control.fail_ids.clear()
    video_retry = client.post('/api/videos/' + item_b['video']['id'] + '/retry', json={
        'expected_job_id': pinned, 'idempotency_key': 'next-attempt'})
    assert video_retry.status_code == 202
    settled(client)
    current_b = batch(client, b['id'])
    assert current_b['items'][0]['job']['id'] == pinned and current_b['counts']['failed'] == 1
    assert current_b['items'][0]['video']['status'] == 'ready'
    assert batch(client, a['id'])['items'][0]['job']['id'] == a['items'][0]['job']['id']


def test_batch_retry_foreign_selection_invalid_shape_and_unavailable_skip(client, setup):
    _settings, control = setup
    p = client.post('/api/video-import-previews', json={'input_kind': 'multiple', 'urls': [
        'https://youtu.be/' + IDS[0], 'invalid']}).json()
    r = client.post('/api/video-import-batches', json={'preview_id': p['id'],
        'selected_item_ids': [p['items'][0]['id']], 'target': {'kind': 'none'}, 'idempotency_key': 'with-invalid'})
    b = r.json(); settled(client)
    unavailable = b['items'][1]
    payload = {'item_ids': [unavailable['id']], 'expected_job_ids': {unavailable['id']: None}, 'idempotency_key': 'skip'}
    response = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload)
    assert response.status_code == 202 and response.json()['items'][0]['status'] == 'skipped'
    for change in ({'item_ids': []}, {'item_ids': ['foreign'], 'expected_job_ids': {'foreign': None}},
                   {'expected_job_ids': {}}, {'item_ids': [unavailable['id']] * 2}):
        result = client.post('/api/video-import-batches/' + b['id'] + '/retry', json=payload | change | {'idempotency_key': 'invalid'})
        assert result.status_code == 422
    assert len(control.completed) == 1


@pytest.mark.parametrize('failure', ['exception', 'no_progress'])
def test_unexpected_pipeline_failure_does_not_stop_consumer(client, setup, failure):
    pipeline = client.app.state.video_import_pipeline
    run = pipeline.run
    first = True
    async def broken_once(*args):
        nonlocal first
        if first:
            first = False
            if failure == 'exception': raise RuntimeError('controlled unexpected failure')
            return
        await run(*args)
    pipeline.run = broken_once
    b = submit_batch(client, IDS[:2]); settled(client)
    current = batch(client, b['id'])
    assert current['counts']['failed'] == 1 and current['counts']['ready'] == 1
    assert current['items'][0]['job']['error_code'] == 'PROCESS_STATE_CONFLICT'


def test_cancel_during_delayed_claim_cannot_leave_job_running(setup):
    from threading import Event
    from app.services.processing.scheduler import VideoImportScheduler
    from app.services.processing.video_import import VideoImportPipeline
    settings, control = setup
    engine = create_db_engine(settings); factory = create_session_factory(engine)
    with factory() as s:
        video, job = save_new_video(s, IDS[0], 'manual_first'); s.commit()
        jid = job.id
    pipeline = VideoImportPipeline(factory, settings.data_dir, control.metadata,
                                   control.captions, control.download, settings=settings)
    claim = pipeline.jobs.claim_metadata
    entered, release, done = Event(), Event(), Event()
    def delayed(*args):
        entered.set()
        assert release.wait(timeout=5)
        try: return claim(*args)
        finally: done.set()
    pipeline.jobs.claim_metadata = delayed
    async def run():
        scheduler = VideoImportScheduler(pipeline, factory)
        scheduler.start()
        assert await asyncio.to_thread(entered.wait, 5)
        try: await scheduler.stop()
        finally: release.set()
        assert await asyncio.to_thread(done.wait, 5)
    asyncio.run(run())
    with factory() as s:
        assert s.get(ProcessingJob, jid).status == 'failed'
        assert s.get(ProcessingJob, jid).error_code == 'PROCESS_INTERRUPTED'
    assert control.started == []
    engine.dispose()


def test_wait_idle_keeps_waiting_when_a_pending_job_is_claimed_during_query(monkeypatch):
    from app.services.processing import scheduler as module

    async def run():
        scheduler = module.VideoImportScheduler(None, None)
        claimed = False

        def pending_query(_factory):
            nonlocal claimed
            if not claimed:
                claimed = True
                scheduler.active_job = ('video-id', 'job-id')
            return None

        monkeypatch.setattr(module, 'next_pending_job', pending_query)
        waiter = asyncio.create_task(scheduler.wait_idle(timeout=1))
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(waiter), timeout=0.05)
        finally:
            scheduler.active_job = None
            await waiter

    asyncio.run(run())
