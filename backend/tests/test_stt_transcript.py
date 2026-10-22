import asyncio
import math
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, select

from app.core.config import Settings
from app.core.enums import JobStatus, ProcessingStage, SubtitleSource
from app.db.models import ProcessingJob, RawTranscriptCue, RawTranscriptWord, Video
from app.db.session import create_db_engine, create_session_factory
from app.services.processing.job_manager import JobManager
from app.services.transcript import (
    FasterWhisperTranscriber,
    STTTranscriptionError,
    TranscriptNormalizer,
    TranscriptionValidationError,
    map_transcription,
)


def word(text=' Hello', start=0.1, end=0.5, probability=0.9):
    return SimpleNamespace(word=text, start=start, end=end, probability=probability)


def segment(index=0, start=0.0, end=1.0, text=' Hello.', words=None):
    return SimpleNamespace(
        id=index,
        seek=index * 100,
        start=start,
        end=end,
        text=text,
        tokens=[10 + index],
        avg_logprob=-0.2,
        compression_ratio=1.1,
        no_speech_prob=0.05,
        temperature=0.0,
        words=[word()] if words is None else words,
    )


def info(language='en', probability=0.99, duration=2.0, duration_after_vad=1.8):
    return SimpleNamespace(
        language=language,
        language_probability=probability,
        duration=duration,
        duration_after_vad=duration_after_vad,
    )


def transcription():
    return map_transcription([
        segment(words=[word(' Hello', 0.1, 0.4, 0.95), word(' world.', 0.4, 0.9, 0.8)]),
        segment(1, 1.0, 2.0, ' Again.', [word(' Again.', 1.1, 1.7, 0.7)]),
    ], info())


def test_mapping_preserves_model_text_times_probability_and_segment_evidence():
    result = transcription()
    assert (result.language, result.language_probability,
            result.duration_seconds, result.duration_after_vad_seconds) == (
                'en', 0.99, 2.0, 1.8)
    assert [(item.sequence_index, item.start_seconds, item.end_seconds, item.text)
            for item in result.segments] == [
        (0, 0.0, 1.0, ' Hello.'), (1, 1.0, 2.0, ' Again.')]
    assert [(item.text, item.start_seconds, item.end_seconds, item.confidence)
            for item in result.segments[0].words] == [
        (' Hello', 0.1, 0.4, 0.95), (' world.', 0.4, 0.9, 0.8)]
    assert result.segments[1].source_payload == {
        'segment_id': 1,
        'seek': 100,
        'tokens': [11],
        'avg_logprob': -0.2,
        'compression_ratio': 1.1,
        'no_speech_probability': 0.05,
        'temperature': 0.0,
    }


def test_mapping_keeps_missing_word_evidence_missing_without_interpolation():
    result = map_transcription([
        segment(words=[word(start=None, end=None, probability=None)]),
    ], info(probability=None))
    mapped = result.segments[0].words[0]
    assert (mapped.start_seconds, mapped.end_seconds, mapped.confidence) == (None, None, None)
    assert result.language_probability is None


@pytest.mark.parametrize(('segments', 'metadata', 'message'), [
    ([], info(), 'no segments'),
    ([segment(text='  ')], info(), 'segment text'),
    ([segment(start=math.nan)], info(), 'segment start'),
    ([segment(start=2, end=1)], info(), 'segment end precedes'),
    ([segment(start=1.0, end=2.0), segment(1, start=0.5, end=1.0)],
     info(), 'segments are not ordered'),
    ([segment(words=[word(text=' ')])], info(), 'word text'),
    ([segment(words=[word(start=0.8, end=0.2)])], info(), 'word end precedes'),
    ([segment(words=[word(start=-0.1)])], info(), 'word start'),
    ([segment(words=[word(probability=math.nan)])], info(), 'word confidence'),
    ([segment(words=[word(probability=1.1)])], info(), 'word confidence'),
    ([segment(words=[word(start=0.8, end=0.9), word(start=0.2, end=0.5)])],
     info(), 'words are not ordered'),
    ([segment()], info(language=''), 'language'),
    ([segment()], info(duration=-1), 'audio duration'),
])
def test_mapping_rejects_empty_nonfinite_negative_or_unordered_output(
        segments, metadata, message):
    with pytest.raises(TranscriptionValidationError, match=message):
        map_transcription(segments, metadata)


def test_transcriber_loads_local_model_and_consumes_lazy_segments_off_event_loop(tmp_path):
    main_thread = threading.get_ident()
    calls = {}

    class FakeModel:
        def transcribe(self, audio_path, **options):
            calls.update(audio_path=audio_path, options=options,
                         transcribe_thread=threading.get_ident())

            def lazy_segments():
                calls['iterate_thread'] = threading.get_ident()
                yield segment()

            return lazy_segments(), info(duration=1.0, duration_after_vad=1.0)

    def factory(model_path, **options):
        calls.update(model_path=model_path, model_options=options,
                     load_thread=threading.get_ident())
        return FakeModel()

    model_path = tmp_path / 'model'
    audio_path = tmp_path / 'audio.webm'
    result = asyncio.run(FasterWhisperTranscriber(
        Settings(_env_file=None, stt_model_path=model_path), factory).transcribe(audio_path))

    assert calls['model_path'] == str(model_path)
    assert calls['model_options'] == {
        'device': 'cpu', 'compute_type': 'int8', 'local_files_only': True}
    assert calls['audio_path'] == str(audio_path)
    assert calls['options'] == {
        'language': 'en', 'vad_filter': True, 'word_timestamps': True}
    assert calls['load_thread'] != main_thread
    assert calls['transcribe_thread'] == calls['load_thread'] == calls['iterate_thread']
    assert len(result.segments) == 1


