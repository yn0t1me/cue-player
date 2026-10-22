from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import JobStatus, ProcessingStage, SubtitleSource, VideoStatus
from app.db.models import (
    LearningTranscriptSegment,
    ProcessingJob,
    RawTranscriptCue,
    RawTranscriptWord,
    TranscriptChunkLayout,
    TranscriptChunkSegment,
    TranscriptNormalizationRun,
    TranscriptRevision,
    TranscriptMark,
    Video,
)
from app.db.session import create_db_engine
from app.repositories.videos import VideoRepository

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "nested/app.db"}')
    config = Config(str(BACKEND / 'alembic.ini'))
    command.upgrade(config, 'head')
    engine = create_db_engine(Settings(_env_file=None))
    yield engine, config
    engine.dispose()


def video(youtube_id='abcdefghijk'):
    return Video(youtube_video_id=youtube_id, youtube_url=f'https://youtube.com/watch?v={youtube_id}')


def test_migration_roundtrip_and_metadata_match(database):
    engine, config = database
    assert set(inspect(engine).get_table_names()) == {
        'alembic_version', 'videos', 'processing_jobs', 'raw_transcript_cues',
        'raw_transcript_words', 'learning_transcript_segments',
        'transcript_normalization_runs', 'transcript_revisions', 'transcript_marks',
        'transcript_chunk_layouts', 'transcript_chunk_segments',
        'transcript_mark_keys', 'transcript_questions',
        'video_collections', 'video_collection_items', 'video_import_previews',
        'video_import_batches', 'video_import_batch_items',
        'video_import_retry_requests', 'video_import_retry_bindings',
    }
    command.check(config)


def test_004_multiple_historical_versions_gain_initial_revisions(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "versions.db"}')
    config = Config(str(BACKEND / 'alembic.ini'))
    command.upgrade(config, '004_add_recoverable_batches')
    engine = create_db_engine(Settings(_env_file=None))
    with engine.begin() as connection:
        for number, version in enumerate((1, 2, 4), start=1):
            connection.execute(text(
                'INSERT INTO videos (id, youtube_video_id, youtube_url) '
                'VALUES (:id, :youtube_id, :url)'),
                {'id': f'video-{number}', 'youtube_id': f'oldvideo{number:03d}',
                 'url': f'https://youtube.test/{number}'})
            connection.execute(text(
                'INSERT INTO learning_transcript_segments '
                '(id, video_id, sequence_index, text, start_seconds, end_seconds, '
                'source_ref_type, source_refs, normalization_version) VALUES '
                '(:id, :video_id, 0, :body, 0, 1, :source, :refs, :version)'),
                {'id': f'learning-{number}', 'video_id': f'video-{number}',
                 'body': f'Historical {version}', 'source': 'cue',
                 'refs': '{"cue_ids": []}', 'version': version})
        connection.execute(text(
            "INSERT INTO videos (id, youtube_video_id, youtube_url) VALUES "
            "('video-pending', 'oldpending0', 'https://youtube.test/pending')"))
    engine.dispose()

    command.upgrade(config, '013_import_retries')
    engine = create_db_engine(Settings(_env_file=None))
    with Session(engine) as session:
        for number, version in enumerate((1, 2, 4), start=1):
            video_row = session.get(Video, f'video-{number}')
            learning = session.get(LearningTranscriptSegment, f'learning-{number}')
            revision = session.get(TranscriptRevision, video_row.current_revision_id)
            assert (revision.id, revision.video_id, revision.origin,
                    revision.revision_number) == (
                learning.revision_id, video_row.id, 'generated', 1)
            assert (learning.text, learning.normalization_version) == (
                f'Historical {version}', version)
        assert session.get(Video, 'video-pending').current_revision_id is None
    engine.dispose()

def test_repository_persistence_and_rollback(database):
    engine, _ = database
    with Session(engine) as session:
        repository = VideoRepository(session)
        item = repository.add(video())
        identifier = item.id
        assert UUID(identifier)
        assert item.status == VideoStatus.PROCESSING
        session.commit()
    with Session(engine) as session:
        repository = VideoRepository(session)
        item = repository.get(identifier)
        assert repository.get_by_youtube_id('abcdefghijk').id == identifier
        assert item.created_at.tzinfo == UTC
        item.title = 'Stored title'
        session.commit()
        assert item.updated_at >= item.created_at
        repository.add(video('uncommitted'))
    with Session(engine) as session:
        assert VideoRepository(session).get(identifier).title == 'Stored title'
        assert VideoRepository(session).get_by_youtube_id('uncommitted') is None
        assert VideoRepository(session).get('missing') is None


def test_duplicate_youtube_id_rejected(database):
    engine, _ = database
    with Session(engine) as session:
        session.add(video())
        session.commit()
        session.add(video())
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert len(session.scalars(select(Video)).all()) == 1


