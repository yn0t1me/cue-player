import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.config import Settings
from app.core.enums import JobStatus, ProcessingStage, SubtitleSource, VideoStatus
from app.db.models import (
    LearningTranscriptSegment,
    ProcessingJob,
    RawTranscriptCue,
    RawTranscriptWord,
    TranscriptChunkSegment,
    TranscriptMark,
    Video,
)
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.services.processing.audio_store import AudioArtifact
from app.services.transcript import (
    TranscriptionData,
    TranscriptionSegmentData,
    TranscriptionWordData,
)
from app.services.youtube.captions import CaptionCandidate
from app.services.youtube.metadata import MetadataFetchError, YouTubeMetadata
from app.services.youtube.parser import extract_video_id


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "api.db"}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    async def fetch_metadata(url):
        youtube_id = extract_video_id(url)
        return YouTubeMetadata(youtube_id, f'Lesson {youtube_id}', 'Test channel', 90, 'https://img.test/thumb.jpg')

    async def discover_captions(_url):
        return [CaptionCandidate(SubtitleSource.YOUTUBE_MANUAL, 'en', 'English',
                                 'https://youtube.test/caption', 'vtt')]

    async def download_caption(_candidate):
        return b'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n'

    with TestClient(create_app(
            Settings(_env_file=None, data_dir=tmp_path), fetch_metadata,
            discover_captions, download_caption)) as client:
        # Existing subtitle/notes tests need a completed fixture import, not timing assumptions.
        post = client.post
        def post_and_settle(url, **kwargs):
            result = post(url, **kwargs)
            if (url == '/api/videos' and result.status_code in (200, 202)
                    and client.app.state.video_import_scheduler._task is not None):
                client.portal.call(client.app.state.video_import_scheduler.wait_idle)
            return result
        client.post = post_and_settle
        yield client


def _source_payload(client, video_id: str, text: str) -> dict:
    # Automatic-source v2 publication allows text edits while rebuilding timing.
    with client.app.state.session_factory() as session:
        session.get(Video, video_id).subtitle_source = SubtitleSource.YOUTUBE_AUTO
        session.commit()
    from app.services.processing.caption_store import CaptionStore
    CaptionStore(client.app.state.data_dir).save(video_id,
        b'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello<00:00:00.500> there\n')
    response = client.get(f'/api/videos/{video_id}/transcript/learning-source')
    assert response.status_code == 200, response.text
    source = response.json()
    result = json.dumps(dict(format='learning-result-v2', source_video_id=source['source_video_id'],
        source_digest=source['source_digest'], segments=[dict(
            first_unit_id=source['units'][0]['id'], last_unit_id=source['units'][-1]['id'],
            text=text, translation_zh='测试译文。')]))
    preview = client.post(f'/api/videos/{video_id}/transcript/source-learning/preview',
                          json={'result': result})
    assert preview.status_code == 200, preview.text
    return dict(result=result, expected_revision_id=preview.json()['base_revision_id'],
                preview_digest=preview.json()['preview_digest'])


def test_create_list_detail_and_duplicate(client):
    assert client.get('/api/videos').json() == {'items': []}
    created = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI?t=2'})
    assert created.status_code == 202
    body = created.json()
    assert body['already_exists'] is False
    item = body['video']
    assert item['status'] == 'processing'
    assert item['subtitle_preference'] == 'manual_first'
    assert item['title'] is None
    assert item['youtube_url'] == 'https://www.youtube.com/watch?v=aB3_dE-fGhI'
    assert item['processing'] == body['job']
    assert body['job']['status'] == 'pending'
    assert body['job']['progress'] == 0
    refreshed = client.get(f'/api/videos/{item["id"]}').json()
    assert refreshed['title'] == 'Lesson aB3_dE-fGhI'
    assert refreshed['channel_title'] == 'Test channel'
    assert refreshed['duration_seconds'] == 90
    assert refreshed['thumbnail_url'] == 'https://img.test/thumb.jpg'
    assert refreshed['status'] == 'ready'
    assert refreshed['processing']['stage'] == 'completed'
    assert refreshed['processing']['status'] == 'completed'
    assert refreshed['processing']['progress'] == 100
    assert refreshed['subtitle_source'] == 'youtube_manual'
    assert refreshed['subtitle_language'] == 'en'
    assert client.get('/api/videos').json() == {'items': [refreshed]}
    duplicate = client.post('/api/videos', json={'url': 'https://youtube.com/shorts/aB3_dE-fGhI'})
    assert duplicate.status_code == 200
    assert duplicate.json() == {'already_exists': True, 'video': refreshed, 'job': refreshed['processing']}
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Video)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 1
        assert session.scalar(select(func.count()).select_from(RawTranscriptCue)) == 1
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord)) == 0
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 1
        job = session.scalar(select(ProcessingJob))
        assert job.started_at is not None and job.finished_at is not None

    transcript = client.get(f'/api/videos/{item["id"]}/transcript')
    assert transcript.status_code == 200
    assert UUID(transcript.json()['revision_id'])
    assert transcript.json() == {
        'video_id': item['id'],
        'revision_id': transcript.json()['revision_id'],
        'origin': 'generated',
        'normalization_version': 2,
        'segments': [{
            'id': transcript.json()['segments'][0]['id'],
            'sequence_index': 0,
            'start': 0.0,
            'end': 1.0,
            'text': 'Hello',
            'translation_zh': None,
        }],
    }
    assert set(transcript.json()['segments'][0]) == {
        'id', 'sequence_index', 'start', 'end', 'text', 'translation_zh'}


@pytest.mark.parametrize('body,code', [
    ({'url': 'https://evil.test/watch?v=aB3_dE-fGhI'}, 'INVALID_YOUTUBE_URL'),
    ({'url': ''}, 'VALIDATION_ERROR'), ({}, 'VALIDATION_ERROR'),
    ({'url': 123}, 'VALIDATION_ERROR'), ({'url': 'x', 'extra': True}, 'VALIDATION_ERROR'),
])
def test_invalid_input_does_not_write(client, body, code):
    response = client.post('/api/videos', json=body)
    assert response.status_code == 422
    assert response.json()['error']['code'] == code
    assert client.get('/api/videos').json() == {'items': []}


def test_missing_video(client):
    response = client.get('/api/videos/missing')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'VIDEO_NOT_FOUND'
    transcript = client.get('/api/videos/missing/transcript')
    assert transcript.status_code == 404
    assert transcript.json()['error']['code'] == 'VIDEO_NOT_FOUND'
    exported = client.get('/api/videos/missing/transcript/export.srt')
    assert exported.status_code == 404


