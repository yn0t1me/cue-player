import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api.routes.health import router as health_router
from app.api.routes.videos import router as videos_router
from app.api.routes.video_collections import router as collections_router
from app.services.youtube.playlists import fetch_playlist
from app.core.errors import register_error_handlers
from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.services.processing.audio_store import AudioStore
from app.services.processing.job_manager import JobManager
from app.services.processing.scheduler import VideoImportScheduler
from app.services.processing.video_import import (
    CaptionDiscoverer,
    CaptionDownloader,
    MetadataFetcher,
    VideoImportPipeline,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None,
               metadata_fetcher: MetadataFetcher | None = None,
               caption_discoverer: CaptionDiscoverer | None = None,
               caption_downloader: CaptionDownloader | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(settings)
        session_factory = create_session_factory(engine)
        app.state.session_factory = session_factory
        app.state.data_dir = settings.data_dir
        app.state.playlist_fetcher = fetch_playlist
        app.state.playlist_preview_slots = asyncio.Semaphore(2)
        pipeline = VideoImportPipeline(
            session_factory, settings.data_dir, metadata_fetcher,
            caption_discoverer, caption_downloader, settings=settings)
        app.state.video_import_pipeline = pipeline
        scheduler = VideoImportScheduler(pipeline, session_factory)
        app.state.video_import_scheduler = scheduler
        if settings.database_path.exists() and inspect(engine).has_table('processing_jobs'):
            jobs = JobManager(session_factory)
            audio_store = AudioStore(settings.data_dir)
            try:
                audio_store.cleanup_stale_staging()
            except Exception:
                logger.exception('Unable to clean stale audio staging directories')
            running = jobs.list_running_jobs()
            resumable = jobs.recover_after_restart()
            resumable_set = set(resumable)
            interrupted = [item for item in running if item not in resumable_set]
            for video_id, job_id in interrupted:
                try:
                    audio_store.cleanup(video_id)
                except Exception:
                    logger.exception('Unable to clean interrupted audio for video %s', video_id)
                    jobs.replace_interrupted_failure_with_cleanup_failure(video_id, job_id)
            scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()
            engine.dispose()

    app = FastAPI(title="Context English", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(collections_router, prefix='/api')
    app.include_router(videos_router, prefix="/api")
    register_error_handlers(app)
    return app


app = create_app()
