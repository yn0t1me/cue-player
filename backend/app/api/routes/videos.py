from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import AppError
from app.repositories.videos import VideoRepository
from app.schemas.errors import ErrorResponse
from app.schemas.transcripts import TranscriptResponse
from app.schemas.chunk_layouts import ChunkLayoutStateResponse
from app.schemas.transcript_marks import (
    CreateTranscriptMarkRequest, TranscriptMarkListResponse,
    TranscriptMarkResponse,
)
from app.schemas.videos import ImportVideoRequest, ImportVideoResponse, VideoListResponse, VideoResponse
from app.services.videos import import_video, video_response
from app.services.transcripts import (
    get_transcript, get_transcript_revision, list_transcript_revisions,
)
from app.services.srt_export import export_raw_srt
from app.services.transcript_marks import create_mark, delete_mark, list_marks
from app.services.chunk_layouts import get_chunk_layout

from app.schemas.source_learning import (
    LearningPublishResponse, SourceLearningPreviewRequest, SourceLearningPreviewResponse, SourceLearningPublishRequest,
)
from app.services.source_learning import (
    read_learning_source, preview_source_learning, publish_source_learning, export_learning_srt,
)


from app.schemas.video_collections import RetryVideoRequest, RetryVideoResponse
from app.services.import_retries import retry_video

router = APIRouter(prefix='/videos', tags=['videos'], responses={422: {'model': ErrorResponse}})
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post('', response_model=ImportVideoResponse, status_code=202,
             responses={200: {'model': ImportVideoResponse}})
def create_video(payload: ImportVideoRequest, request: Request, background_tasks: BackgroundTasks,
                 response: Response, session: DatabaseSession):
    result = import_video(session, payload.url, payload.subtitle_preference)
    response.status_code = 200 if result.already_exists else 202
    if not result.already_exists and result.job is not None:
        background_tasks.add_task(
            request.app.state.video_import_scheduler.wake)
    return result


@router.post('/{video_id}/retry', response_model=RetryVideoResponse, status_code=202,
             responses={200: {'model': RetryVideoResponse}})
def retry_failed_video(video_id: str, payload: RetryVideoRequest, request: Request,
                       response: Response, background_tasks: BackgroundTasks, session: DatabaseSession):
    result, replayed = retry_video(session, video_id, payload, request.app.state.data_dir)
    response.status_code = 200 if replayed else 202
    background_tasks.add_task(request.app.state.video_import_scheduler.wake)
    return result


@router.get('', response_model=VideoListResponse)
def list_videos(session: DatabaseSession):
    return VideoListResponse(items=[video_response(video, job)
                                    for video, job in VideoRepository(session).list_with_jobs()])


@router.get('/{video_id}', response_model=VideoResponse, responses={404: {'model': ErrorResponse}})
def get_video(video_id: str, session: DatabaseSession):
    repository = VideoRepository(session)
    video = repository.get(video_id)
    if video is None:
        raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频，请返回视频库。')
    return video_response(video, repository.get_latest_job(video.id))


@router.get('/{video_id}/transcript', response_model=TranscriptResponse,
            responses={404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}})
def read_transcript(video_id: str, session: DatabaseSession):
    return get_transcript(session, video_id)


@router.get('/{video_id}/transcript/export.srt',
            responses={404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}})
def download_raw_srt(video_id: str, session: DatabaseSession):
    content, youtube_id = export_raw_srt(session, video_id)
    return Response(
        content=content,
        media_type='application/x-subrip; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{youtube_id}-raw.srt"',
                 'Cache-Control': 'no-store'},
    )


@router.get('/{video_id}/transcript/revisions')
def read_transcript_revisions(video_id: str, session: DatabaseSession):
    return list_transcript_revisions(session, video_id)


@router.get('/{video_id}/transcript/revisions/{revision_id}',
            response_model=TranscriptResponse)
def read_transcript_revision(video_id: str, revision_id: str,
                             session: DatabaseSession):
    return get_transcript_revision(session, video_id, revision_id)


@router.get('/{video_id}/transcript/chunk-layout',
            response_model=ChunkLayoutStateResponse)
def read_chunk_layout(video_id: str, session: DatabaseSession):
    return get_chunk_layout(session, video_id)


@router.get('/{video_id}/marks', response_model=TranscriptMarkListResponse)
def read_transcript_marks(video_id: str, session: DatabaseSession):
    return list_marks(session, video_id)


@router.post('/{video_id}/marks', response_model=TranscriptMarkResponse,
             status_code=201, responses={200: {'model': TranscriptMarkResponse}})
def add_transcript_mark(video_id: str, payload: CreateTranscriptMarkRequest,
                        request: Request, response: Response):
    result, created = create_mark(request.app.state.session_factory, video_id, payload)
    response.status_code = 201 if created else 200
    return result


@router.delete('/{video_id}/marks/{mark_id}', status_code=204)
def remove_transcript_mark(video_id: str, mark_id: str, session: DatabaseSession):
    delete_mark(session, video_id, mark_id)


@router.get('/{video_id}/transcript/learning-source')
def read_source(video_id: str, request: Request, response: Response, session: DatabaseSession):
    source = read_learning_source(session, video_id, request.app.state.data_dir)
    response.headers['Cache-Control'] = 'no-store'
    return source.public_data()


@router.post('/{video_id}/transcript/source-learning/preview',
             response_model=SourceLearningPreviewResponse)
def preview_source(video_id: str, payload: SourceLearningPreviewRequest,
                   request: Request, session: DatabaseSession):
    return preview_source_learning(session, video_id, request.app.state.data_dir, payload.result)


@router.post('/{video_id}/transcript/source-learning', response_model=LearningPublishResponse)
def publish_source(video_id: str, payload: SourceLearningPublishRequest, request: Request):
    return publish_source_learning(request.app.state.session_factory, video_id,
                                   request.app.state.data_dir, payload.result,
                                   payload.expected_revision_id, payload.preview_digest)


@router.get('/{video_id}/transcript/learning-export.srt')
def download_learning_srt(video_id: str, session: DatabaseSession):
    content, youtube_id = export_learning_srt(session, video_id)
    return Response(content=content, media_type='application/x-subrip; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{youtube_id}-learning.srt"',
                             'Cache-Control': 'no-store'})