@pytest.mark.parametrize('source', [
    SubtitleSource.YOUTUBE_MANUAL, SubtitleSource.YOUTUBE_AUTO, SubtitleSource.STT,
])
def test_raw_srt_export_is_source_independent_and_ignores_learning_text(client, source):
    created = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()
    video_id = created['video']['id']
    with client.app.state.session_factory() as session:
        video = session.get(Video, video_id)
        video.subtitle_source = source
        raw = session.scalar(select(RawTranscriptCue))
        raw.start_seconds = 3661.25
        raw.end_seconds = 3662.5
        raw.text = '<i>Fish &amp; chips</i>\nnow'
        learning = session.scalar(select(LearningTranscriptSegment))
        learning.text = 'Changed learning text.'
        session.commit()

    response = client.get(f'/api/videos/{video_id}/transcript/export.srt')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/x-subrip')
    assert response.headers['content-disposition'] == 'attachment; filename="aB3_dE-fGhI-raw.srt"'
    assert response.text == '1\n01:01:01,250 --> 01:01:02,500\nFish & chips now\n'
    assert 'Changed learning' not in response.text
    assert client.get(f'/api/videos/{video_id}/transcript').json()['segments'][0]['text'] == (
        'Changed learning text.')


def test_raw_srt_export_requires_ready_video_and_raw_cues(client):
    created = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()
    video_id = created['video']['id']
    with client.app.state.session_factory() as session:
        session.get(Video, video_id).status = VideoStatus.PROCESSING
        session.commit()
    response = client.get(f'/api/videos/{video_id}/transcript/export.srt')
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'TRANSCRIPT_NOT_READY'
    with client.app.state.session_factory() as session:
        session.get(Video, video_id).status = VideoStatus.READY
        session.scalar(select(RawTranscriptCue)).text = '  '
        session.commit()
    response = client.get(f'/api/videos/{video_id}/transcript/export.srt')
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'RAW_TRANSCRIPT_UNAVAILABLE'


def test_raw_srt_export_keeps_zero_duration_cue_text(client):
    created = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()
    video_id = created['video']['id']
    with client.app.state.session_factory() as session:
        cue = session.scalar(select(RawTranscriptCue))
        cue.start_seconds = cue.end_seconds = 0.5
        session.commit()
    response = client.get(f'/api/videos/{video_id}/transcript/export.srt')
    assert response.status_code == 200
    assert response.text == '1\n00:00:00,500 --> 00:00:00,501\nHello\n'


def test_raw_srt_export_collapses_automatic_rolling_cues(client):
    created = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()
    video_id = created['video']['id']
    with client.app.state.session_factory() as session:
        video = session.get(Video, video_id)
        video.subtitle_source = SubtitleSource.YOUTUBE_AUTO
        first = session.scalar(select(RawTranscriptCue))
        first.text = 'We are'
        first.end_seconds = 0.01
        session.add(RawTranscriptCue(
            video_id=video_id, sequence_index=1, start_seconds=0.01,
            end_seconds=2.0, text='We are ready.',
            source_type=SubtitleSource.YOUTUBE_AUTO,
        ))
        session.commit()
    response = client.get(f'/api/videos/{video_id}/transcript/export.srt')
    assert response.status_code == 200
    assert response.text == '1\n00:00:00,000 --> 00:00:02,000\nWe are ready.\n'


def test_transcript_reports_processing_and_failed_videos(client):
    with client.app.state.session_factory() as session:
        processing = Video(youtube_video_id='pR0_cE-sSiN',
                           youtube_url='https://www.youtube.com/watch?v=pR0_cE-sSiN')
        failed = Video(youtube_video_id='fA1_lE-dVid',
                       youtube_url='https://www.youtube.com/watch?v=fA1_lE-dVid',
                       status=VideoStatus.FAILED)
        session.add_all([processing, failed])
        session.commit()
        ids = processing.id, failed.id
    pending = client.get(f'/api/videos/{ids[0]}/transcript')
    unavailable = client.get(f'/api/videos/{ids[1]}/transcript')
    assert (pending.status_code, pending.json()['error']['code']) == (
        409, 'TRANSCRIPT_NOT_READY')
    assert (unavailable.status_code, unavailable.json()['error']['code']) == (
        409, 'TRANSCRIPT_UNAVAILABLE')


def test_failed_duplicate_is_not_retried(client):
    result = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()
    with client.app.state.session_factory() as session:
        session.get(Video, result['video']['id']).status = VideoStatus.FAILED
        session.get(ProcessingJob, result['job']['id']).status = JobStatus.FAILED
        session.commit()
    duplicate = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()
    assert duplicate['video']['status'] == 'failed'
    assert duplicate['job']['id'] == result['job']['id']
    assert duplicate['job']['status'] == 'failed'


def test_parallel_duplicates_are_one_video_and_job(client):
    barrier = Barrier(4)
    def send(_):
        barrier.wait()
        return client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'})
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(4)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 202]
    assert len({r.json()['video']['id'] for r in responses}) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 1


def test_list_order_and_refresh_metadata(client):
    from datetime import UTC, datetime
    older = client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'}).json()['video']
    newer = client.post('/api/videos', json={'url': 'https://youtu.be/jK4_lM-nOpQ'}).json()['video']
    with client.app.state.session_factory() as session:
        session.get(Video, older['id']).created_at = datetime(2026, 1, 1, tzinfo=UTC)
        item = session.get(Video, newer['id'])
        item.created_at = datetime(2026, 1, 2, tzinfo=UTC)
        item.title = 'Persisted title'
        session.commit()
    items = client.get('/api/videos').json()['items']
    assert [item['id'] for item in items] == [newer['id'], older['id']]
    assert client.get(f'/api/videos/{newer["id"]}').json()['title'] == 'Persisted title'


def test_video_and_job_creation_is_atomic(client):
    from sqlalchemy import event
    def fail_job(*_):
        raise RuntimeError('intentional job failure')
    event.listen(ProcessingJob, 'before_insert', fail_job)
    try:
        with pytest.raises(RuntimeError, match='intentional job failure'):
            client.post('/api/videos', json={'url': 'https://youtu.be/aB3_dE-fGhI'})
    finally:
        event.remove(ProcessingJob, 'before_insert', fail_job)
    assert client.get('/api/videos').json() == {'items': []}


