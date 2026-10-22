from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProcessingJob, Video


class VideoRepository:
    """Persistence operations only; transaction ownership stays with the caller."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, video: Video) -> Video:
        self.session.add(video)
        self.session.flush()
        return video

    def get(self, video_id: str) -> Video | None:
        return self.session.get(Video, video_id)

    def get_by_youtube_id(self, youtube_id: str) -> Video | None:
        return self.session.scalar(select(Video).where(Video.youtube_video_id == youtube_id))

    def get_latest_job(self, video_id: str):
        return self.session.scalar(select(ProcessingJob).where(ProcessingJob.video_id == video_id)
                                   .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc()).limit(1))

    def list_with_jobs(self):
        latest_id = (select(ProcessingJob.id).where(ProcessingJob.video_id == Video.id)
                     .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
                     .limit(1).correlate(Video).scalar_subquery())
        return self.session.execute(select(Video, ProcessingJob)
                                    .outerjoin(ProcessingJob, ProcessingJob.id == latest_id)
                                    .order_by(Video.created_at.desc(), Video.id.desc())).all()
