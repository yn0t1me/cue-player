from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import (
    and_,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import SubtitlePreference, JobStatus, ProcessingStage, SubtitleSource, VideoStatus
from app.db.models import (
    LearningTranscriptSegment,
    ProcessingJob,
    RawTranscriptCue,
    RawTranscriptWord,
    TranscriptNormalizationRun,
    TranscriptRevision,
    Video,
)
from app.services.transcript import (
    NormalizationRunData,
    NormalizedSegmentData,
    PersistedRawCueData,
    PersistedRawWordData,
    PersistedSTTTranscript,
    RawTranscriptEvidence,
    RawCueData,
    TranscriptionData,
    persist_raw_cues,
    persist_stt_transcript,
)
from app.services.youtube.metadata import YouTubeMetadata


@dataclass(frozen=True, slots=True)
class MetadataJob:
    video_url: str
    youtube_video_id: str


@dataclass(frozen=True, slots=True)
class CaptionJob:
    video_url: str
    subtitle_preference: SubtitlePreference


@dataclass(frozen=True, slots=True)
class AudioJob:
    video_url: str


class JobManager:
    """Own short transactions around external processing work."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    @staticmethod
    def _lock_job(session: Session, job_id: str) -> None:
        # Reserve SQLite's writer before reading evidence/state that we will mutate.
        session.execute(update(ProcessingJob).where(ProcessingJob.id == job_id)
                        .values(progress=ProcessingJob.progress))

    def claim_metadata(self, video_id: str, job_id: str) -> MetadataJob | None:
        with self.session_factory() as session:
            claimed = session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id,
                       ProcessingJob.video_id == video_id,
                       ProcessingJob.status == JobStatus.PENDING,
                       ProcessingJob.stage == ProcessingStage.FETCHING_METADATA)
                .values(status=JobStatus.RUNNING, started_at=datetime.now(UTC),
                        error_code=None, error_message=None))
            if claimed.rowcount != 1:
                session.rollback()
                return None
            video = session.get(Video, video_id)
            if video is None:
                session.rollback()
                return None
            session.commit()
            return MetadataJob(video.youtube_url, video.youtube_video_id)

    def save_metadata(self, video_id: str, job_id: str, metadata: YouTubeMetadata) -> bool:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.FETCHING_METADATA):
                return False
            video.title = metadata.title
            video.channel_title = metadata.channel_title
            video.duration_seconds = metadata.duration
            video.thumbnail_url = metadata.thumbnail_url
            job.stage = ProcessingStage.FETCHING_CAPTIONS
            job.status = JobStatus.PENDING
            job.progress = 10
            session.commit()
            return True

    def claim_captions(self, video_id: str, job_id: str) -> CaptionJob | None:
        with self.session_factory() as session:
            claimed = session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id,
                       ProcessingJob.video_id == video_id,
                       ProcessingJob.status == JobStatus.PENDING,
                       ProcessingJob.stage == ProcessingStage.FETCHING_CAPTIONS,
                       ProcessingJob.progress < 35)
                .values(status=JobStatus.RUNNING, started_at=func.coalesce(
                    ProcessingJob.started_at, datetime.now(UTC))))
            if claimed.rowcount != 1:
                session.rollback()
                return None
            video = session.get(Video, video_id)
            if video is None:
                session.rollback()
                return None
            session.commit()
            return CaptionJob(video.youtube_url, video.subtitle_preference)

    def save_caption(self, video_id: str, job_id: str, source: SubtitleSource,
                     language: str) -> bool:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.FETCHING_CAPTIONS
                    or source not in (
                        SubtitleSource.YOUTUBE_MANUAL, SubtitleSource.YOUTUBE_AUTO)):
                return False
            video.subtitle_source = source
            video.subtitle_language = language
            job.status = JobStatus.PENDING
            job.progress = 35
            session.commit()
            return True

    def start_audio_download(self, video_id: str, job_id: str) -> bool:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.FETCHING_CAPTIONS
                    or job.progress != 10):
                return False
            job.stage = ProcessingStage.DOWNLOADING_AUDIO
            job.status = JobStatus.PENDING
            job.progress = 20
            session.commit()
            return True

    def claim_audio_download(self, video_id: str, job_id: str) -> AudioJob | None:
        with self.session_factory() as session:
            claimed = session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id,
                       ProcessingJob.video_id == video_id,
                       ProcessingJob.status == JobStatus.PENDING,
                       ProcessingJob.stage == ProcessingStage.DOWNLOADING_AUDIO,
                       ProcessingJob.progress == 20)
                .values(status=JobStatus.RUNNING, started_at=func.coalesce(
                    ProcessingJob.started_at, datetime.now(UTC))))
            if claimed.rowcount != 1:
                session.rollback()
                return None
            video = session.get(Video, video_id)
            if video is None:
                session.rollback()
                return None
            session.commit()
            return AudioJob(video.youtube_url)

    def save_audio_download(self, video_id: str, job_id: str) -> bool:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.DOWNLOADING_AUDIO
                    or job.progress != 20):
                return False
            job.stage = ProcessingStage.TRANSCRIBING
            job.status = JobStatus.PENDING
            job.progress = 40
            session.commit()
            return True

    def claim_transcription(self, video_id: str, job_id: str) -> bool:
        with self.session_factory() as session:
            claimed = session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id,
                       ProcessingJob.video_id == video_id,
                       ProcessingJob.status == JobStatus.PENDING,
                       ProcessingJob.stage == ProcessingStage.TRANSCRIBING,
                       ProcessingJob.progress == 40)
                .values(status=JobStatus.RUNNING, started_at=func.coalesce(
                    ProcessingJob.started_at, datetime.now(UTC))))
            if claimed.rowcount != 1:
                session.rollback()
                return False
            session.commit()
            return True

    def claim_raw_transcript(self, video_id: str, job_id: str) -> bool:
        with self.session_factory() as session:
            claimed = session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id,
                       ProcessingJob.video_id == video_id,
                       ProcessingJob.status == JobStatus.PENDING,
                       ProcessingJob.stage == ProcessingStage.FETCHING_CAPTIONS,
                       ProcessingJob.progress == 35)
                .values(status=JobStatus.RUNNING, started_at=func.coalesce(
                    ProcessingJob.started_at, datetime.now(UTC))))
            if claimed.rowcount != 1:
                session.rollback()
                return False
            session.commit()
            return True

    def save_raw_transcript(self, video_id: str, job_id: str,
                            cues: list[RawCueData]) -> list[PersistedRawCueData] | None:
        """Insert every cue and advance the job in the same transaction."""
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            source = video.subtitle_source if video is not None else None
            existing = session.scalar(
                select(RawTranscriptCue.id).where(RawTranscriptCue.video_id == video_id).limit(1))
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.FETCHING_CAPTIONS
                    or job.progress != 35
                    or source not in (
                        SubtitleSource.YOUTUBE_MANUAL, SubtitleSource.YOUTUBE_AUTO)
                    or existing is not None):
                return None
            persisted = persist_raw_cues(session, video_id, cues, source)
            job.stage = ProcessingStage.NORMALIZING
            job.status = JobStatus.PENDING
            job.progress = 80
            session.commit()
            return persisted

    def claim_normalization(self, video_id: str, job_id: str) -> bool:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            existing_learning = session.scalar(
                select(LearningTranscriptSegment.id)
                .where(LearningTranscriptSegment.video_id == video_id).limit(1))
            existing_run = session.scalar(
                select(TranscriptNormalizationRun.id)
                .where(TranscriptNormalizationRun.job_id == job_id).limit(1))
            if existing_learning is not None or existing_run is not None:
                session.rollback()
                return False
            claimed = session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id,
                       ProcessingJob.video_id == video_id,
                       ProcessingJob.status == JobStatus.PENDING,
                       ProcessingJob.stage == ProcessingStage.NORMALIZING,
                       ProcessingJob.progress == 80)
                .values(status=JobStatus.RUNNING, started_at=func.coalesce(
                    ProcessingJob.started_at, datetime.now(UTC))))
            if claimed.rowcount != 1:
                session.rollback()
                return False
            session.commit()
            return True

    def save_stt_transcript(self, video_id: str, job_id: str,
                            transcription: TranscriptionData) -> PersistedSTTTranscript | None:
        """Insert STT cues/words and advance the job in one transaction."""
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            existing_cue = session.scalar(
                select(RawTranscriptCue.id)
                .where(RawTranscriptCue.video_id == video_id).limit(1))
            existing_word = session.scalar(
                select(RawTranscriptWord.id)
                .where(RawTranscriptWord.video_id == video_id).limit(1))
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.TRANSCRIBING
                    or job.progress != 40
                    or existing_cue is not None or existing_word is not None):
                return None
            persisted = persist_stt_transcript(session, video_id, transcription)
            video.subtitle_source = SubtitleSource.STT
            video.subtitle_language = transcription.language
            job.stage = ProcessingStage.NORMALIZING
            job.status = JobStatus.PENDING
            job.progress = 80
            session.commit()
            return persisted


    def load_raw_transcript_evidence(
        self, video_id: str
    ) -> RawTranscriptEvidence | None:
        """Load one immutable normalization input without leaking ORM rows."""
        with self.session_factory() as session:
            video = session.get(Video, video_id)
            if (video is None or video.subtitle_source is None
                    or not video.subtitle_language):
                return None
            cues = session.scalars(
                select(RawTranscriptCue)
                .where(RawTranscriptCue.video_id == video_id)
                .order_by(RawTranscriptCue.sequence_index)).all()
            if not cues:
                return None
            words = session.scalars(
                select(RawTranscriptWord)
                .where(RawTranscriptWord.video_id == video_id)
                .order_by(RawTranscriptWord.sequence_index)).all()
            return RawTranscriptEvidence(
                source=video.subtitle_source,
                language=video.subtitle_language,
                cues=tuple(PersistedRawCueData(
                    id=row.id,
                    sequence_index=row.sequence_index,
                    start_seconds=row.start_seconds,
                    end_seconds=row.end_seconds,
                    text=row.text,
                ) for row in cues),
                words=tuple(PersistedRawWordData(
                    id=row.id,
                    cue_id=row.cue_id,
                    sequence_index=row.sequence_index,
                    text=row.text,
                    start_seconds=row.start_seconds,
                    end_seconds=row.end_seconds,
                    confidence=row.confidence,
                ) for row in words),
            )


    def save_normalization_result(
        self,
        video_id: str,
        job_id: str,
        segments: Sequence[NormalizedSegmentData],
        run_data: NormalizationRunData,
    ) -> bool:
        """Atomically persist initial subtitles and deterministic generation evidence."""
        self._validate_normalization_result(segments, run_data)
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            existing_learning = session.scalar(
                select(LearningTranscriptSegment.id)
                .where(LearningTranscriptSegment.video_id == video_id).limit(1))
            existing_run = session.scalar(
                select(TranscriptNormalizationRun.id)
                .where(TranscriptNormalizationRun.job_id == job_id).limit(1))
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.RUNNING
                    or job.stage != ProcessingStage.NORMALIZING
                    or job.progress != 80
                    or existing_learning is not None
                    or existing_run is not None
                    or video.current_revision_id is not None):
                return False
            self._validate_persisted_source_refs(
                session, video_id, segments)

            run = TranscriptNormalizationRun(
                video_id=video_id,
                job_id=job_id,
                method=run_data.method,
                normalization_version=run_data.normalization_version,
                input_unit_count=run_data.input_unit_count,
            )
            session.add(run)
            session.flush()

            revision = TranscriptRevision(video_id=video_id, origin='generated',
                                          revision_number=1)
            session.add(revision)
            session.flush()

            learning_rows = [LearningTranscriptSegment(
                video_id=video_id,
                revision_id=revision.id,
                sequence_index=segment.sequence_index,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                source_ref_type=segment.source_ref_type,
                source_refs={f'{segment.source_ref_type}_ids': list(segment.source_refs)},
                normalization_version=segment.normalization_version,
                normalization_run_id=run.id,
            ) for segment in segments]
            session.add_all(learning_rows)
            session.flush()
            video.status = VideoStatus.READY
            video.current_revision_id = revision.id
            job.stage = ProcessingStage.COMPLETED
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.finished_at = datetime.now(UTC)
            session.commit()
            return True


    @staticmethod
    def _validate_normalization_result(
        segments: Sequence[NormalizedSegmentData],
        run_data: NormalizationRunData,
    ) -> None:
        JobManager._validate_run_data(run_data)
        if not segments or [row.sequence_index for row in segments] != list(range(len(segments))):
            raise ValueError('Learning segment sequence must be continuous from zero')
        if any(row.normalization_version != run_data.normalization_version for row in segments):
            raise ValueError('Learning segment and run versions must match')
    @staticmethod
    def _validate_run_data(run_data: NormalizationRunData) -> None:
        if (run_data.input_unit_count <= 0 or run_data.method != 'deterministic'
                or run_data.normalization_version != 2):
            raise ValueError('Deterministic generation evidence is invalid')

    @staticmethod
    def _validate_persisted_source_refs(
        session: Session,
        video_id: str,
        segments: Sequence[NormalizedSegmentData],
    ) -> None:
        cue_ids: set[str] = set()
        for segment in segments:
            if not segment.source_refs:
                raise ValueError('Learning segment source refs must not be empty')
            if segment.source_ref_type == 'cue':
                cue_ids.update(segment.source_refs)
            else:
                raise ValueError('Learning segment source ref type is invalid')
        persisted_cues = set(session.scalars(
            select(RawTranscriptCue.id).where(
                RawTranscriptCue.video_id == video_id,
                RawTranscriptCue.id.in_(cue_ids),
            )).all()) if cue_ids else set()
        if persisted_cues != cue_ids:
            raise ValueError('Normalization source refs must belong to this Video Raw evidence')


    def fail(self, video_id: str, job_id: str, code: str, message: str) -> None:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            if job is None or video is None or job.video_id != video.id:
                return
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                return
            video.status = VideoStatus.FAILED
            job.stage = ProcessingStage.FAILED
            job.status = JobStatus.FAILED
            job.error_code = code
            job.error_message = message
            job.finished_at = datetime.now(UTC)
            session.commit()

    def replace_interrupted_failure_with_cleanup_failure(
            self, video_id: str, job_id: str) -> None:
        with self.session_factory() as session:
            self._lock_job(session, job_id)
            job = session.get(ProcessingJob, job_id)
            video = session.get(Video, video_id)
            if (job is None or video is None or job.video_id != video.id
                    or job.status != JobStatus.FAILED
                    or job.error_code != 'PROCESS_INTERRUPTED'):
                return
            job.error_code = 'AUDIO_CLEANUP_FAILED'
            job.error_message = '上次处理已中断，但临时音频无法完全清理，请检查数据目录。'
            session.commit()

    def list_running_jobs(self) -> list[tuple[str, str]]:
        with self.session_factory() as session:
            return list(session.execute(
                select(ProcessingJob.video_id, ProcessingJob.id)
                .where(ProcessingJob.status == JobStatus.RUNNING)).all())

    def recover_after_restart(self) -> list[tuple[str, str]]:
        """Fail interrupted work and return resumable pending jobs."""
        with self.session_factory() as session:
            interrupted = session.scalars(
                select(ProcessingJob).where(ProcessingJob.status == JobStatus.RUNNING)).all()
            now = datetime.now(UTC)
            for job in interrupted:
                video = session.get(Video, job.video_id)
                existing_learning = session.scalar(
                    select(LearningTranscriptSegment.id)
                    .where(LearningTranscriptSegment.video_id == job.video_id).limit(1))
                existing_run = session.scalar(
                    select(TranscriptNormalizationRun.id)
                    .where(TranscriptNormalizationRun.job_id == job.id).limit(1))
                if (video is not None
                        and video.status == VideoStatus.PROCESSING
                        and job.stage == ProcessingStage.NORMALIZING
                        and job.progress == 80
                        and existing_learning is None
                        and existing_run is None):
                    job.status = JobStatus.PENDING
                    job.error_code = None
                    job.error_message = None
                    job.finished_at = None
                    continue
                if video is not None:
                    video.status = VideoStatus.FAILED
                job.stage = ProcessingStage.FAILED
                job.status = JobStatus.FAILED
                job.error_code = 'PROCESS_INTERRUPTED'
                job.error_message = '上次处理因应用停止而中断，可主动重试。'
                job.finished_at = now
            resumable = session.execute(
                select(ProcessingJob.video_id, ProcessingJob.id)
                .where(ProcessingJob.status == JobStatus.PENDING,
                       or_(ProcessingJob.stage == ProcessingStage.FETCHING_METADATA,
                           and_(ProcessingJob.stage == ProcessingStage.FETCHING_CAPTIONS,
                                ProcessingJob.progress.in_((10, 35))),
                           and_(ProcessingJob.stage == ProcessingStage.DOWNLOADING_AUDIO,
                                ProcessingJob.progress == 20),
                           and_(ProcessingJob.stage == ProcessingStage.TRANSCRIBING,
                                ProcessingJob.progress == 40),
                           and_(ProcessingJob.stage == ProcessingStage.NORMALIZING,
                                ProcessingJob.progress == 80)))
                .order_by(ProcessingJob.created_at, ProcessingJob.id)).all()
            session.commit()
            return list(resumable)
