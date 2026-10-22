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
    TranscriptNormalizationRun,
    TranscriptRevision,
    Video,
)
from app.db.session import create_db_engine, create_session_factory
from app.services.processing.job_manager import JobManager
from app.services.transcript import NormalizationRunData, NormalizedSegmentData


@pytest.fixture
def normalization_database(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "normalization.db"}')
    command.upgrade(
        Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    engine = create_db_engine(Settings(_env_file=None))
    factory = create_session_factory(engine)
    with factory() as session:
        video = Video(
            youtube_video_id='normalize01',
            youtube_url='https://youtube.test/watch?v=normalize01',
            subtitle_source=SubtitleSource.YOUTUBE_MANUAL,
            subtitle_language='en',
        )
        session.add(video)
        session.flush()
        job = ProcessingJob(
            video_id=video.id,
            stage=ProcessingStage.NORMALIZING,
            status=JobStatus.RUNNING,
            progress=80,
        )
        cue = RawTranscriptCue(
            video_id=video.id,
            sequence_index=0,
            start_seconds=0,
            end_seconds=2,
            text='we sale cars',
            source_type=SubtitleSource.YOUTUBE_MANUAL,
        )
        session.add_all([job, cue])
        session.commit()
        identifiers = video.id, job.id, cue.id
    yield engine, factory, identifiers
    engine.dispose()


def result(cue_id: str):
    return ([NormalizedSegmentData(
        sequence_index=0, start_seconds=0, end_seconds=2, text='we sale cars',
        source_ref_type='cue', source_refs=(cue_id,), normalization_version=2)],
        NormalizationRunData(method='deterministic', normalization_version=2, input_unit_count=3))


def test_saves_audited_normalization_atomically(normalization_database):
    _, factory, (video_id, job_id, cue_id) = normalization_database
    segments, run_data = result(cue_id)

    assert JobManager(factory).save_normalization_result(
        video_id, job_id, segments, run_data)

    with factory() as session:
        run = session.scalar(select(TranscriptNormalizationRun))
        learning = session.scalar(select(LearningTranscriptSegment))
        video = session.get(Video, video_id)
        job = session.get(ProcessingJob, job_id)
        raw = session.get(RawTranscriptCue, cue_id)
        assert run.job_id == job_id
        assert (run.method, run.normalization_version, run.input_unit_count) == ('deterministic', 2, 3)
        assert learning.normalization_run_id == run.id
        assert learning.source_refs == {'cue_ids': [cue_id]}
        assert video.status == VideoStatus.READY
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.COMPLETED, JobStatus.COMPLETED, 100)
        assert raw.text == 'we sale cars'


def test_duplicate_save_does_not_overwrite_result(normalization_database):
    _, factory, identifiers = normalization_database
    video_id, job_id, cue_id = identifiers
    payload = result(cue_id)
    manager = JobManager(factory)
    assert manager.save_normalization_result(video_id, job_id, *payload)
    assert manager.save_normalization_result(video_id, job_id, *payload) is False
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptNormalizationRun)) == 1
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 1


@pytest.mark.parametrize('model', [TranscriptNormalizationRun, TranscriptRevision, LearningTranscriptSegment])
def test_failure_at_any_insert_stage_rolls_back_whole_batch(
    normalization_database, model,
):
    _, factory, (video_id, job_id, cue_id) = normalization_database

    def fail_insert(*_args):
        raise RuntimeError('injected persistence failure')

    event.listen(model, 'before_insert', fail_insert)
    try:
        with pytest.raises(RuntimeError, match='injected persistence failure'):
            JobManager(factory).save_normalization_result(
                video_id, job_id, *result(cue_id))
    finally:
        event.remove(model, 'before_insert', fail_insert)

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptNormalizationRun)) == 0
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 0
        assert session.get(Video, video_id).status == VideoStatus.PROCESSING
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.NORMALIZING, JobStatus.RUNNING, 80)
        assert session.get(RawTranscriptCue, cue_id).text == 'we sale cars'


def test_invalid_state_and_existing_learning_are_rejected(normalization_database):
    _, factory, (video_id, job_id, cue_id) = normalization_database
    manager = JobManager(factory)
    with factory() as session:
        session.get(ProcessingJob, job_id).status = JobStatus.PENDING
        session.commit()
    assert manager.save_normalization_result(video_id, job_id, *result(cue_id)) is False
    with factory() as session:
        session.get(ProcessingJob, job_id).status = JobStatus.RUNNING
        revision = TranscriptRevision(video_id=video_id, origin='generated', revision_number=1)
        session.add(revision)
        session.flush()
        session.add(LearningTranscriptSegment(
            video_id=video_id,
            revision_id=revision.id,
            sequence_index=0,
            text='Historical result',
            start_seconds=0,
            end_seconds=1,
            source_ref_type='cue',
            source_refs={'cue_ids': [cue_id]},
            normalization_version=2,
        ))
        session.commit()
    assert manager.save_normalization_result(video_id, job_id, *result(cue_id)) is False
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptNormalizationRun)) == 0
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 1


@pytest.mark.parametrize('fault', ['source', 'sequence', 'version'])
def test_invalid_generation_never_writes(normalization_database, fault):
    from dataclasses import replace
    _, factory, (video_id, job_id, cue_id) = normalization_database
    segments, run = result(cue_id)
    changes = {'source_refs': ('another-video-cue',)} if fault == 'source' else (
        {'sequence_index': 1} if fault == 'sequence' else {'normalization_version': 4})
    with pytest.raises(ValueError):
        JobManager(factory).save_normalization_result(
            video_id, job_id, [replace(segments[0], **changes)], run)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptNormalizationRun)) == 0
        assert session.scalar(select(func.count()).select_from(LearningTranscriptSegment)) == 0
        assert session.get(Video, video_id).current_revision_id is None
