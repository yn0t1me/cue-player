import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, select
from app.core.config import Settings
from app.core.enums import JobStatus, ProcessingStage, SubtitleSource, VideoStatus
from app.db.models import (
    LearningTranscriptSegment,
    ProcessingJob,
    RawTranscriptCue,
    RawTranscriptWord,
    TranscriptNormalizationRun,
    TranscriptRevision,
    Video,
)
from app.db.session import create_db_engine, create_session_factory
from app.services.processing.audio_store import AudioArtifact
from app.services.processing.job_manager import JobManager
from app.services.processing.video_import import VideoImportPipeline
from app.services.transcript import (
    EmptyTranscriptionError,
    STTModelLoadError,
    STTTranscriptionError,
    TranscriptionData,
    TranscriptionSegmentData,
    TranscriptionValidationError,
    TranscriptionWordData,
)
from app.services.youtube.audio import AudioDownloadError
from app.services.youtube.captions import CaptionCandidate, CaptionDownloadError
from app.services.youtube.metadata import MetadataFetchError, YouTubeMetadata


@pytest.fixture
def processing(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "pipeline.db"}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    engine = create_db_engine(Settings(_env_file=None, data_dir=tmp_path))
    factory = create_session_factory(engine)
    with factory() as session:
        video = Video(youtube_video_id='aB3_dE-fGhI',
                      youtube_url='https://www.youtube.com/watch?v=aB3_dE-fGhI')
        session.add(video)
        session.flush()
        job = ProcessingJob(video_id=video.id, stage=ProcessingStage.FETCHING_METADATA)
        session.add(job)
        session.commit()
        identifiers = video.id, job.id
    yield factory, identifiers, tmp_path
    engine.dispose()


def manual_caption():
    return CaptionCandidate(SubtitleSource.YOUTUBE_MANUAL, 'en', 'English',
                            'https://youtube.test/caption', 'vtt')


def automatic_caption():
    return CaptionCandidate(SubtitleSource.YOUTUBE_AUTO, 'en', 'English',
                            'https://youtube.test/auto-caption', 'vtt')


def stt_result():
    return TranscriptionData(
        language='en',
        language_probability=1.0,
        duration_seconds=2.0,
        duration_after_vad_seconds=2.0,
        segments=(TranscriptionSegmentData(
            sequence_index=0,
            start_seconds=0.0,
            end_seconds=2.0,
            text=' Spoken English.',
            words=(TranscriptionWordData(' Spoken', 0.1, 0.8, 0.9),
                   TranscriptionWordData(' English.', 0.8, 1.8, 0.8)),
            source_payload={'segment_id': 0},
        ),),
    )


def save_fake_audio(data_dir: Path, video_id: str) -> AudioArtifact:
    path = data_dir / 'videos' / video_id / 'audio' / 'source.webm'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'audio')
    return AudioArtifact(path=path, extension='webm', size_bytes=5)


def test_caption_store_rejects_a_path_instead_of_an_internal_id(processing):
    factory, (_video_id, _job_id), data_dir = processing
    pipeline = VideoImportPipeline(factory, data_dir)
    with pytest.raises(ValueError):
        pipeline.store.path_for('../outside')