def test_metadata_failure_is_persisted_and_visible(client):
    async def fail(_url):
        raise MetadataFetchError('upstream details are not user-facing')

    client.app.state.video_import_pipeline.fetch_metadata = fail
    created = client.post('/api/videos', json={'url': 'https://youtu.be/zY5_xW-vUtS'})
    assert created.status_code == 202
    detail = client.get(f'/api/videos/{created.json()["video"]["id"]}').json()
    assert detail['status'] == 'failed'
    assert detail['processing']['status'] == 'failed'
    assert detail['processing']['stage'] == 'failed'
    assert detail['processing']['error_code'] == 'METADATA_FETCH_FAILED'
    assert 'upstream' not in detail['processing']['error_message']


def test_missing_english_caption_uses_stt_and_is_visible_through_api(client, tmp_path):
    async def no_english(_url):
        return []

    async def acquire_audio(video_id, _url):
        path = tmp_path / 'videos' / video_id / 'audio' / 'source.webm'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'audio')
        return AudioArtifact(path, 'webm', 5)

    async def transcribe(_path):
        return TranscriptionData('en', 1.0, 1.0, 1.0, (
            TranscriptionSegmentData(
                0, 0.0, 1.0, ' Spoken English.',
                (TranscriptionWordData(' Spoken', 0.0, 0.5, 0.9),
                 TranscriptionWordData(' English.', 0.5, 1.0, 0.8)),
                {'segment_id': 0}),
        ))

    pipeline = client.app.state.video_import_pipeline
    pipeline.discover_captions = no_english
    pipeline.acquire_audio = acquire_audio
    pipeline.transcribe_audio = transcribe
    created = client.post('/api/videos', json={'url': 'https://youtu.be/cA5_tI-oNqR'})
    video_id = created.json()['video']['id']
    detail = client.get(f'/api/videos/{video_id}').json()
    transcript = client.get(f'/api/videos/{video_id}/transcript').json()
    assert detail['status'] == 'ready'
    assert detail['subtitle_source'] == 'stt'
    assert detail['subtitle_language'] == 'en'
    assert transcript['segments'][0]['text'] == 'Spoken English.'
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord).where(
            RawTranscriptWord.video_id == video_id)) == 2
    assert not (tmp_path / 'videos' / video_id / 'audio').exists()


def test_automatic_caption_source_is_visible_through_api_and_raw_storage(client):
    async def discover_auto(_url):
        return [CaptionCandidate(SubtitleSource.YOUTUBE_AUTO, 'en', 'English',
                                 'https://youtube.test/auto-caption', 'vtt')]

    client.app.state.video_import_pipeline.discover_captions = discover_auto
    created = client.post('/api/videos', json={'url': 'https://youtu.be/cA5_tI-oNqR'})
    video_id = created.json()['video']['id']
    detail = client.get(f'/api/videos/{video_id}').json()
    transcript = client.get(f'/api/videos/{video_id}/transcript').json()
    assert detail['status'] == 'ready'
    assert detail['subtitle_source'] == 'youtube_auto'
    assert detail['subtitle_language'] == 'en'
    assert transcript['normalization_version'] == 2
    with client.app.state.session_factory() as session:
        cues = session.scalars(select(RawTranscriptCue).where(
            RawTranscriptCue.video_id == video_id)).all()
        assert cues
        assert all(cue.source_type == SubtitleSource.YOUTUBE_AUTO for cue in cues)
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord).where(
            RawTranscriptWord.video_id == video_id)) == 0


def test_startup_marks_interrupted_job_failed_and_cleans_managed_audio(tmp_path, monkeypatch):
    from uuid import uuid4

    database_path = tmp_path / 'recovery.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{database_path}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    settings = Settings(_env_file=None, data_dir=tmp_path)
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as session:
        video = Video(youtube_video_id='iN7_er-RuN1',
                      youtube_url='https://www.youtube.com/watch?v=iN7_er-RuN1')
        session.add(video)
        session.flush()
        job = ProcessingJob(
            video_id=video.id, stage=ProcessingStage.TRANSCRIBING,
            status=JobStatus.RUNNING, progress=40)
        session.add(job)
        session.commit()
        video_id = video.id
    engine.dispose()

    audio_dir = tmp_path / 'videos' / video_id / 'audio'
    audio_dir.mkdir(parents=True)
    (audio_dir / 'source.webm').write_bytes(b'audio')
    staging = audio_dir / f'.download-{uuid4()}'
    staging.mkdir()
    (staging / 'source.webm.part').write_bytes(b'partial')

    with TestClient(create_app(settings)) as recovery_client:
        detail = recovery_client.get(f'/api/videos/{video_id}').json()
        assert detail['status'] == 'failed'
        assert detail['processing']['error_code'] == 'PROCESS_INTERRUPTED'
    assert not audio_dir.exists()


def test_transcript_marks_save_edit_list_and_delete(client):
    video_id = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI'}).json()['video']['id']
    transcript = client.get(f'/api/videos/{video_id}/transcript').json()
    segment = transcript['segments'][0]
    url = f'/api/videos/{video_id}/marks'
    assert client.get(url).json() == {'items': []}

    created = client.post(url, json={
        'revision_id': transcript['revision_id'], 'segment_id': segment['id'],
        'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello',
    })
    assert created.status_code == 201
    mark = created.json()
    assert UUID(mark['id'])
    assert mark['video_id'] == video_id
    assert mark['revision_id'] == transcript['revision_id']
    assert mark['segment_id'] == segment['id']
    assert mark['selected_text'] == mark['segment_text'] == 'Hello'
    assert (mark['revision_number'], mark['revision_origin'], mark['is_current']) == (
        1, 'generated', True)
    assert mark['note'] is None
    assert client.get(url).json() == {'items': [mark]}

    edited = client.patch(f'{url}/{mark["id"]}', json={'note': 'My own note'}).json()
    assert edited['note'] == 'My own note'
    assert edited['selected_text'] == 'Hello'
    assert edited['segment_id'] == segment['id']
    assert client.patch(f'{url}/{mark["id"]}', json={'note': ''}).json()['note'] is None
    assert client.patch(f'{url}/{mark["id"]}', json={'note': '  '}).json()['note'] is None
    assert client.patch(f'{url}/{mark["id"]}', json={'selected_text': 'Other'}).status_code == 422
    assert client.delete(f'{url}/{mark["id"]}').status_code == 204
    assert client.get(url).json() == {'items': []}
    assert client.delete(f'{url}/{mark["id"]}').status_code == 404
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptMark)) == 0