@pytest.mark.parametrize('model', [RawTranscriptCue, RawTranscriptWord, LearningTranscriptSegment])
def test_sequence_unique_per_video_not_global(database, model):
    engine, _ = database
    with Session(engine) as session:
        first, second = video(), video('secondvideo')
        session.add_all([first, second])
        session.flush()
        revisions = {}
        if model is LearningTranscriptSegment:
            for item in (first, second):
                revision = TranscriptRevision(video_id=item.id, origin='generated',
                                              revision_number=1)
                session.add(revision)
                session.flush()
                revisions[item.id] = revision.id

        def row(video_id, revision_id=None):
            values = dict(video_id=video_id, sequence_index=0, text='Original text')
            if model is not RawTranscriptWord:
                values.update(start_seconds=0.0, end_seconds=1.5)
            if model is RawTranscriptCue:
                values['source_type'] = SubtitleSource.YOUTUBE_MANUAL
            if model is LearningTranscriptSegment:
                values.update(revision_id=revision_id or revisions[video_id], source_ref_type='cue',
                              source_refs={'cue_ids': []})
            return model(**values)
        session.add_all([row(first.id), row(second.id)])
        session.commit()
        session.add(row(first.id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert len(session.scalars(select(model)).all()) == 2
        if model is LearningTranscriptSegment:
            newer = TranscriptRevision(video_id=first.id, origin='generated',
                                       revision_number=2)
            session.add(newer)
            session.flush()
            session.add(row(first.id, newer.id))
            session.commit()
            assert len(session.scalars(select(model)).all()) == 3


def test_json_optional_word_timing_and_utc_roundtrip(database):
    engine, _ = database
    with Session(engine) as session:
        item = video()
        session.add(item)
        session.flush()
        cue = RawTranscriptCue(video_id=item.id, sequence_index=0, start_seconds=0, end_seconds=1,
                               text='Hello', source_type=SubtitleSource.YOUTUBE_MANUAL,
                               source_payload={'lines': ['Hello'], 'source': '原始'})
        session.add(cue)
        session.flush()
        job = ProcessingJob(video_id=item.id, stage=ProcessingStage.FETCHING_METADATA,
                            started_at=datetime(2026, 9, 5, 18, tzinfo=timezone(timedelta(hours=8))))
        revision = TranscriptRevision(video_id=item.id, origin='generated',
                                      revision_number=1)
        session.add(revision)
        session.flush()
        session.add_all([job, RawTranscriptWord(video_id=item.id, cue_id=cue.id, sequence_index=0, text='Hello'),
                        LearningTranscriptSegment(video_id=item.id, revision_id=revision.id,
                                                  sequence_index=0, text='Hello',
                                                  start_seconds=0, end_seconds=1, source_ref_type='cue',
                                                  source_refs={'cue_ids': [cue.id]})])
        session.commit()
        session.expire_all()
        assert job.status == JobStatus.PENDING
        assert job.started_at == datetime(2026, 9, 5, 10, tzinfo=UTC)
        assert cue.source_payload == {'lines': ['Hello'], 'source': '原始'}
        assert session.scalar(select(RawTranscriptWord)).start_seconds is None
        assert session.scalar(select(LearningTranscriptSegment)).source_refs == {'cue_ids': [cue.id]}


def test_foreign_keys_and_delete_restriction(database):
    engine, _ = database
    with engine.connect() as connection:
        assert connection.scalar(text('PRAGMA foreign_keys')) == 1
    with Session(engine) as session:
        session.add(ProcessingJob(video_id='missing', stage=ProcessingStage.FETCHING_METADATA))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        item = video()
        session.add(item)
        session.flush()
        session.add(ProcessingJob(video_id=item.id, stage=ProcessingStage.FETCHING_METADATA))
        session.commit()
        session.delete(item)
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_checks_reject_invalid_progress_and_status(database):
    engine, _ = database
    with Session(engine) as session:
        item = video()
        session.add(item)
        session.commit()
        session.add(ProcessingJob(video_id=item.id, stage=ProcessingStage.FETCHING_METADATA, progress=101))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE videos SET status = 'unknown'"))
        session.rollback()


def test_transcript_mark_constraints_and_source_restriction(database):
    engine, _ = database
    with Session(engine) as session:
        item = video()
        item.status = VideoStatus.READY
        session.add(item)
        session.flush()
        revision = TranscriptRevision(video_id=item.id, origin='generated', revision_number=1)
        session.add(revision)
        session.flush()
        segment = LearningTranscriptSegment(
            video_id=item.id, revision_id=revision.id, sequence_index=0,
            text='Hello', start_seconds=0, end_seconds=1,
            source_ref_type='cue', source_refs={'cue_ids': []})
        session.add(segment)
        session.flush()
        item.current_revision_id = revision.id
        mark = TranscriptMark(
            video_id=item.id, revision_id=revision.id, segment_id=segment.id,
            start_offset=0, end_offset=5, selected_text='Hello')
        session.add(mark)
        session.commit()
        for statement in (
            'UPDATE transcript_marks SET end_offset = start_offset WHERE id = :id',
            "UPDATE transcript_marks SET selected_text = '  ' WHERE id = :id",
            "UPDATE transcript_marks SET segment_id = 'missing' WHERE id = :id",
        ):
            with pytest.raises(IntegrityError):
                session.execute(text(statement), {'id': mark.id})
            session.rollback()
        session.delete(segment)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(TranscriptMark, mark.id).selected_text == 'Hello'


def test_transcript_chunk_layout_constraints_and_source_restriction(database):
    engine, _ = database
    with Session(engine) as session:
        item = video()
        item.status = VideoStatus.READY
        session.add(item)
        session.flush()
        revision = TranscriptRevision(video_id=item.id, origin='generated', revision_number=1)
        session.add(revision)
        session.flush()
        segment = LearningTranscriptSegment(
            video_id=item.id, revision_id=revision.id, sequence_index=0,
            text='Hello world', start_seconds=0, end_seconds=1,
            source_ref_type='cue', source_refs={'cue_ids': []})
        session.add(segment)
        session.flush()
        item.current_revision_id = revision.id
        layout = TranscriptChunkLayout(
            video_id=item.id, revision_id=revision.id, content_sha256='a' * 64)
        session.add(layout)
        session.flush()
        chunk_segment = TranscriptChunkSegment(
            layout_id=layout.id, segment_id=segment.id, boundary_offsets=[5])
        session.add(chunk_segment)
        session.commit()
        session.add(TranscriptChunkLayout(
            video_id=item.id, revision_id=revision.id, content_sha256='b' * 64))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text(
                "UPDATE transcript_chunk_layouts SET content_sha256 = 'short' WHERE id = :id"),
                {'id': layout.id})
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text(
                "UPDATE transcript_chunk_segments SET segment_id = 'missing' WHERE id = :id"),
                {'id': chunk_segment.id})
        session.rollback()
        session.delete(segment)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(TranscriptChunkSegment, chunk_segment.id).boundary_offsets == [5]