def test_pipeline_runs_through_learning_transcript_and_marks_ready(processing):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(url):
        with factory() as session:
            running = session.get(ProcessingJob, job_id)
            assert running.status == JobStatus.RUNNING
            assert running.started_at is not None
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', 'Teacher', 125.5, 'https://img.test/t.jpg')

    async def discover(url):
        assert url.endswith('aB3_dE-fGhI')
        with factory() as session:
            running = session.get(ProcessingJob, job_id)
            assert running.status == JobStatus.RUNNING
            assert running.stage == ProcessingStage.FETCHING_CAPTIONS
            assert session.get(Video, video_id).title == 'Lesson'
        return [manual_caption()]

    async def download(selected):
        assert selected == manual_caption()
        return b'WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n'

    asyncio.run(VideoImportPipeline(factory, data_dir, fetch, discover, download).run(video_id, job_id))
    with factory() as session:
        video = session.get(Video, video_id)
        job = session.get(ProcessingJob, job_id)
        assert (video.title, video.channel_title, video.duration_seconds, video.thumbnail_url) == (
            'Lesson', 'Teacher', 125.5, 'https://img.test/t.jpg')
        assert video.status == VideoStatus.READY
        assert video.subtitle_source == SubtitleSource.YOUTUBE_MANUAL
        assert video.subtitle_language == 'en'
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.COMPLETED, JobStatus.COMPLETED, 100)
        assert job.started_at is not None and job.finished_at is not None
        cue = session.scalar(select(RawTranscriptCue))
        assert (cue.sequence_index, cue.start_seconds, cue.end_seconds, cue.text) == (
            0, 0.0, 1.0, 'Hello')
        assert cue.source_type == SubtitleSource.YOUTUBE_MANUAL
        assert cue.source_payload['lines'] == ['Hello']
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord)) == 0
        segment = session.scalar(select(LearningTranscriptSegment))
        assert (segment.sequence_index, segment.start_seconds, segment.end_seconds,
                segment.text, segment.source_ref_type) == (0, 0.0, 1.0, 'Hello', 'cue')
        assert segment.source_refs == {'cue_ids': [cue.id]}
        run = session.scalar(select(TranscriptNormalizationRun))
        assert (run.method, run.normalization_version) == (
            'deterministic', 2)
        assert segment.normalization_run_id == run.id
    assert (data_dir / 'videos' / video_id / 'raw' / 'caption.vtt').read_bytes().startswith(b'WEBVTT')
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_pipeline_persists_automatic_source_through_raw_and_learning(processing):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Automatic lesson', None, 30, None)

    async def discover(_url):
        return [automatic_caption()]

    async def download(selected):
        assert selected == automatic_caption()
        return (
            b'WEBVTT\n\n00:00.000 --> 00:00.010\nWe are checking\n\n'
            b'00:00.010 --> 00:02.000\nWe are checking <00:01.000>into the hotel\n\n'
            b'00:02.000 --> 00:02.010\ninto the hotel\n\n'
            b'00:02.010 --> 00:04.000\ninto the hotel <00:03.000>together now.\n'
        )

    asyncio.run(VideoImportPipeline(
        factory,
        data_dir,
        fetch,
        discover,
        download,
        settings=Settings(_env_file=None, data_dir=data_dir),

    ).run(video_id, job_id))
    with factory() as session:
        video = session.get(Video, video_id)
        job = session.get(ProcessingJob, job_id)
        cues = session.scalars(select(RawTranscriptCue).order_by(
            RawTranscriptCue.sequence_index)).all()
        segments = session.scalars(select(LearningTranscriptSegment)).all()
        assert video.status == VideoStatus.READY
        assert (video.subtitle_source, video.subtitle_language) == (
            SubtitleSource.YOUTUBE_AUTO, 'en')
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.COMPLETED, JobStatus.COMPLETED, 100)
        assert len(cues) == 4
        assert all(cue.source_type == SubtitleSource.YOUTUBE_AUTO for cue in cues)
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord)) == 0
        assert len(segments) == 1
        assert (segments[0].text, segments[0].normalization_version) == (
            'We are checking into the hotel together now.', 2)
        assert segments[0].source_refs == {
            'cue_ids': [cue.id for cue in cues],
        }
        run = session.scalar(select(TranscriptNormalizationRun))
        assert (run.method, run.normalization_version) == ('deterministic', 2)
        assert segments[0].normalization_run_id == run.id
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_pipeline_generates_local_initial_subtitles_and_preserves_raw(processing):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Correction lesson', None, 3, None)

    async def discover(_url):
        return [manual_caption()]

    async def download(_selected):
        return b'WEBVTT\n\n00:01.000 --> 00:03.000\nwe sale cars\n'

    pipeline = VideoImportPipeline(
        factory,
        data_dir,
        fetch,
        discover,
        download,
        settings=Settings(_env_file=None, data_dir=data_dir),

    )
    asyncio.run(pipeline.run(video_id, job_id))
    asyncio.run(pipeline.run(video_id, job_id))

    with factory() as session:
        video = session.get(Video, video_id)
        job = session.get(ProcessingJob, job_id)
        cue = session.scalar(select(RawTranscriptCue))
        learning = session.scalar(select(LearningTranscriptSegment))
        run = session.scalar(select(TranscriptNormalizationRun))
        assert video.status == VideoStatus.READY
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.COMPLETED, JobStatus.COMPLETED, 100)
        assert (learning.text, learning.normalization_version) == ('we sale cars', 2)
        assert learning.normalization_run_id == run.id
        assert (run.method, run.normalization_version, run.input_unit_count) == ('deterministic', 2, 3)
        assert cue.text == 'we sale cars'