def test_transcript_marks_reject_invalid_selection_and_cross_video_ids(client):
    first = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI'}).json()['video']['id']
    second = client.post('/api/videos', json={
        'url': 'https://youtu.be/bB3_dE-fGhI'}).json()['video']['id']
    transcript = client.get(f'/api/videos/{first}/transcript').json()
    base = {
        'revision_id': transcript['revision_id'],
        'segment_id': transcript['segments'][0]['id'],
        'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello',
    }
    url = f'/api/videos/{first}/marks'
    assert client.get('/api/videos/missing/marks').status_code == 404
    assert client.post('/api/videos/missing/marks', json=base).status_code == 404
    assert client.post(f'/api/videos/{second}/marks', json=base).status_code == 409
    wrong_segment = {**base, 'segment_id': client.get(
        f'/api/videos/{second}/transcript').json()['segments'][0]['id']}
    assert client.post(url, json=wrong_segment).status_code == 404
    for change in (
        {'selected_text': 'Hallo'},
        {'start_offset': 1, 'end_offset': 5, 'selected_text': 'Hello'},
        {'start_offset': 0, 'end_offset': 6},
        {'start_offset': 3, 'end_offset': 2},
    ):
        response = client.post(url, json={**base, **change})
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'MARK_SELECTION_INVALID'
    assert client.post(url, json={**base, 'start_offset': True}).json()[
        'error']['code'] == 'VALIDATION_ERROR'
    assert client.get(url).json() == {'items': []}

    mark_id = client.post(url, json=base).json()['id']
    assert client.patch(f'/api/videos/{second}/marks/{mark_id}',
                        json={'note': 'No'}).status_code == 404
    assert client.delete(f'/api/videos/{second}/marks/{mark_id}').status_code == 404
    assert len(client.get(url).json()['items']) == 1


def test_marks_keep_exact_unicode_offsets_and_old_revision_after_source_publication(client):
    video_id = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI'}).json()['video']['id']
    url = f'/api/videos/{video_id}/marks'
    original = client.get(f'/api/videos/{video_id}/transcript').json()
    old_mark = client.post(url, json={
        'revision_id': original['revision_id'],
        'segment_id': original['segments'][0]['id'],
        'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello',
        'note': 'Original wording',
    }).json()
    srt = 'Hi 😀 sold on sold on'
    updated = client.post(f'/api/videos/{video_id}/transcript/source-learning',
                          json=_source_payload(client, video_id, srt))
    assert updated.status_code == 200
    current = updated.json()['transcript']
    assert current['revision_id'] != original['revision_id']
    stale = client.post(url, json={
        'revision_id': original['revision_id'],
        'segment_id': original['segments'][0]['id'],
        'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello',
    })
    assert stale.status_code == 409
    assert stale.json()['error']['code'] == 'TRANSCRIPT_REVISION_CONFLICT'

    sentence = current['segments'][0]['text']
    first = sentence.index('sold on')
    second = sentence.index('sold on', first + 1)
    new_mark = client.post(url, json={
        'revision_id': current['revision_id'], 'segment_id': current['segments'][0]['id'],
        'start_offset': second, 'end_offset': second + len('sold on'),
        'selected_text': 'sold on',
    })
    assert new_mark.status_code == 201
    assert new_mark.json()['start_offset'] == second
    assert sentence[new_mark.json()['start_offset']:new_mark.json()['end_offset']] == 'sold on'
    assert client.post(url, json={
        'revision_id': current['revision_id'], 'segment_id': current['segments'][0]['id'],
        'start_offset': 3, 'end_offset': 4, 'selected_text': '😀',
    }).status_code == 201
    whitespace = client.post(url, json={
        'revision_id': current['revision_id'], 'segment_id': current['segments'][0]['id'],
        'start_offset': 2, 'end_offset': 3, 'selected_text': ' ',
    })
    assert whitespace.status_code == 422
    assert whitespace.json()['error']['code'] == 'MARK_SELECTION_INVALID'
    listed = client.get(url).json()['items']
    assert [item['is_current'] for item in listed] == [True, True, False]
    assert listed[-1]['id'] == old_mark['id']
    assert listed[-1]['revision_number'] == 1
    assert listed[-1]['segment_text'] == 'Hello'
    assert listed[-1]['note'] == 'Original wording'
    assert client.get(f'/api/videos/{video_id}/transcript/revisions/{original["revision_id"]}').json()[
        'normalization_version'] == 2
    assert client.patch(f'{url}/{old_mark["id"]}',
                        json={'note': 'Still useful'}).json()['is_current'] is False
    assert client.delete(f'{url}/{old_mark["id"]}').status_code == 204
    assert len(client.get(url).json()['items']) == 2


def test_mark_create_serializes_with_concurrent_source_publication(client):
    video_id = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI'}).json()['video']['id']
    original = client.get(f'/api/videos/{video_id}/transcript').json()
    srt = 'Updated sentence.'
    publish_payload = _source_payload(client, video_id, srt)
    mark_payload = {
        'revision_id': original['revision_id'],
        'segment_id': original['segments'][0]['id'],
        'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello',
    }
    barrier = Barrier(3)

    def create():
        barrier.wait()
        return client.post(f'/api/videos/{video_id}/marks', json=mark_payload)

    def publish():
        barrier.wait()
        return client.post(f'/api/videos/{video_id}/transcript/source-learning',
                           json=publish_payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        mark_future = executor.submit(create)
        publish_future = executor.submit(publish)
        barrier.wait()
        mark_response = mark_future.result()
        publish_response = publish_future.result()
    assert publish_response.status_code == 200
    assert mark_response.status_code in (201, 409)
    marks = client.get(f'/api/videos/{video_id}/marks').json()['items']
    if mark_response.status_code == 201:
        assert len(marks) == 1
        assert marks[0]['revision_id'] == original['revision_id']
        assert marks[0]['is_current'] is False
    else:
        assert mark_response.json()['error']['code'] == 'TRANSCRIPT_REVISION_CONFLICT'
        assert marks == []


def _notes_anchor(client, youtube_id='aB3_dE-fGhI'):
    video_id = client.post('/api/videos', json={
        'url': f'https://youtu.be/{youtube_id}'}).json()['video']['id']
    transcript = client.get(f'/api/videos/{video_id}/transcript').json()
    return video_id, {
        'revision_id': transcript['revision_id'], 'segment_id': transcript['segments'][0]['id'],
        'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello',
    }


def test_favorite_deduplicates_without_overwriting_note_and_can_recreate(client):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/marks'
    first = client.post(url, json={**anchor, 'note': 'Keep this note'})
    duplicate = client.post(url, json={**anchor, 'note': 'Do not overwrite'})
    assert first.status_code == 201 and duplicate.status_code == 200
    assert duplicate.json() == first.json()
    assert len(client.get(url).json()['items']) == 1
    assert client.delete(f'{url}/{first.json()["id"]}').status_code == 204
    replacement = client.post(url, json=anchor)
    assert replacement.status_code == 201
    assert replacement.json()['id'] != first.json()['id']


def test_concurrent_favorites_converge_and_questions_do_not_deduplicate(client):
    video_id, anchor = _notes_anchor(client)
    barrier = Barrier(4)

    def save(kind):
        barrier.wait()
        payload = anchor if kind == 'marks' else {**anchor, 'question': 'Why?'}
        return client.post(f'/api/videos/{video_id}/{kind}', json=payload)

    for kind in ('marks', 'questions'):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(save, [kind] * 4))
        if kind == 'marks':
            assert sorted(item.status_code for item in results) == [200, 200, 200, 201]
            assert len({item.json()['id'] for item in results}) == 1
        else:
            assert all(item.status_code == 201 for item in results)
            assert len({item.json()['id'] for item in results}) == 4


