"""One lifecycle-owned consumer for every first-import job in this process."""
import asyncio
from contextlib import suppress
import logging

from sqlalchemy import and_, or_, select

from app.core.enums import JobStatus, ProcessingStage, VideoStatus
from app.db.models import ProcessingJob, Video

logger = logging.getLogger(__name__)


def next_pending_job(session_factory):
    with session_factory() as session:
        row = session.execute(select(ProcessingJob.video_id, ProcessingJob.id).join(
            Video, Video.id == ProcessingJob.video_id).where(
            Video.status == VideoStatus.PROCESSING,
            ProcessingJob.status == JobStatus.PENDING,
            or_(and_(ProcessingJob.stage == ProcessingStage.FETCHING_METADATA, ProcessingJob.progress == 0),
                and_(ProcessingJob.stage == ProcessingStage.FETCHING_CAPTIONS, ProcessingJob.progress.in_((10, 35))),
                and_(ProcessingJob.stage == ProcessingStage.DOWNLOADING_AUDIO, ProcessingJob.progress == 20),
                and_(ProcessingJob.stage == ProcessingStage.TRANSCRIBING, ProcessingJob.progress == 40),
                and_(ProcessingJob.stage == ProcessingStage.NORMALIZING, ProcessingJob.progress == 80)))
            .order_by(ProcessingJob.created_at, ProcessingJob.id).limit(1)).first()
        return tuple(row) if row else None


class VideoImportScheduler:
    def __init__(self, pipeline, session_factory, *, poll_interval=1.0):
        self.pipeline = pipeline
        self.session_factory = session_factory
        self.poll_interval = poll_interval
        self._wake = asyncio.Event()
        self._task = None
        self.active_job = None

    def start(self):
        if self._task is not None:
            raise RuntimeError('Import scheduler already started')
        self._task = asyncio.create_task(self._consume(), name='video-import-consumer')

    async def wake(self):
        self._wake.set()

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def wait_idle(self, timeout=15):
        """Integration-test synchronization; requests never wait for processing."""
        async with asyncio.timeout(timeout):
            while True:
                if self.active_job is None:
                    pending = await asyncio.to_thread(next_pending_job, self.session_factory)
                    # A consumer may claim the pending job while this query runs.
                    if pending is None and self.active_job is None:
                        return
                await asyncio.sleep(0.01)

    async def _fail_active(self, video_id, job_id, *, interrupted=False):
        code = 'PROCESS_INTERRUPTED' if interrupted else 'PROCESS_STATE_CONFLICT'
        message = '处理已中断，可主动重试。' if interrupted else '导入任务状态不一致，请检查后重试。'
        try:
            await asyncio.to_thread(self.pipeline.audio_store.cleanup, video_id)
        except Exception:
            code, message = 'AUDIO_CLEANUP_FAILED', '临时音频无法完全清理，请检查数据目录后重试。'
            logger.exception('Unable to clean import audio for %s', video_id)
        await asyncio.to_thread(self.pipeline.jobs.fail, video_id, job_id, code, message)

    def _is_terminal(self, job_id):
        with self.session_factory() as session:
            job = session.get(ProcessingJob, job_id)
            return job is None or job.status in (JobStatus.COMPLETED, JobStatus.FAILED)

    async def _consume(self):
        while True:
            self._wake.clear()
            try:
                candidate = await asyncio.to_thread(next_pending_job, self.session_factory)
                if candidate is None:
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval)
                    except TimeoutError:
                        pass
                    continue
                self.active_job = candidate
                try:
                    await self.pipeline.run(*candidate)
                    if not await asyncio.to_thread(self._is_terminal, candidate[1]):
                        await self._fail_active(*candidate)
                except asyncio.CancelledError:
                    # Also catches cancellation while a stage claim is in flight.
                    await self._fail_active(*candidate, interrupted=True)
                    raise
                except Exception:
                    logger.exception('Unexpected import failure for %s', candidate[0])
                    await self._fail_active(*candidate)
                finally:
                    self.active_job = None
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Import scheduler could not update persistent work')
                # A transient database failure must not kill the consumer or cause a tight loop.
                await asyncio.sleep(self.poll_interval)