def test_pipeline_local_generation_records_input_evidence(processing):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Fallback lesson', None, 2, None)

    async def discover(_url):
        return [manual_caption()]

    async def download(_selected):
        return b'WEBVTT\n\n00:00.000 --> 00:02.000\none two\n'

    asyncio.run(VideoImportPipeline(
        factory,
        data_dir,
        fetch,
        discover,
        download,
        settings=Settings(_env_file=None, data_dir=data_dir),

    ).run(video_id, job_id))

    with factory() as session:
        assert session.get(Video, video_id).status == VideoStatus.READY
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status) == (
            ProcessingStage.COMPLETED, JobStatus.COMPLETED)
        learning = session.scalar(select(LearningTranscriptSegment))
        run = session.scalar(select(TranscriptNormalizationRun))
        assert (learning.text, learning.normalization_version) == ('one two', 2)
        assert learning.normalization_run_id == run.id
        assert (run.method, run.normalization_version) == (
            'deterministic', 2)
        assert run.input_unit_count == 2


def test_pipeline_records_a_user_safe_failure(processing):
    factory, (video_id, job_id), data_dir = processing

    async def fail(_url):
        raise MetadataFetchError('private upstream details')

    asyncio.run(VideoImportPipeline(factory, data_dir, fail).run(video_id, job_id))
    with factory() as session:
        video = session.get(Video, video_id)
        job = session.get(ProcessingJob, job_id)
        assert video.status == VideoStatus.FAILED
        assert (job.stage, job.status, job.error_code) == (
            ProcessingStage.FAILED, JobStatus.FAILED, 'METADATA_FETCH_FAILED')
        assert job.error_message == '无法获取这个 YouTube 视频的信息，请确认视频仍可访问。'
        assert job.finished_at is not None


def test_pipeline_claim_prevents_duplicate_execution(processing):
    factory, (video_id, job_id), data_dir = processing
    calls = {'metadata': 0, 'captions': 0}

    async def fetch(_url):
        calls['metadata'] += 1
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def discover(_url):
        calls['captions'] += 1
        return [manual_caption()]

    async def download(_candidate):
        return b'WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n'

    pipeline = VideoImportPipeline(factory, data_dir, fetch, discover, download)
    asyncio.run(pipeline.run(video_id, job_id))
    asyncio.run(pipeline.run(video_id, job_id))
    assert calls == {'metadata': 1, 'captions': 1}
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RawTranscriptCue)) == 1
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 1
        assert session.get(Video, video_id).status == VideoStatus.READY


def test_normalization_claim_does_not_overwrite_existing_result(processing):
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        video = session.get(Video, video_id)
        video.subtitle_source = SubtitleSource.YOUTUBE_MANUAL
        video.subtitle_language = 'en'
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.NORMALIZING
        job.status = JobStatus.PENDING
        job.progress = 80
        cue = RawTranscriptCue(
            video_id=video_id,
            sequence_index=0,
            start_seconds=0,
            end_seconds=1,
            text='existing raw text',
            source_type=SubtitleSource.YOUTUBE_MANUAL,
        )
        session.add(cue)
        session.flush()
        revision = TranscriptRevision(video_id=video_id, origin='generated', revision_number=1)
        session.add(revision)
        session.flush()
        existing = LearningTranscriptSegment(
            video_id=video_id,
            revision_id=revision.id,
            sequence_index=0,
            text='Existing learning text.',
            start_seconds=0,
            end_seconds=1,
            source_ref_type='cue',
            source_refs={'cue_ids': [cue.id]},
            normalization_version=2,
        )
        session.add(existing)
        session.commit()
        existing_id = existing.id

    asyncio.run(VideoImportPipeline(
        factory,
        data_dir,
        settings=Settings(_env_file=None, data_dir=data_dir),

    )._run_normalization(video_id, job_id))

    with factory() as session:
        learning = session.scalars(select(LearningTranscriptSegment)).all()
        assert [(item.id, item.text) for item in learning] == [
            (existing_id, 'Existing learning text.'),
        ]
        assert session.scalar(select(func.count()).select_from(
            TranscriptNormalizationRun)) == 0
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.NORMALIZING, JobStatus.PENDING, 80)


