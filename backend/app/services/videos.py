from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import SubtitlePreference, ProcessingStage
from app.core.errors import AppError
from app.db.models import ProcessingJob, Video
from app.repositories.videos import VideoRepository
from app.schemas.videos import ImportVideoResponse, ProcessingJobResponse, VideoResponse
from app.services.youtube.parser import extract_video_id


def video_response(video: Video, job: ProcessingJob | None) -> VideoResponse:
    response = VideoResponse.model_validate(video)
    response.processing = ProcessingJobResponse.model_validate(job) if job else None
    return response


def save_new_video(session: Session, youtube_id: str,
                   subtitle_preference: SubtitlePreference) -> tuple[Video, ProcessingJob]:
    """Save without committing so a batch can own the whole transaction."""
    video = VideoRepository(session).add(Video(
        subtitle_preference=subtitle_preference, youtube_video_id=youtube_id,
        youtube_url=f'https://www.youtube.com/watch?v={youtube_id}'))
    job = ProcessingJob(video_id=video.id, stage=ProcessingStage.FETCHING_METADATA,
                        created_at=datetime.now(UTC))
    session.add(job)
    session.flush()
    return video, job


def import_video(session: Session, url: str,
                 subtitle_preference: SubtitlePreference = SubtitlePreference.MANUAL_FIRST) -> ImportVideoResponse:
    try:
        youtube_id = extract_video_id(url)
    except ValueError as error:
        raise AppError(422, 'INVALID_YOUTUBE_URL', '请输入有效的 YouTube 视频链接（watch、短链、shorts 或 embed）。') from error
    repository = VideoRepository(session)
    existing = repository.get_by_youtube_id(youtube_id)
    already_exists = existing is not None
    if existing is None:
        # End the read transaction before acquiring SQLite's writer lock. The
        # unique index resolves another importer winning this race.
        session.rollback()
        try:
            existing, _job = save_new_video(session, youtube_id, subtitle_preference)
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = repository.get_by_youtube_id(youtube_id)
            if existing is None:
                raise
            already_exists = True
    response = video_response(existing, repository.get_latest_job(existing.id))
    result = ImportVideoResponse(already_exists=already_exists, video=response, job=response.processing)
    # Response assembly opens a read transaction after the creation commit.
    # Release it before the background task claims the job in another Session.
    session.rollback()
    return result
