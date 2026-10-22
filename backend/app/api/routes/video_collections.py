import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import AppError
from app.schemas.errors import ErrorResponse
from app.schemas.video_collections import (
    BatchRequest, BatchResponse, CollectionCreate, CollectionPatch, CollectionMembersRequest,
    CollectionOrderRequest, CollectionDetailResponse, CollectionListResponse, PreviewRequest,
    PreviewResponse, RetryBatchRequest, RetryBatchResponse,
)
from app.services.import_retries import retry_batch
from app.services import video_collections as collections
from app.services.video_imports import make_preview, submit_batch, get_batch
from app.services.youtube.playlists import (
    PlaylistFetchError, PlaylistLimitError, normalize_playlist_url,
)

router = APIRouter(tags=['video collections'], responses={422: {'model': ErrorResponse}})
DatabaseSession = Annotated[Session, Depends(get_db)]
ExpectedVersion = Annotated[int, Query(ge=1)]


@router.get('/collections', response_model=CollectionListResponse)
def list_collections(session: DatabaseSession):
    return CollectionListResponse(items=collections.list_collections(session))


@router.post('/collections', response_model=CollectionDetailResponse, status_code=201)
def create_collection(payload: CollectionCreate, session: DatabaseSession):
    return collections.create_collection(session, payload)


@router.get('/collections/{collection_id}', response_model=CollectionDetailResponse)
def get_collection(collection_id: str, session: DatabaseSession):
    return collections.collection_response(session, collections.require_collection(session, collection_id), detail=True)


@router.patch('/collections/{collection_id}', response_model=CollectionDetailResponse)
def patch_collection(collection_id: str, payload: CollectionPatch, session: DatabaseSession):
    return collections.patch_collection(session, collection_id, payload)


@router.delete('/collections/{collection_id}', status_code=204)
def delete_collection(collection_id: str, expected_version: ExpectedVersion, session: DatabaseSession):
    collections.delete_collection(session, collection_id, expected_version)


@router.post('/collections/{collection_id}/items', response_model=CollectionDetailResponse)
def add_members(collection_id: str, payload: CollectionMembersRequest, session: DatabaseSession):
    return collections.add_members(session, collection_id, payload.video_ids, payload.expected_version)


@router.delete('/collections/{collection_id}/items/{item_id}', status_code=204)
def remove_member(collection_id: str, item_id: str, expected_version: ExpectedVersion, session: DatabaseSession):
    collections.remove_member(session, collection_id, item_id, expected_version)


@router.patch('/collections/{collection_id}/order', response_model=CollectionDetailResponse)
def reorder_members(collection_id: str, payload: CollectionOrderRequest, session: DatabaseSession):
    return collections.reorder_members(session, collection_id, payload.item_ids, payload.expected_version)


@router.post('/video-import-previews', response_model=PreviewResponse)
async def create_preview(payload: PreviewRequest, request: Request):
    snapshot = None
    if payload.input_kind == 'playlist':
        try:
            _playlist_id, url = normalize_playlist_url(payload.urls[0])
        except ValueError as error:
            raise AppError(422, 'INVALID_YOUTUBE_PLAYLIST_URL', '请输入有效的YouTube播放列表链接。') from error
        try:
            # Bound concurrent workers and total time, including time waiting for a slot.
            async with asyncio.timeout(50):
                async with request.app.state.playlist_preview_slots:
                    snapshot = await request.app.state.playlist_fetcher(url)
            if snapshot.playlist_id != _playlist_id or snapshot.url != url:
                raise PlaylistFetchError('Playlist identity mismatch')
        except PlaylistLimitError as error:
            raise AppError(422, 'IMPORT_LIMIT_EXCEEDED', '每次最多预览200条，请选择较小的播放列表。') from error
        except (PlaylistFetchError, TimeoutError, OSError) as error:
            raise AppError(502, 'PLAYLIST_FETCH_FAILED', '无法获取完整播放列表，请稍后重新获取。') from error
    # No database session is held during external extraction or subprocess waits.
    def save():
        with request.app.state.session_factory() as session:
            return make_preview(session, payload, snapshot)
    return await asyncio.to_thread(save)


@router.post('/video-import-batches', response_model=BatchResponse, status_code=202,
             responses={200: {'model': BatchResponse}})
def create_batch(payload: BatchRequest, request: Request, response: Response,
                 background_tasks: BackgroundTasks, session: DatabaseSession):
    result, reused = submit_batch(session, payload)
    response.status_code = 200 if reused else 202
    background_tasks.add_task(request.app.state.video_import_scheduler.wake)
    return result


@router.get('/video-import-batches/{batch_id}', response_model=BatchResponse)
def read_batch(batch_id: str, session: DatabaseSession):
    return get_batch(session, batch_id)


@router.post('/video-import-batches/{batch_id}/retry', response_model=RetryBatchResponse, status_code=202,
             responses={200: {'model': RetryBatchResponse}})
def retry_failed_batch(batch_id: str, payload: RetryBatchRequest, request: Request,
                       response: Response, background_tasks: BackgroundTasks, session: DatabaseSession):
    result, replayed = retry_batch(session, batch_id, payload, request.app.state.data_dir)
    response.status_code = 200 if replayed else 202
    background_tasks.add_task(request.app.state.video_import_scheduler.wake)
    return result