def test_pipeline_falls_back_to_stt_and_cleans_audio_when_no_caption_is_selected(processing):
    factory, (video_id, job_id), data_dir = processing
    calls = {'audio': 0, 'transcribe': 0}

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def no_english(_url):
        return []

    async def acquire_audio(internal_video_id, url):
        calls['audio'] += 1
        assert internal_video_id == video_id
        assert url.endswith('aB3_dE-fGhI')
        with factory() as session:
            job = session.get(ProcessingJob, job_id)
            assert (job.stage, job.status, job.progress) == (
                ProcessingStage.DOWNLOADING_AUDIO, JobStatus.RUNNING, 20)
        return save_fake_audio(data_dir, video_id)

    async def transcribe(path):
        calls['transcribe'] += 1
        assert path.read_bytes() == b'audio'
        with factory() as session:
            job = session.get(ProcessingJob, job_id)
            assert (job.stage, job.status, job.progress) == (
                ProcessingStage.TRANSCRIBING, JobStatus.RUNNING, 40)
        return stt_result()

    pipeline = VideoImportPipeline(
        factory, data_dir, fetch, no_english,
        audio_fetcher=acquire_audio, audio_transcriber=transcribe,
        settings=Settings(_env_file=None, data_dir=data_dir), )
    asyncio.run(pipeline.run(video_id, job_id))
    asyncio.run(pipeline.run(video_id, job_id))
    assert calls == {'audio': 1, 'transcribe': 1}
    with factory() as session:
        video = session.get(Video, video_id)
        job = session.get(ProcessingJob, job_id)
        cues = session.scalars(select(RawTranscriptCue)).all()
        words = session.scalars(select(RawTranscriptWord).order_by(
            RawTranscriptWord.sequence_index)).all()
        learning = session.scalar(select(LearningTranscriptSegment))
        assert (video.status, video.subtitle_source, video.subtitle_language) == (
            VideoStatus.READY, SubtitleSource.STT, 'en')
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.COMPLETED, JobStatus.COMPLETED, 100)
        assert len(cues) == 1 and cues[0].source_type == SubtitleSource.STT
        assert [item.cue_id for item in words] == [cues[0].id, cues[0].id]
        assert learning.source_ref_type == 'cue'
        assert learning.source_refs == {'cue_ids': [cues[0].id]}
        assert learning.normalization_version == 2
        run = session.scalar(select(TranscriptNormalizationRun))
        assert (run.method, run.normalization_version) == ('deterministic', 2)
        assert learning.normalization_run_id == run.id
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_pipeline_records_caption_download_failure(processing):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def discover(_url):
        return [manual_caption()]

    async def fail_download(_candidate):
        raise CaptionDownloadError('private upstream response')

    asyncio.run(VideoImportPipeline(factory, data_dir, fetch, discover, fail_download).run(video_id, job_id))
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert job.error_code == 'CAPTION_DOWNLOAD_FAILED'
        assert 'private' not in job.error_message


def test_caption_discovery_failure_does_not_fall_back_to_audio(processing):
    from app.services.youtube.captions import CaptionDiscoveryError

    factory, (video_id, job_id), data_dir = processing
    calls = {'audio': 0}

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def fail_discovery(_url):
        raise CaptionDiscoveryError('private upstream failure')

    async def unexpected_audio(_video_id, _url):
        calls['audio'] += 1
        raise AssertionError('audio fallback must not run')

    pipeline = VideoImportPipeline(
        factory, data_dir, fetch, fail_discovery, audio_fetcher=unexpected_audio)
    asyncio.run(pipeline.run(video_id, job_id))
    assert calls['audio'] == 0
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert job.error_code == 'CAPTION_DISCOVERY_FAILED'


def test_caption_parse_failure_does_not_fall_back_to_audio(processing):
    factory, (video_id, job_id), data_dir = processing
    calls = {'audio': 0}

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def discover(_url):
        return [manual_caption()]

    async def invalid_caption(_candidate):
        return b'not webvtt'

    async def unexpected_audio(_video_id, _url):
        calls['audio'] += 1
        raise AssertionError('audio fallback must not run')

    pipeline = VideoImportPipeline(
        factory, data_dir, fetch, discover, invalid_caption,
        audio_fetcher=unexpected_audio)
    asyncio.run(pipeline.run(video_id, job_id))
    assert calls['audio'] == 0
    with factory() as session:
        assert session.get(ProcessingJob, job_id).error_code == 'CAPTION_PARSE_FAILED'


@pytest.mark.parametrize(('failure', 'expected_code'), [
    (AudioDownloadError('private download failure'), 'AUDIO_DOWNLOAD_FAILED'),
    (OSError('private save failure'), 'AUDIO_SAVE_FAILED'),
])
def test_audio_acquisition_failures_are_safe_and_terminal(
        processing, failure, expected_code):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def no_captions(_url):
        return []

    async def fail_audio(_video_id, _url):
        save_fake_audio(data_dir, video_id)
        raise failure

    pipeline = VideoImportPipeline(
        factory, data_dir, fetch, no_captions, audio_fetcher=fail_audio)
    asyncio.run(pipeline.run(video_id, job_id))
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.error_code) == (
            ProcessingStage.FAILED, JobStatus.FAILED, expected_code)
        assert 'private' not in job.error_message
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