def test_question_crud_normalization_and_separate_favorite(client):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    assert client.get(url).json() == {'items': []}
    created = client.post(url, json={**anchor, 'question': ' Why Hello? ', 'answer': '\t\n　'})
    assert created.status_code == 201
    item = created.json()
    assert item['question'] == ' Why Hello? ' and item['answer'] is None
    assert item['segment_text'] == 'Hello' and item['is_current']
    assert 'note' not in item
    assert client.post(f'/api/videos/{video_id}/marks', json=anchor).status_code == 201
    path = f'{url}/{item["id"]}'
    answer = client.patch(path, json={'answer': ' Answer 😀\nwith formatting '}).json()
    assert answer['question'] == item['question']
    assert answer['answer'] == ' Answer 😀\nwith formatting '
    edited = client.patch(path, json={'question': 'A different question'}).json()
    assert edited['answer'] == answer['answer']
    assert client.get(url).json()['items'] == [edited]
    assert client.patch(path, json={'answer': ''}).json()['answer'] is None
    assert client.patch(path, json={'answer': None}).json()['answer'] is None
    assert client.delete(path).status_code == 204
    assert client.delete(path).json()['error']['code'] == 'TRANSCRIPT_QUESTION_NOT_FOUND'
    assert client.get(url).json() == {'items': []}


@pytest.mark.parametrize('changes', [
    {'question': ''}, {'question': ' \n\t　'}, {'question': None}, {'question': 123},
    {'question': 'q' * 10001}, {'answer': 'a' * 100001}, {'answer': 123},
    {'unknown': 'secret'}, {'start_offset': True}, {'revision_id': 2},
])
def test_question_create_validation_does_not_echo_text(client, changes):
    video_id, anchor = _notes_anchor(client)
    result = client.post(f'/api/videos/{video_id}/questions',
                         json={**anchor, 'question': 'Private question', **changes})
    assert result.status_code == 422
    assert result.json()['error']['code'] == 'VALIDATION_ERROR'
    assert 'Private question' not in result.text and 'secret' not in result.text


@pytest.mark.parametrize('changes', [
    {}, {'question': None}, {'question': '　\t'}, {'question': False},
    {'answer': 2}, {'question': 'q' * 10001}, {'answer': 'a' * 100001},
    {'selected_text': 'Changed'}, {'segment_id': 'missing'},
])
def test_question_patch_rejects_empty_invalid_and_anchor_changes(client, changes):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    item = client.post(url, json={**anchor, 'question': 'Private question'}).json()
    result = client.patch(f'{url}/{item["id"]}', json=changes)
    assert result.status_code == 422
    assert result.json()['error']['code'] == 'VALIDATION_ERROR'
    assert client.get(url).json()['items'] == [item]


def test_question_anchor_errors_cross_video_and_unavailable(client):
    video_id, anchor = _notes_anchor(client)
    other_id, other_anchor = _notes_anchor(client, 'abcdefghijk')
    url = f'/api/videos/{video_id}/questions'
    payload = {**anchor, 'question': 'Why?'}
    item = client.post(url, json=payload).json()
    assert client.post('/api/videos/missing/questions', json=payload).status_code == 404
    assert client.get('/api/videos/missing/questions').status_code == 404
    assert client.post(f'/api/videos/{other_id}/questions', json=payload).status_code == 409
    for changes, code in [
        ({'segment_id': other_anchor['segment_id']}, 'TRANSCRIPT_SEGMENT_NOT_FOUND'),
        ({'segment_id': 'missing'}, 'TRANSCRIPT_SEGMENT_NOT_FOUND'),
        ({'end_offset': 6}, 'MARK_SELECTION_INVALID'),
        ({'start_offset': 5}, 'MARK_SELECTION_INVALID'),
        ({'selected_text': 'Other'}, 'MARK_SELECTION_INVALID'),
    ]:
        result = client.post(url, json={**payload, **changes})
        assert result.json()['error']['code'] == code
    for method in ('patch', 'delete'):
        path = f'/api/videos/{other_id}/questions/{item["id"]}'
        result = (client.patch(path, json={'answer': 'No'}) if method == 'patch'
                  else client.delete(path))
        assert result.status_code == 404
        assert result.json()['error']['code'] == 'TRANSCRIPT_QUESTION_NOT_FOUND'
    with client.app.state.session_factory() as session:
        session.get(Video, other_id).status = VideoStatus.PROCESSING
        session.commit()
    assert client.post(f'/api/videos/{other_id}/questions', json={
        **other_anchor, 'question': 'Why?'}).json()['error']['code'] == 'TRANSCRIPT_UNAVAILABLE'


def test_questions_keep_unicode_positions_old_versions_and_order(client):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    old = client.post(url, json={**anchor, 'question': 'Old question'}).json()
    srt = 'Hi 😀 sold on sold on'
    current = client.post(f'/api/videos/{video_id}/transcript/source-learning',
                          json=_source_payload(client, video_id, srt)).json()['transcript']
    assert client.post(url, json={**anchor, 'question': 'Stale'}).status_code == 409
    text = current['segments'][0]['text']
    ids = []
    for selected, start in [('sold on', text.rindex('sold on')), ('😀', 3),
                            ('sold on', text.index('sold on'))]:
        payload = {**anchor, 'revision_id': current['revision_id'],
                   'segment_id': current['segments'][0]['id'], 'start_offset': start,
                   'end_offset': start + len(selected), 'selected_text': selected,
                   'question': 'Why this expression?'}
        result = client.post(url, json=payload)
        assert result.status_code == 201
        assert text[result.json()['start_offset']:result.json()['end_offset']] == selected
        ids.append(result.json()['id'])
    assert [item['id'] for item in client.get(url).json()['items']] == [
        ids[1], ids[2], ids[0], old['id']]
    old_path = f'{url}/{old["id"]}'
    updated = client.patch(old_path, json={'question': 'Edited old', 'answer': 'Manual answer'})
    assert updated.status_code == 200 and updated.json()['is_current'] is False
    assert updated.json()['segment_text'] == 'Hello'
    assert client.delete(old_path).status_code == 204