def test_transcriber_reuses_model_and_wraps_runtime_failures(tmp_path):
    created = []

    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            raise RuntimeError('private model failure')

    def factory(*_args, **_kwargs):
        created.append(True)
        return FakeModel()

    transcriber = FasterWhisperTranscriber(
        Settings(_env_file=None, stt_model_path=tmp_path / 'model'), factory)
    for _ in range(2):
        with pytest.raises(STTTranscriptionError, match='could not transcribe') as caught:
            asyncio.run(transcriber.transcribe(tmp_path / 'audio.webm'))
        assert isinstance(caught.value.__cause__, RuntimeError)
    assert len(created) == 1


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "stt.db"}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    engine = create_db_engine(Settings(_env_file=None, data_dir=tmp_path))
    factory = create_session_factory(engine)
    with factory() as session:
        video = Video(
            youtube_video_id='sT3_tE-sT01',
            youtube_url='https://www.youtube.com/watch?v=sT3_tE-sT01')
        session.add(video)
        session.flush()
        job = ProcessingJob(
            video_id=video.id,
            stage=ProcessingStage.TRANSCRIBING,
            status=JobStatus.RUNNING,
            progress=40,
        )
        session.add(job)
        session.commit()
        identifiers = video.id, job.id
    yield factory, identifiers
    engine.dispose()


def test_stt_cues_words_and_job_handoff_commit_atomically_with_stable_uuids(database):
    factory, (video_id, job_id) = database
    persisted = JobManager(factory).save_stt_transcript(
        video_id, job_id, transcription())
    assert persisted is not None
    assert len({cue.id for cue in persisted.cues}) == 2
    assert len({item.id for item in persisted.words}) == 3
    assert all(len(item.id) == 36 for item in (*persisted.cues, *persisted.words))
    assert [item.cue_id for item in persisted.words] == [
        persisted.cues[0].id, persisted.cues[0].id, persisted.cues[1].id]

    with factory() as session:
        cues = session.scalars(select(RawTranscriptCue).order_by(
            RawTranscriptCue.sequence_index)).all()
        words = session.scalars(select(RawTranscriptWord).order_by(
            RawTranscriptWord.sequence_index)).all()
        job = session.get(ProcessingJob, job_id)
        assert all(cue.source_type == SubtitleSource.STT for cue in cues)
        assert [cue.id for cue in cues] == [cue.id for cue in persisted.cues]
        assert [(item.sequence_index, item.text, item.start_seconds,
                 item.end_seconds, item.confidence) for item in words] == [
            (0, ' Hello', 0.1, 0.4, 0.95),
            (1, ' world.', 0.4, 0.9, 0.8),
            (2, ' Again.', 1.1, 1.7, 0.7),
        ]
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.NORMALIZING, JobStatus.PENDING, 80)

    learning = TranscriptNormalizer().normalize(list(persisted.cues))
    assert learning[0].source_ref_type == 'cue'
    assert learning[0].source_refs == {'cue_ids': [persisted.cues[0].id]}
    assert 'word' not in learning[0].source_refs


def test_stt_persistence_keeps_missing_word_values_null(database):
    factory, (video_id, job_id) = database
    missing = map_transcription([
        segment(words=[word(start=None, end=None, probability=None)]),
    ], info())
    JobManager(factory).save_stt_transcript(video_id, job_id, missing)
    with factory() as session:
        stored = session.scalar(select(RawTranscriptWord))
        assert (stored.start_seconds, stored.end_seconds, stored.confidence) == (
            None, None, None)


def test_stt_persistence_rejects_wrong_state_or_existing_raw(database):
    factory, (video_id, job_id) = database
    manager = JobManager(factory)
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        job.status = JobStatus.PENDING
        session.commit()
    assert manager.save_stt_transcript(video_id, job_id, transcription()) is None
    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        job.status = JobStatus.RUNNING
        session.add(RawTranscriptCue(
            video_id=video_id, sequence_index=0, start_seconds=0, end_seconds=1,
            text='existing', source_type=SubtitleSource.STT))
        session.commit()
    assert manager.save_stt_transcript(video_id, job_id, transcription()) is None


def test_stt_cues_words_and_job_handoff_roll_back_together(database):
    factory, (video_id, job_id) = database

    def fail_second_word(_mapper, _connection, target):
        if target.sequence_index == 1:
            raise RuntimeError('intentional word failure')

    event.listen(RawTranscriptWord, 'before_insert', fail_second_word)
    try:
        with pytest.raises(RuntimeError, match='intentional word failure'):
            JobManager(factory).save_stt_transcript(video_id, job_id, transcription())
    finally:
        event.remove(RawTranscriptWord, 'before_insert', fail_second_word)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RawTranscriptCue)) == 0
        assert session.scalar(select(func.count()).select_from(RawTranscriptWord)) == 0
        job = session.get(ProcessingJob, job_id)
        assert (job.stage, job.status, job.progress) == (
            ProcessingStage.TRANSCRIBING, JobStatus.RUNNING, 40)