@pytest.mark.parametrize(('failure', 'expected_code'), [
    (STTModelLoadError('private model failure'), 'STT_MODEL_UNAVAILABLE'),
    (STTTranscriptionError('private inference failure'), 'TRANSCRIPTION_FAILED'),
    (EmptyTranscriptionError('private empty output'), 'TRANSCRIPTION_EMPTY'),
    (TranscriptionValidationError('private invalid output'), 'TRANSCRIPTION_INVALID'),
])
def test_transcription_failures_are_safe_terminal_and_clean_audio(
        processing, failure, expected_code):
    factory, (video_id, job_id), data_dir = processing

    async def fetch(_url):
        return YouTubeMetadata('aB3_dE-fGhI', 'Lesson', None, None, None)

    async def no_captions(_url):
        return []

    async def acquire(internal_video_id, _url):
        return save_fake_audio(data_dir, internal_video_id)

    async def fail_transcription(_path):
        raise failure

    pipeline = VideoImportPipeline(
        factory, data_dir, fetch, no_captions,
        audio_fetcher=acquire, audio_transcriber=fail_transcription)
    asyncio.run(pipeline.run(video_id, job_id))
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.error_code) == (
            ProcessingStage.FAILED, JobStatus.FAILED, expected_code)
        assert 'private' not in job.error_message
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_missing_audio_and_cleanup_failure_have_distinct_safe_errors(processing, monkeypatch):
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.TRANSCRIBING
        job.status = JobStatus.PENDING
        job.progress = 40
        session.commit()
    pipeline = VideoImportPipeline(factory, data_dir)
    asyncio.run(pipeline.run(video_id, job_id))
    with factory() as session:
        assert session.get(ProcessingJob, job_id).error_code == 'AUDIO_FILE_MISSING'

    with factory() as session:
        video = Video(youtube_video_id='cl3_an-Up01',
                      youtube_url='https://www.youtube.com/watch?v=cl3_an-Up01')
        session.add(video)
        session.flush()
        job = ProcessingJob(video_id=video.id, stage=ProcessingStage.TRANSCRIBING,
                            status=JobStatus.PENDING, progress=40)
        session.add(job)
        session.commit()
        cleanup_ids = video.id, job.id
    save_fake_audio(data_dir, cleanup_ids[0])
    cleanup_pipeline = VideoImportPipeline(
        factory, data_dir, audio_transcriber=lambda _path: asyncio.sleep(0, result=stt_result()))
    monkeypatch.setattr(
        cleanup_pipeline.audio_store, 'cleanup',
        lambda _video_id: (_ for _ in ()).throw(OSError('private cleanup failure')))
    asyncio.run(cleanup_pipeline.run(*cleanup_ids))
    with factory() as session:
        cleanup_job = session.get(ProcessingJob, cleanup_ids[1])
        assert cleanup_job.error_code == 'AUDIO_CLEANUP_FAILED'
        assert 'private' not in cleanup_job.error_message


def test_pipeline_resumes_pending_transcription_without_downloading_again(processing):
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.TRANSCRIBING
        job.status = JobStatus.PENDING
        job.progress = 40
        session.commit()
    save_fake_audio(data_dir, video_id)
    calls = {'audio': 0, 'transcribe': 0}

    async def unexpected_audio(_video_id, _url):
        calls['audio'] += 1
        raise AssertionError('resumed transcription must reuse saved audio')

    async def transcribe(_path):
        calls['transcribe'] += 1
        return stt_result()

    pipeline = VideoImportPipeline(
        factory, data_dir, audio_fetcher=unexpected_audio,
        audio_transcriber=transcribe)
    asyncio.run(pipeline.run(video_id, job_id))
    assert calls == {'audio': 0, 'transcribe': 1}
    with factory() as session:
        assert session.get(Video, video_id).status == VideoStatus.READY
        assert session.get(ProcessingJob, job_id).status == JobStatus.COMPLETED
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_cancelled_transcription_records_interruption_and_cleans_audio(processing):
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.TRANSCRIBING
        job.status = JobStatus.PENDING
        job.progress = 40
        session.commit()
    save_fake_audio(data_dir, video_id)

    async def exercise_cancellation():
        started = asyncio.Event()

        async def wait_forever(_path):
            started.set()
            await asyncio.Future()

        pipeline = VideoImportPipeline(
            factory, data_dir, audio_transcriber=wait_forever)
        task = asyncio.create_task(pipeline.run(video_id, job_id))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise_cancellation())
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert (job.status, job.stage, job.error_code) == (
            JobStatus.FAILED, ProcessingStage.FAILED, 'PROCESS_INTERRUPTED')
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_stt_raw_save_failure_is_safe_and_cleans_audio(processing, monkeypatch):
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.TRANSCRIBING
        job.status = JobStatus.PENDING
        job.progress = 40
        session.commit()
    save_fake_audio(data_dir, video_id)
    pipeline = VideoImportPipeline(
        factory, data_dir,
        audio_transcriber=lambda _path: asyncio.sleep(0, result=stt_result()))
    monkeypatch.setattr(
        pipeline.jobs, 'save_stt_transcript',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('private database failure')))

    asyncio.run(pipeline.run(video_id, job_id))
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert (job.status, job.stage, job.error_code) == (
            JobStatus.FAILED, ProcessingStage.FAILED, 'STT_TRANSCRIPT_SAVE_FAILED')
        assert 'private' not in job.error_message
    assert not (data_dir / 'videos' / video_id / 'audio').exists()