def test_question_creation_serializes_with_publication(client):
    video_id, anchor = _notes_anchor(client)
    payload = _source_payload(client, video_id,
                                'New words')
    barrier = Barrier(2)

    def create():
        barrier.wait()
        return client.post(f'/api/videos/{video_id}/questions',
                           json={**anchor, 'question': 'Why?'})

    def publish():
        barrier.wait()
        return client.post(f'/api/videos/{video_id}/transcript/source-learning', json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create)
        second = executor.submit(publish)
        question, published = first.result(), second.result()
    assert published.status_code == 200
    assert question.status_code in (201, 409)
    items = client.get(f'/api/videos/{video_id}/questions').json()['items']
    assert len(items) == (1 if question.status_code == 201 else 0)
    if items:
        assert not items[0]['is_current'] and items[0]['revision_id'] == anchor['revision_id']


def test_notes_migration_preserves_all_rows_and_historical_duplicate_bindings(client):
    from sqlalchemy import inspect, text
    from app.db.models import TranscriptMarkKey

    video_id, _ = _notes_anchor(client)
    # Include published layout/boundaries and old revisions in the preservation check.
    srt = 'Hello / again'
    published = client.post(f'/api/videos/{video_id}/transcript/source-learning',
                            json=_source_payload(client, video_id, srt))
    assert published.status_code == 200
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptChunkSegment)) > 0
        for segment in session.scalars(select(LearningTranscriptSegment)):
            segment.translation_zh = None
        session.commit()
    transcript = client.get(f'/api/videos/{video_id}/transcript').json()
    anchor = {'revision_id': transcript['revision_id'],
              'segment_id': transcript['segments'][0]['id'],
              'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello'}
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.downgrade(config, '008_source_aligned_learning')
    factory = client.app.state.session_factory
    with factory() as session:
        from datetime import UTC, datetime, timedelta
        created = datetime(2026, 10, 1, tzinfo=UTC)
        for index, (name, note) in enumerate([
            ('empty', '\t　\n'), ('with-note', 'Keep me'), ('later-note', 'Also keep me')]):
            session.add(TranscriptMark(id=name, video_id=video_id, **anchor,
                                       note=note, created_at=created + timedelta(seconds=index)))
        session.commit()
    engine = factory.kw['bind']
    tables = [table for table in inspect(engine).get_table_names() if table != 'alembic_version']
    columns = {table: [column['name'] for column in inspect(engine).get_columns(table)]
               for table in tables}

    def snapshot():
        with engine.connect() as connection:
            return {table: connection.execute(text(
                        f'SELECT {", ".join(columns[table])} FROM "{table}" ORDER BY id')).all()
                    for table in tables}

    before = snapshot()
    command.upgrade(config, '013_import_retries')
    assert snapshot() == before
    with engine.connect() as connection:
        assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
        assert connection.scalar(text('PRAGMA integrity_check')) == 'ok'
    url = f'/api/videos/{video_id}/marks'
    duplicate = client.post(url, json={**anchor, 'note': 'No overwrite'})
    assert duplicate.status_code == 200 and duplicate.json()['id'] == 'with-note'
    assert duplicate.json()['note'] == 'Keep me'
    assert len(client.get(url).json()['items']) == 3
    assert client.patch(f'{url}/empty', json={'note': 'Editable duplicate'}).status_code == 200
    # Binding stays stable despite note edits; deleting an unbound duplicate leaves it intact.
    assert client.delete(f'{url}/empty').status_code == 204
    assert client.post(url, json=anchor).json()['id'] == 'with-note'
    assert client.delete(f'{url}/with-note').status_code == 204
    rebound = client.post(url, json=anchor)
    assert rebound.status_code == 200 and rebound.json()['id'] == 'later-note'
    assert rebound.json()['note'] == 'Also keep me'
    with factory() as session:
        assert session.scalar(select(TranscriptMarkKey)).mark_id == 'later-note'
    command.downgrade(config, '008_source_aligned_learning')
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptMark)) == 1
    command.upgrade(config, '013_import_retries')
    assert client.post(url, json=anchor).json()['id'] == 'later-note'

    command.upgrade(config, 'head')
    command.check(config)


def test_notes_downgrade_refuses_saved_questions_and_allows_empty_rollback(client):
    from sqlalchemy import inspect

    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    item = client.post(url, json={**anchor, 'question': 'Keep question', 'answer': 'Keep answer'}).json()
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with pytest.raises(RuntimeError, match='questions or answers exist'):
        command.downgrade(config, '008_source_aligned_learning')
    # Earlier downgrade steps may have committed before the older guard refused.
    command.upgrade(config, 'head')
    assert client.get(url).json()['items'] == [item]
    assert client.delete(f'{url}/{item["id"]}').status_code == 204
    command.downgrade(config, '008_source_aligned_learning')
    tables = inspect(client.app.state.session_factory.kw['bind']).get_table_names()
    assert 'transcript_questions' not in tables and 'transcript_mark_keys' not in tables
    command.upgrade(config, 'head')
    command.check(config)
    assert client.get(url).json() == {'items': []}


def test_favorite_binding_and_row_creation_roll_back_together(client):
    from app.db.models import TranscriptMarkKey

    video_id, anchor = _notes_anchor(client)
    engine = client.app.state.session_factory.kw['bind']

    def reject_binding(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO transcript_mark_keys'):
            raise RuntimeError('Injected binding failure')

    event.listen(engine, 'before_cursor_execute', reject_binding)
    try:
        with pytest.raises(RuntimeError, match='binding failure'):
            client.post(f'/api/videos/{video_id}/marks', json=anchor)
    finally:
        event.remove(engine, 'before_cursor_execute', reject_binding)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptMark)) == 0
        assert session.scalar(select(func.count()).select_from(TranscriptMarkKey)) == 0
    assert client.post(f'/api/videos/{video_id}/marks', json=anchor).status_code == 201


def test_favorite_delete_serializes_with_concurrent_create(client):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/marks'
    original = client.post(url, json=anchor).json()
    barrier = Barrier(2)

    def create():
        barrier.wait()
        return client.post(url, json=anchor)

    def delete():
        barrier.wait()
        return client.delete(f'{url}/{original["id"]}')

    with ThreadPoolExecutor(max_workers=2) as executor:
        create_future = executor.submit(create)
        delete_future = executor.submit(delete)
        created, deleted = create_future.result(), delete_future.result()
    assert deleted.status_code == 204
    assert created.status_code in (200, 201)
    items = client.get(url).json()['items']
    assert len(items) == (1 if created.status_code == 201 else 0)
    if items:
        assert items[0]['id'] != original['id']
    final = client.post(url, json=anchor)
    assert final.status_code == (200 if items else 201)
    assert len(client.get(url).json()['items']) == 1