def test_request_dependency_rolls_back_after_error(database):
    from fastapi import Depends, HTTPException
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.main import create_app

    engine, _ = database
    app = create_app(Settings(_env_file=None))

    @app.post('/test-rollback')
    def fail_after_write(session: Session = Depends(get_db)):
        VideoRepository(session).add(video('requestfail'))
        raise HTTPException(status_code=409, detail='Intentional test failure')

    with TestClient(app) as client:
        assert client.post('/test-rollback').status_code == 409
    with Session(engine) as session:
        assert VideoRepository(session).get_by_youtube_id('requestfail') is None


def test_word_cannot_reference_missing_cue(database):
    engine, _ = database
    with Session(engine) as session:
        item = video()
        session.add(item)
        session.flush()
        session.add(RawTranscriptWord(video_id=item.id, cue_id='missing', sequence_index=0, text='Hello'))
        with pytest.raises(IntegrityError):
            session.commit()


def test_naive_timestamp_is_rejected(database):
    from sqlalchemy.exc import StatementError

    engine, _ = database
    with Session(engine) as session:
        item = video()
        item.created_at = datetime(2026, 9, 5, 12)
        session.add(item)
        with pytest.raises(StatementError, match='Datetime must include a timezone'):
            session.commit()


def test_001_data_remains_readable_after_upgrade(tmp_path, monkeypatch):
    database_path = tmp_path / 'upgrade.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{database_path}')
    config = Config(str(BACKEND / 'alembic.ini'))
    command.upgrade(config, '001_create_m0_tables')
    engine = create_db_engine(Settings(_env_file=None))
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO videos (id, youtube_video_id, youtube_url) "
            "VALUES ('video-old', 'oldvideo001', 'https://youtube.test/old')"))
        connection.execute(text(
            "INSERT INTO learning_transcript_segments "
            "(id, video_id, sequence_index, text, start_seconds, end_seconds, "
            "source_ref_type, source_refs, normalization_version) VALUES "
            "('learning-old', 'video-old', 0, 'Old result', 0, 1, "
            "'cue', '{\"cue_ids\": []}', 2)"))
    engine.dispose()

    command.upgrade(config, 'head')
    engine = create_db_engine(Settings(_env_file=None))
    with Session(engine) as session:
        old = session.get(LearningTranscriptSegment, 'learning-old')
        assert old.text == 'Old result'
        assert old.normalization_version == 2
        assert old.normalization_run_id is None
        assert session.scalar(select(TranscriptNormalizationRun)) is None
    engine.dispose()
    command.upgrade(config, 'head')
    command.downgrade(config, 'base')
    assert set(inspect(engine).get_table_names()) == {'alembic_version'}
    command.upgrade(config, 'head')
    command.check(config)