def test_startup_recovery_fails_interrupted_running_and_returns_never_started(processing):
    factory, (pending_video_id, pending_job_id), _data_dir = processing
    with factory() as session:
        interrupted_video = Video(youtube_video_id='jK4_lM-nOpQ',
                                  youtube_url='https://www.youtube.com/watch?v=jK4_lM-nOpQ')
        session.add(interrupted_video)
        session.flush()
        interrupted_job = ProcessingJob(
            video_id=interrupted_video.id, stage=ProcessingStage.FETCHING_METADATA,
            status=JobStatus.RUNNING, started_at=datetime.now(UTC))
        session.add(interrupted_job)
        session.commit()
        interrupted_ids = interrupted_video.id, interrupted_job.id
        caption_video = Video(youtube_video_id='cA5_tI-oNqR',
                              youtube_url='https://www.youtube.com/watch?v=cA5_tI-oNqR')
        session.add(caption_video)
        session.flush()
        caption_job = ProcessingJob(video_id=caption_video.id, stage=ProcessingStage.FETCHING_CAPTIONS,
                                    status=JobStatus.PENDING, progress=10)
        session.add(caption_job)
        session.commit()
        caption_ids = caption_video.id, caption_job.id
        raw_video = Video(youtube_video_id='rA7_tR-aWqS',
                          youtube_url='https://www.youtube.com/watch?v=rA7_tR-aWqS',
                          subtitle_source=SubtitleSource.YOUTUBE_MANUAL,
                          subtitle_language='en')
        session.add(raw_video)
        session.flush()
        raw_job = ProcessingJob(video_id=raw_video.id, stage=ProcessingStage.FETCHING_CAPTIONS,
                                status=JobStatus.PENDING, progress=35)
        session.add(raw_job)
        session.commit()
        raw_ids = raw_video.id, raw_job.id

        normalizing_video = Video(youtube_video_id='nO8_mA-lIzE',
                                  youtube_url='https://www.youtube.com/watch?v=nO8_mA-lIzE',
                                  subtitle_source=SubtitleSource.YOUTUBE_MANUAL,
                                  subtitle_language='en')
        session.add(normalizing_video)
        session.flush()
        normalizing_job = ProcessingJob(
            video_id=normalizing_video.id, stage=ProcessingStage.NORMALIZING,
            status=JobStatus.PENDING, progress=80)
        session.add(normalizing_job)
        session.commit()
        normalizing_ids = normalizing_video.id, normalizing_job.id

        audio_video = Video(youtube_video_id='aU2_dI-oJob',
                            youtube_url='https://www.youtube.com/watch?v=aU2_dI-oJob')
        session.add(audio_video)
        session.flush()
        audio_job = ProcessingJob(
            video_id=audio_video.id, stage=ProcessingStage.DOWNLOADING_AUDIO,
            status=JobStatus.PENDING, progress=20)
        session.add(audio_job)
        session.commit()
        audio_ids = audio_video.id, audio_job.id

        transcription_video = Video(youtube_video_id='tR4_ns-CrIb',
                                    youtube_url='https://www.youtube.com/watch?v=tR4_ns-CrIb')
        session.add(transcription_video)
        session.flush()
        transcription_job = ProcessingJob(
            video_id=transcription_video.id, stage=ProcessingStage.TRANSCRIBING,
            status=JobStatus.PENDING, progress=40)
        session.add(transcription_job)
        session.commit()
        transcription_ids = transcription_video.id, transcription_job.id

    resumable = JobManager(factory).recover_after_restart()
    assert set(resumable) == {
        (pending_video_id, pending_job_id), caption_ids, raw_ids, normalizing_ids,
        audio_ids, transcription_ids}
    with factory() as session:
        video = session.get(Video, interrupted_ids[0])
        job = session.get(ProcessingJob, interrupted_ids[1])
        assert video.status == VideoStatus.FAILED
        assert (job.status, job.stage, job.error_code) == (
            JobStatus.FAILED, ProcessingStage.FAILED, 'PROCESS_INTERRUPTED')
        assert job.finished_at is not None