def test_first_answer_collects_once_and_cancel_clear_and_delete_are_independent(client):
    from app.db.models import TranscriptQuestion

    video_id, anchor = _notes_anchor(client)
    questions = f'/api/videos/{video_id}/questions'
    marks = f'/api/videos/{video_id}/marks'
    item = client.post(questions, json={**anchor, 'question': 'Why?', 'answer': '　\t'}).json()
    path = f'{questions}/{item["id"]}'
    assert client.get(marks).json()['items'] == []
    assert client.patch(path, json={'question': 'Still why?'}).status_code == 200
    assert client.get(marks).json()['items'] == []
    assert client.patch(path, json={'answer': ' Meaning 😀 '}).json()['answer'] == ' Meaning 😀 '
    saved = client.get(marks).json()['items']
    assert len(saved) == 1
    assert saved[0]['note'] is None
    assert all(saved[0][field] == value for field, value in anchor.items())
    assert client.patch(path, json={'answer': None}).json()['answer'] is None
    assert client.get(marks).json()['items'] == saved
    assert client.delete(f'{marks}/{saved[0]["id"]}').status_code == 204
    # Clearing and re-filling the same answer is not a second first-save event.
    assert client.patch(path, json={'answer': 'Another explanation'}).status_code == 200
    assert client.patch(path, json={'answer': 'Edited explanation'}).status_code == 200
    assert client.get(marks).json()['items'] == []
    with client.app.state.session_factory() as session:
        assert session.get(TranscriptQuestion, item['id']).has_saved_answer is True
    # A different question can collect the same expression again.
    another = client.post(questions, json={**anchor, 'question': 'How?', 'answer': 'Like this'}).json()
    again = client.get(marks).json()['items']
    assert len(again) == 1 and again[0]['id'] != saved[0]['id']
    assert client.delete(f'{questions}/{another["id"]}').status_code == 204
    assert client.get(marks).json()['items'] == again
    assert client.get(questions).json()['items'][0]['id'] == item['id']
    assert client.delete(path).status_code == 204
    assert client.get(marks).json()['items'] == again


def test_answer_reuses_favorite_without_modifying_note_or_response_contract(client):
    video_id, anchor = _notes_anchor(client)
    marks = f'/api/videos/{video_id}/marks'
    questions = f'/api/videos/{video_id}/questions'
    favorite = client.post(marks, json={**anchor, 'note': 'Keep my personal note'}).json()
    for number in range(2):
        response = client.post(questions, json={**anchor, 'question': f'Question {number}',
                                               'answer': ' Answer\nwith formatting '})
        assert response.status_code == 201
        assert response.json()['answer'] == ' Answer\nwith formatting '
        assert 'has_saved_answer' not in response.json()  # Internal fact, not a client-controlled state.
    assert client.get(marks).json()['items'] == [favorite]
    assert len(client.get(questions).json()['items']) == 2
    invalid = client.post(questions, json={**anchor, 'question': 'Why?', 'has_saved_answer': True})
    assert invalid.status_code == 422


def test_old_revision_first_answer_collects_original_anchor_without_changing_current(client):
    video_id, anchor = _notes_anchor(client)
    questions = f'/api/videos/{video_id}/questions'
    old = client.post(questions, json={**anchor, 'question': 'Old words?'}).json()
    imported = client.post(f'/api/videos/{video_id}/transcript/source-learning', json=_source_payload(
        client, video_id, 'Hello again')).json()['transcript']
    assert client.patch(f'{questions}/{old["id"]}', json={'answer': 'Old meaning'}).status_code == 200
    mark = client.get(f'/api/videos/{video_id}/marks').json()['items'][0]
    assert not mark['is_current'] and mark['segment_text'] == 'Hello'
    assert all(mark[field] == value for field, value in anchor.items())
    assert client.get(f'/api/videos/{video_id}/transcript').json() == imported


@pytest.mark.parametrize('creating', [False, True])
def test_answer_and_first_save_fact_roll_back_when_favorite_binding_fails(client, creating):
    from app.db.models import TranscriptMarkKey, TranscriptQuestion

    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    original = None if creating else client.post(url, json={**anchor, 'question': 'Why?'}).json()
    engine = client.app.state.session_factory.kw['bind']

    def fail_binding(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO transcript_mark_keys'):
            raise RuntimeError('Injected answer collection failure')

    def save():
        return (client.post(url, json={**anchor, 'question': 'Why?', 'answer': 'Meaning'})
                if creating else client.patch(f'{url}/{original["id"]}', json={'answer': 'Meaning'}))

    event.listen(engine, 'before_cursor_execute', fail_binding)
    try:
        with pytest.raises(RuntimeError, match='answer collection failure'):
            save()
    finally:
        event.remove(engine, 'before_cursor_execute', fail_binding)
    assert client.get(url).json()['items'] == ([] if creating else [original])
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptMark)) == 0
        assert session.scalar(select(func.count()).select_from(TranscriptMarkKey)) == 0
        if original:
            assert session.get(TranscriptQuestion, original['id']).has_saved_answer is False
    assert save().status_code == (201 if creating else 200)
    assert len(client.get(f'/api/videos/{video_id}/marks').json()['items']) == 1


@pytest.mark.parametrize('same_question', [True, False])
def test_concurrent_first_answers_converge_on_one_favorite(client, same_question):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    ids = [client.post(url, json={**anchor, 'question': f'Why {index}?'}).json()['id']
           for index in range(1 if same_question else 4)]
    barrier = Barrier(4)

    def answer(index):
        barrier.wait()
        return client.patch(f'{url}/{ids[index % len(ids)]}', json={'answer': f'Answer {index}'})

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(answer, range(4)))
    assert all(response.status_code == 200 for response in results)
    marks = f'/api/videos/{video_id}/marks'
    favorite = client.get(marks).json()['items']
    assert len(favorite) == 1
    assert client.delete(f'{marks}/{favorite[0]["id"]}').status_code == 204
    for question_id in ids:
        assert client.patch(f'{url}/{question_id}', json={'answer': 'Edited'}).status_code == 200
    assert client.get(marks).json()['items'] == []


