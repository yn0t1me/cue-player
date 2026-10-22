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
    assert 'note' not in mark
    assert client.get(url).json() == {'items': [mark]}

    assert client.patch(f'{url}/{mark["id"]}', json={'note': 'Removed'}).status_code == 405
    assert client.post(url, json={'revision_id': transcript['revision_id'], 'segment_id': segment['id'],
                                 'start_offset': 0, 'end_offset': 5, 'selected_text': 'Hello', 'note': 'Removed'}).status_code == 422
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
                        json={'note': 'No'}).status_code == 405
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
    assert client.get(f'/api/videos/{video_id}/transcript/revisions/{original["revision_id"]}').json()[
        'normalization_version'] == 2
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


def test_favorite_deduplicates_and_can_recreate(client):
    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/marks'
    first = client.post(url, json=anchor)
    duplicate = client.post(url, json=anchor)
    assert first.status_code == 201 and duplicate.status_code == 200
    assert first.json() == duplicate.json()
    assert client.delete(f'{url}/{first.json()["id"]}').status_code == 204
    assert client.post(url, json=anchor).status_code == 201


def test_concurrent_favorites_converge(client):
    video_id, anchor = _notes_anchor(client)
    barrier = Barrier(4)
    def save(_):
        barrier.wait()
        return client.post(f'/api/videos/{video_id}/marks', json=anchor)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(save, range(4)))
    assert sorted(item.status_code for item in results) == [200, 200, 200, 201]
    assert len({item.json()['id'] for item in results}) == 1


def test_questions_endpoints_are_retired(client):
    video_id, anchor = _notes_anchor(client)
    path = f'/api/videos/{video_id}/questions'
    assert client.get(path).status_code == 404
    assert client.post(path, json={**anchor, 'question': 'Why?'}).status_code == 404
    assert client.patch(path + '/old', json={'answer': 'Answer'}).status_code == 404
    assert client.delete(path + '/old').status_code == 404


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


def test_favorite_deletion_rebinds_historical_duplicate_by_creation_time(client):
    from datetime import datetime, timedelta, timezone
    from app.db.models import TranscriptMarkKey

    video_id, anchor = _notes_anchor(client)
    url = f'/api/videos/{video_id}/marks'
    original = client.post(url, json=anchor).json()
    created = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with client.app.state.session_factory() as session:
        for index, name in enumerate(('earlier-duplicate', 'later-duplicate')):
            session.add(TranscriptMark(id=name, video_id=video_id, **anchor,
                                       created_at=created + timedelta(seconds=index)))
        session.commit()
    assert client.delete(f'{url}/{original["id"]}').status_code == 204
    assert client.post(url, json=anchor).json()['id'] == 'earlier-duplicate'
    with client.app.state.session_factory() as session:
        assert session.scalar(select(TranscriptMarkKey)).mark_id == 'earlier-duplicate'
    assert client.delete(f'{url}/earlier-duplicate').status_code == 204
    assert client.post(url, json=anchor).json()['id'] == 'later-duplicate'
    assert client.delete(f'{url}/later-duplicate').status_code == 204
    assert client.get(url).json() == {'items': []}
    assert client.post(url, json=anchor).status_code == 201
