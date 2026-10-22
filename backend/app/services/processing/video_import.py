import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.services.processing.audio_acquisition import AudioAcquirer
from app.services.processing.audio_store import AudioArtifact, AudioStore
from app.services.processing.caption_store import CaptionStore
from app.services.processing.job_manager import JobManager
from app.services.transcript import (
    EmptyTranscriptionError,
    FasterWhisperTranscriber,
    STTModelLoadError,
    STTTranscriptionError,
    TranscriptNormalizationService,
    TranscriptionData,
    TranscriptionValidationError,
    VTTParseError,
    parse_vtt,
)
from app.services.youtube.audio import AudioDownloadError
from app.services.youtube.captions import (
    CaptionCandidate,
    CaptionDiscoveryError,
    CaptionDownloadError,
    discover_captions,
    download_caption,
    select_best_caption,
)
from app.services.youtube.metadata import MetadataFetchError, YouTubeMetadata, fetch_metadata

MetadataFetcher = Callable[[str], Awaitable[YouTubeMetadata]]
CaptionDiscoverer = Callable[[str], Awaitable[list[CaptionCandidate]]]
CaptionDownloader = Callable[[CaptionCandidate], Awaitable[bytes]]
AudioFetcher = Callable[[str, str], Awaitable[AudioArtifact]]
AudioTranscriber = Callable[[Path], Awaitable[TranscriptionData]]
logger = logging.getLogger(__name__)


class _STTSaveError(RuntimeError):
    pass