def test_startup_recovery_reexecutes_evidence_free_running_normalization(processing):
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        video = session.get(Video, video_id)
        video.subtitle_source = SubtitleSource.YOUTUBE_MANUAL
        video.subtitle_language = 'en'
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.NORMALIZING
        job.status = JobStatus.RUNNING
        job.progress = 80
        session.add(RawTranscriptCue(
            video_id=video_id,
            sequence_index=0,
            start_seconds=0,
            end_seconds=1,
            text='hello world',
            source_type=SubtitleSource.YOUTUBE_MANUAL,
        ))
        session.commit()

    assert JobManager(factory).recover_after_restart() == [(video_id, job_id)]
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.NORMALIZING, JobStatus.PENDING, 80)
        assert session.get(Video, video_id).status == VideoStatus.PROCESSING

    asyncio.run(VideoImportPipeline(
        factory,
        data_dir,
        settings=Settings(_env_file=None, data_dir=data_dir),

    ).run(video_id, job_id))
    with factory() as session:
        assert session.get(Video, video_id).status == VideoStatus.READY
        assert session.get(ProcessingJob, job_id).status == JobStatus.COMPLETED
        assert session.scalar(select(LearningTranscriptSegment)).normalization_version == 2


@pytest.mark.parametrize('partial_evidence', ['learning', 'run'])
def test_startup_recovery_rejects_partial_normalization_evidence(
    processing, partial_evidence,
):
    factory, (video_id, job_id), _data_dir = processing
    with factory() as session:
        video = session.get(Video, video_id)
        video.subtitle_source = SubtitleSource.YOUTUBE_MANUAL
        video.subtitle_language = 'en'
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.NORMALIZING
        job.status = JobStatus.RUNNING
        job.progress = 80
        if partial_evidence == 'learning':
            revision = TranscriptRevision(video_id=video_id, origin='generated', revision_number=1)
            session.add(revision)
            session.flush()
            session.add(LearningTranscriptSegment(
                video_id=video_id,
                revision_id=revision.id,
                sequence_index=0,
                text='partial',
                start_seconds=0,
                end_seconds=1,
                source_ref_type='cue',
                source_refs={'cue_ids': []},
                normalization_version=2,
            ))
        else:
            session.add(TranscriptNormalizationRun(
                video_id=video_id,
                job_id=job_id,
                method='deterministic',
                normalization_version=2,
                input_unit_count=1,
            ))
        session.commit()

    assert (video_id, job_id) not in JobManager(factory).recover_after_restart()
    with factory() as session:
        assert session.get(Video, video_id).status == VideoStatus.FAILED
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.error_code) == (
            ProcessingStage.FAILED, JobStatus.FAILED, 'PROCESS_INTERRUPTED')


def _prepare_raw_handoff(factory, video_id, job_id, data_dir, *, save_file=True):
    with factory() as session:
        video = session.get(Video, video_id)
        video.subtitle_source = SubtitleSource.YOUTUBE_MANUAL
        video.subtitle_language = 'en'
        job = session.get(ProcessingJob, job_id)
        job.stage = ProcessingStage.FETCHING_CAPTIONS
        job.status = JobStatus.PENDING
        job.progress = 35
        session.commit()
    if save_file:
        from app.services.processing.caption_store import CaptionStore
        CaptionStore(data_dir).save(
            video_id,
            b'WEBVTT\n\none\n00:00.125 --> 00:01.500\nFirst\n\n'
            b'00:01.400 --> 00:02.750\nSecond\n')


def test_raw_handoff_persists_stable_cue_ids_without_word_rows(processing):
    factory, (video_id, job_id), data_dir = processing
    _prepare_raw_handoff(factory, video_id, job_id, data_dir)
    asyncio.run(VideoImportPipeline(factory, data_dir)._run_raw_transcript(video_id, job_id))
    with factory() as session:
        cues = session.scalars(select(RawTranscriptCue).order_by(
            RawTranscriptCue.sequence_index)).all()
        assert len(cues) == 2
        assert len({cue.id for cue in cues}) == 2
        assert all(len(cue.id) == 36 for cue in cues)
        assert [(cue.start_seconds, cue.end_seconds, cue.text) for cue in cues] == [
            (0.125, 1.5, 'First'), (1.4, 2.75, 'Second')]
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord)) == 0
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.NORMALIZING, JobStatus.PENDING, 80)