def test_answer_collection_keeps_equal_words_at_distinct_unicode_positions_separate(client):
    video_id, _ = _notes_anchor(client)
    current = client.post(f'/api/videos/{video_id}/transcript/source-learning', json=_source_payload(
        client, video_id, '😀 sold on sold on')).json()['transcript']
    text = current['segments'][0]['text']
    for start in (text.index('sold on'), text.rindex('sold on')):
        response = client.post(f'/api/videos/{video_id}/questions', json={
            'revision_id': current['revision_id'], 'segment_id': current['segments'][0]['id'],
            'start_offset': start, 'end_offset': start + 7, 'selected_text': 'sold on',
            'question': 'Why this usage?', 'answer': 'Explanation'})
        assert response.status_code == 201
    marks = client.get(f'/api/videos/{video_id}/marks').json()['items']
    assert len(marks) == 2
    assert [item['start_offset'] for item in marks] == [text.index('sold on'), text.rindex('sold on')]


def test_saved_answer_migration_preserves_every_old_column_and_does_not_restore_favorites(client):
    from sqlalchemy import inspect, text

    video_id, _ = _notes_anchor(client)
    # Include revision/layout relations as well as duplicate marks in the snapshot.
    published = client.post(f'/api/videos/{video_id}/transcript/source-learning', json=
                            _source_payload(client, video_id,
                                'Hello / again'))
    assert published.status_code == 200
    published = client.get(f'/api/videos/{video_id}/transcript').json()
    anchor = {'revision_id': published['revision_id'], 'segment_id': published['segments'][0]['id'],
              'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello'}
    questions = f'/api/videos/{video_id}/questions'
    marks = f'/api/videos/{video_id}/marks'
    original = client.post(marks, json={**anchor, 'note': 'Keep original note'}).json()
    with client.app.state.session_factory() as session:
        for segment in session.scalars(select(LearningTranscriptSegment)):
            segment.translation_zh = None
        session.add(TranscriptMark(id='historical-duplicate', video_id=video_id, **anchor,
                                   note='Keep duplicate note'))
        session.commit()
    ids = [client.post(questions, json={**anchor, 'question': f'Question {index}'}).json()['id']
           for index in range(3)]
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.downgrade(config, '009_notes_experience')
    engine = client.app.state.session_factory.kw['bind']
    # Simulate the pre-010 database, including legacy whitespace not normalized by API.
    with engine.begin() as connection:
        for question_id, answer in zip(ids, [' Answer 😀\n ', '\t　\n', None]):
            connection.execute(text('UPDATE transcript_questions SET answer = :answer WHERE id = :id'),
                               {'id': question_id, 'answer': answer})
    columns = {table: [column['name'] for column in inspect(engine).get_columns(table)]
               for table in inspect(engine).get_table_names() if table != 'alembic_version'}

    def snapshot():
        with engine.connect() as connection:
            result = {}
            for table, names in columns.items():
                fields = ', '.join(f'"{name}"' for name in names)
                result[table] = sorted((tuple(row) for row in connection.execute(
                    text(f'SELECT {fields} FROM "{table}"'))), key=repr)
            return result

    before = snapshot()
    command.upgrade(config, '013_import_retries')
    assert snapshot() == before
    with engine.connect() as connection:
        flags = dict(connection.execute(text(
            'SELECT id, has_saved_answer FROM transcript_questions')).all())
        assert flags == {ids[0]: 1, ids[1]: 0, ids[2]: 0}
        assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
        assert connection.scalar(text('PRAGMA integrity_check')) == 'ok'
    assert client.post(marks, json=anchor).json()['id'] == original['id']
    # Simulate cancellation after migration. Editing an old answer cannot undo it.
    for item in client.get(marks).json()['items']:
        assert client.delete(f'{marks}/{item["id"]}').status_code == 204
    assert client.patch(f'{questions}/{ids[1]}', json={'question': 'Edited legacy blank question'}).status_code == 200
    assert client.get(marks).json()['items'] == []
    assert client.patch(f'{questions}/{ids[0]}', json={'answer': 'Edited old answer'}).status_code == 200
    assert client.get(marks).json()['items'] == []
    # Legacy blank answers have no recoverable history; their first save collects.
    assert client.patch(f'{questions}/{ids[1]}', json={'answer': 'First new answer'}).status_code == 200
    assert len(client.get(marks).json()['items']) == 1

    command.upgrade(config, 'head')
    command.check(config)


def test_saved_answer_history_blocks_lossy_downgrade_even_after_answer_is_cleared(client):
    from sqlalchemy import text

    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/questions'
    item = client.post(url, json={**anchor, 'question': 'Why?', 'answer': 'Meaning'}).json()
    assert client.patch(f'{url}/{item["id"]}', json={'answer': None}).status_code == 200
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with pytest.raises(RuntimeError, match='saved-answer history'):
        command.downgrade(config, '009_notes_experience')
    engine = client.app.state.session_factory.kw['bind']
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '010_saved_answer_history'
        assert connection.scalar(text('SELECT has_saved_answer FROM transcript_questions')) == 1
    command.upgrade(config, 'head')
    assert client.get(url).json()['items'][0]['answer'] is None
    assert client.delete(f'{url}/{item["id"]}').status_code == 204
    marks = client.get(f'/api/videos/{video_id}/marks').json()['items']
    command.downgrade(config, '009_notes_experience')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '009_notes_experience'
    command.upgrade(config, 'head')
    command.check(config)
    assert client.get(url).json()['items'] == []
    assert client.get(f'/api/videos/{video_id}/marks').json()['items'] == marks


def test_import_preference_is_persisted_and_duplicates_keep_original(client):
    # Stop external work so this test examines import/transaction semantics only.
    async def no_work(*_args):
        pass
    client.portal.call(client.app.state.video_import_scheduler.stop)
    client.app.state.video_import_pipeline.run = no_work
    first = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI', 'subtitle_preference': 'auto_only'})
    assert first.status_code == 202
    item = first.json()['video']
    assert item['subtitle_preference'] == 'auto_only'
    duplicate = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI', 'subtitle_preference': 'manual_first'})
    assert duplicate.status_code == 200 and duplicate.json()['already_exists']
    assert duplicate.json()['video'] == item
    assert client.get(f'/api/videos/{item["id"]}').json()['subtitle_preference'] == 'auto_only'
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Video)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 1


@pytest.mark.parametrize('preference', ['automatic', '', None, 1, []])
def test_invalid_import_preference_never_creates_video(client, preference):
    response = client.post('/api/videos', json={
        'url': 'https://youtu.be/aB3_dE-fGhI', 'subtitle_preference': preference})
    assert response.status_code == 422
    assert client.get('/api/videos').json() == {'items': []}