class VideoImportPipeline:
    def __init__(self, session_factory: sessionmaker[Session], data_dir: Path,
                 metadata_fetcher: MetadataFetcher | None = None,
                 caption_discoverer: CaptionDiscoverer | None = None,
                 caption_downloader: CaptionDownloader | None = None,
                 audio_fetcher: AudioFetcher | None = None,
                 audio_transcriber: AudioTranscriber | None = None,
                 settings: Settings | None = None):
        self.jobs = JobManager(session_factory)
        self.store = CaptionStore(data_dir)
        self.audio_store = AudioStore(data_dir)
        self.fetch_metadata = metadata_fetcher or fetch_metadata
        self.discover_captions = caption_discoverer or discover_captions
        self.download_caption = caption_downloader or download_caption
        self.acquire_audio = audio_fetcher or AudioAcquirer(self.audio_store).acquire
        runtime_settings = settings or Settings(data_dir=data_dir)
        self.transcribe_audio = (
            audio_transcriber or FasterWhisperTranscriber(runtime_settings).transcribe)
        self.normalization_service = TranscriptNormalizationService()
        self.normalize_transcript = self.normalization_service.normalize

    async def run(self, video_id: str, job_id: str) -> None:
        if not await self._run_metadata(video_id, job_id):
            return
        if not await self._run_captions(video_id, job_id):
            return
        if not await self._run_audio_download(video_id, job_id):
            return
        if not await self._run_transcription(video_id, job_id):
            return
        await self._run_raw_transcript(video_id, job_id)
        await self._run_normalization(video_id, job_id)

    async def _run_metadata(self, video_id: str, job_id: str) -> bool:
        job = await asyncio.to_thread(self.jobs.claim_metadata, video_id, job_id)
        if job is None:
            return True
        try:
            metadata = await self.fetch_metadata(job.video_url)
            if metadata.video_id != job.youtube_video_id:
                raise MetadataFetchError('metadata video id did not match the saved video')
            return await asyncio.to_thread(self.jobs.save_metadata, video_id, job_id, metadata)
        except asyncio.CancelledError:
            await self._fail(video_id, job_id, 'PROCESS_INTERRUPTED',
                             '处理因应用停止而中断，可主动重试。')
            raise
        except MetadataFetchError:
            await self._fail(video_id, job_id, 'METADATA_FETCH_FAILED',
                             '无法获取这个 YouTube 视频的信息，请确认视频仍可访问。')
        except Exception:
            logger.exception('Unexpected metadata failure for video %s', video_id)
            await self._fail(video_id, job_id, 'METADATA_FETCH_FAILED',
                             '获取视频信息时发生意外错误，请稍后重试。')
        return False

    async def _run_captions(self, video_id: str, job_id: str) -> bool:
        job = await asyncio.to_thread(self.jobs.claim_captions, video_id, job_id)
        if job is None:
            return True
        try:
            candidates = await self.discover_captions(job.video_url)
            selected = select_best_caption(candidates, job.subtitle_preference)
            if selected is None:
                started = await asyncio.to_thread(
                    self.jobs.start_audio_download, video_id, job_id)
                if not started:
                    raise RuntimeError('caption job changed before STT fallback')
                return True
            content = await self.download_caption(selected)
            await asyncio.to_thread(self.store.save, video_id, content)
            saved = await asyncio.to_thread(
                self.jobs.save_caption, video_id, job_id, selected.source, selected.language)
            if not saved:
                raise RuntimeError('caption job changed before completion')
            return True
        except asyncio.CancelledError:
            await self._fail(video_id, job_id, 'PROCESS_INTERRUPTED',
                             '处理因应用停止而中断，可主动重试。')
            raise
        except CaptionDiscoveryError:
            await self._fail(video_id, job_id, 'CAPTION_DISCOVERY_FAILED',
                             '暂时无法检查这个视频的字幕，请稍后重试。')
        except CaptionDownloadError:
            await self._fail(video_id, job_id, 'CAPTION_DOWNLOAD_FAILED',
                             '找到了英文字幕，但暂时无法下载。')
        except OSError:
            logger.exception('Unable to save caption for video %s', video_id)
            await self._fail(video_id, job_id, 'CAPTION_SAVE_FAILED',
                             '字幕已获取，但无法保存到本地数据目录。')
        except Exception:
            logger.exception('Unexpected caption failure for video %s', video_id)
            await self._fail(video_id, job_id, 'CAPTION_DISCOVERY_FAILED',
                             '处理英文字幕时发生意外错误，请稍后重试。')
        return False

    async def _run_audio_download(self, video_id: str, job_id: str) -> bool:
        job = await asyncio.to_thread(self.jobs.claim_audio_download, video_id, job_id)
        if job is None:
            return True
        try:
            await self.acquire_audio(video_id, job.video_url)
            saved = await asyncio.to_thread(
                self.jobs.save_audio_download, video_id, job_id)
            if not saved:
                raise RuntimeError('audio job changed before completion')
            return True
        except asyncio.CancelledError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'PROCESS_INTERRUPTED',
                '处理因应用停止而中断，可主动重试。')
            raise
        except AudioDownloadError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'AUDIO_DOWNLOAD_FAILED',
                '没有可用英文字幕，且暂时无法获取转写所需的音频。')
        except (OSError, ValueError):
            logger.exception('Unable to save audio for video %s', video_id)
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'AUDIO_SAVE_FAILED',
                '音频已获取，但无法安全保存到本地数据目录。')
        except Exception:
            logger.exception('Unexpected audio download failure for video %s', video_id)
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'AUDIO_DOWNLOAD_FAILED',
                '获取转写音频时发生意外错误，请稍后重试。')
        return False

    async def _run_transcription(self, video_id: str, job_id: str) -> bool:
        claimed = await asyncio.to_thread(
            self.jobs.claim_transcription, video_id, job_id)
        if not claimed:
            return True
        try:
            artifact = await asyncio.to_thread(self.audio_store.load, video_id)
            transcription = await self.transcribe_audio(artifact.path)
            persisted = await asyncio.to_thread(
                self.jobs.save_stt_transcript, video_id, job_id, transcription)
            if persisted is None:
                raise _STTSaveError('transcription job changed before completion')
            return await self._cleanup_audio(video_id, job_id)
        except asyncio.CancelledError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'PROCESS_INTERRUPTED',
                '处理因应用停止而中断，可主动重试。')
            raise
        except FileNotFoundError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'AUDIO_FILE_MISSING',
                '已获取的转写音频不存在，无法继续处理。')
        except EmptyTranscriptionError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'TRANSCRIPTION_EMPTY',
                '音频中没有生成可保存的英文字幕。')
        except STTModelLoadError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'STT_MODEL_UNAVAILABLE',
                '本地语音识别模型不可用，请按运行说明完成准备。')
        except TranscriptionValidationError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'TRANSCRIPTION_INVALID',
                '语音识别返回了无效的字幕时间或文本。')
        except STTTranscriptionError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'TRANSCRIPTION_FAILED',
                '暂时无法将这个视频的音频转换为英文字幕。')
        except _STTSaveError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'STT_TRANSCRIPT_SAVE_FAILED',
                '语音识别已完成，但无法保存原始字幕记录。')
        except ValueError:
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'AUDIO_FILE_INVALID',
                '已获取的转写音频文件无效，无法继续处理。')
        except OSError:
            logger.exception('Unable to read audio for video %s', video_id)
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'AUDIO_READ_FAILED',
                '无法读取已获取的转写音频。')
        except Exception:
            logger.exception('Unexpected transcription failure for video %s', video_id)
            await self._fail_with_audio_cleanup(
                video_id, job_id, 'STT_TRANSCRIPT_SAVE_FAILED',
                '保存语音识别字幕时发生意外错误。')
        return False

    async def _run_raw_transcript(self, video_id: str, job_id: str) -> None:
        claimed = await asyncio.to_thread(self.jobs.claim_raw_transcript, video_id, job_id)
        if not claimed:
            return
        try:
            content = await asyncio.to_thread(self.store.load, video_id)
            cues = await asyncio.to_thread(parse_vtt, content)
            persisted = await asyncio.to_thread(
                self.jobs.save_raw_transcript, video_id, job_id, cues)
            if persisted is None:
                raise RuntimeError('raw transcript job changed before completion')
        except asyncio.CancelledError:
            await self._fail(video_id, job_id, 'PROCESS_INTERRUPTED',
                             '处理因应用停止而中断，可主动重试。')
            raise
        except FileNotFoundError:
            await self._fail(video_id, job_id, 'CAPTION_FILE_MISSING',
                             '已获取的字幕文件不存在，无法继续处理。')
        except VTTParseError:
            await self._fail(video_id, job_id, 'CAPTION_PARSE_FAILED',
                             '英文字幕格式无效，无法转换为可读取的原始字幕。')
        except OSError:
            logger.exception('Unable to read caption for video %s', video_id)
            await self._fail(video_id, job_id, 'CAPTION_READ_FAILED',
                             '无法读取已保存的字幕文件。')
        except Exception:
            logger.exception('Unable to save raw transcript for video %s', video_id)
            await self._fail(video_id, job_id, 'RAW_TRANSCRIPT_SAVE_FAILED',
                             '字幕已解析，但无法保存原始字幕记录。')

    async def _run_normalization(self, video_id: str, job_id: str) -> None:
        claimed = await asyncio.to_thread(self.jobs.claim_normalization, video_id, job_id)
        if not claimed:
            return
        try:
            evidence = await asyncio.to_thread(
                self.jobs.load_raw_transcript_evidence, video_id)
            if evidence is None:
                raise RuntimeError('normalization has no persisted Raw evidence')
            outcome = await self.normalize_transcript(evidence)
            saved = await asyncio.to_thread(
                self.jobs.save_normalization_result,
                video_id,
                job_id,
                outcome.segments,
                outcome.run,
            )
            if not saved:
                raise RuntimeError('normalization produced no savable transcript')
        except asyncio.CancelledError:
            await self._fail(video_id, job_id, 'PROCESS_INTERRUPTED',
                             '处理因应用停止而中断，可主动重试。')
            raise
        except Exception:
            logger.exception('Unable to normalize transcript for video %s', video_id)
            await self._fail(video_id, job_id, 'NORMALIZATION_FAILED',
                             '无法生成可读取的学习字幕。')

    async def _fail(self, video_id: str, job_id: str, code: str, message: str) -> None:
        await asyncio.to_thread(self.jobs.fail, video_id, job_id, code, message)

    async def _cleanup_audio(self, video_id: str, job_id: str) -> bool:
        try:
            await asyncio.to_thread(self.audio_store.cleanup, video_id)
            return True
        except Exception:
            logger.exception('Unable to clean audio for video %s', video_id)
            await self._fail(
                video_id, job_id, 'AUDIO_CLEANUP_FAILED',
                '处理已停止，但临时音频无法完全清理，请检查数据目录。')
            return False

    async def _fail_with_audio_cleanup(
            self, video_id: str, job_id: str, code: str, message: str) -> None:
        if await self._cleanup_audio(video_id, job_id):
            await self._fail(video_id, job_id, code, message)