def test_learning_segments_and_completion_roll_back_together(processing):
    factory, (video_id, job_id), data_dir = processing
    _prepare_raw_handoff(factory, video_id, job_id, data_dir)
    pipeline = VideoImportPipeline(factory, data_dir)
    asyncio.run(pipeline._run_raw_transcript(video_id, job_id))

    def fail_segment(*_):
        raise RuntimeError('intentional learning segment failure')

    event.listen(LearningTranscriptSegment, 'before_insert', fail_segment)
    try:
        asyncio.run(pipeline._run_normalization(video_id, job_id))
    finally:
        event.remove(LearningTranscriptSegment, 'before_insert', fail_segment)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 0
        assert session.scalar(select(func.count()).select_from(TranscriptNormalizationRun)) == 0
        assert session.get(Video, video_id).status == VideoStatus.FAILED
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.error_code) == (
            ProcessingStage.FAILED, JobStatus.FAILED, 'NORMALIZATION_FAILED')


def test_raw_handoff_reports_missing_saved_caption(processing):
    factory, (video_id, job_id), data_dir = processing
    _prepare_raw_handoff(factory, video_id, job_id, data_dir, save_file=False)
    asyncio.run(VideoImportPipeline(factory, data_dir).run(video_id, job_id))
    with factory() as session:
        assert session.get(ProcessingJob, job_id).error_code == 'CAPTION_FILE_MISSING'
        assert session.get(Video, video_id).status == VideoStatus.FAILED


def test_raw_cues_and_job_handoff_roll_back_together(processing):
    factory, (video_id, job_id), data_dir = processing
    _prepare_raw_handoff(factory, video_id, job_id, data_dir)

    def fail_second(_mapper, _connection, target):
        if target.sequence_index == 1:
            raise RuntimeError('intentional raw cue failure')

    event.listen(RawTranscriptCue, 'before_insert', fail_second)
    try:
        asyncio.run(VideoImportPipeline(factory, data_dir).run(video_id, job_id))
    finally:
        event.remove(RawTranscriptCue, 'before_insert', fail_second)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RawTranscriptCue)) == 0
        job = session.get(ProcessingJob, job_id)
        assert (job.status, job.stage, job.error_code) == (
            JobStatus.FAILED, ProcessingStage.FAILED, 'RAW_TRANSCRIPT_SAVE_FAILED')


@pytest.mark.parametrize('preference,tracks,expected', [
    ('manual_first', 'both', SubtitleSource.YOUTUBE_MANUAL),
    ('manual_first', 'auto', SubtitleSource.YOUTUBE_AUTO),
    ('auto_only', 'both', SubtitleSource.YOUTUBE_AUTO),
    ('auto_only', 'manual', SubtitleSource.STT),
])
def test_resumed_caption_job_uses_persisted_preference(processing, preference, tracks, expected):
    from app.core.enums import SubtitlePreference
    factory, (video_id, job_id), data_dir = processing
    with factory() as session:
        session.get(Video, video_id).subtitle_preference = SubtitlePreference(preference)
        session.get(ProcessingJob, job_id).stage = ProcessingStage.FETCHING_CAPTIONS
        session.get(ProcessingJob, job_id).progress = 10
        session.commit()
    assert JobManager(factory).recover_after_restart() == [(video_id, job_id)]
    downloaded = []
    audio_calls = []

    async def unexpected_metadata(_url):
        raise AssertionError('metadata is already complete')

    async def discover(_url):
        return {'both': [manual_caption(), automatic_caption()],
                'manual': [manual_caption()], 'auto': [automatic_caption()]}[tracks]

    async def download(selected):
        downloaded.append(selected.source)
        return b'WEBVTT\n\n00:00.000 --> 00:02.000\nHello there.\n'

    async def audio(identifier, _url):
        audio_calls.append(identifier)
        return save_fake_audio(data_dir, identifier)

    asyncio.run(VideoImportPipeline(
        factory, data_dir, unexpected_metadata, discover, download,
        audio_fetcher=audio, audio_transcriber=lambda _path: asyncio.sleep(0, result=stt_result())
    ).run(video_id, job_id))
    assert downloaded == ([] if expected == SubtitleSource.STT else [expected])
    assert audio_calls == ([video_id] if expected == SubtitleSource.STT else [])
    with factory() as session:
        video = session.get(Video, video_id)
        assert video.status == VideoStatus.READY
        assert video.subtitle_source == expected
        assert video.subtitle_preference == preference
        assert session.scalar(select(LearningTranscriptSegment)).translation_zh is None
