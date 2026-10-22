from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Video, VideoCollection, VideoCollectionItem
from app.repositories.videos import VideoRepository
from app.schemas.video_collections import (
    CollectionCreate, CollectionPatch, CollectionDetailResponse, CollectionMemberResponse,
    CollectionResponse,
)
from app.services.videos import video_response


def acquire_import_write_lock(session: Session) -> None:
    """Acquire SQLite's writer before any read; prevents read-to-write deadlocks.

    A no-row UPDATE obtains the writer reservation without touching user rows.
    Collection writes and batch submission share the same transaction boundary.
    """
    session.execute(update(VideoCollection).where(VideoCollection.id == '').values(
        version=VideoCollection.version))


def require_collection(session: Session, collection_id: str) -> VideoCollection:
    collection = session.get(VideoCollection, collection_id)
    if collection is None:
        raise AppError(404, 'COLLECTION_NOT_FOUND', '找不到这个合集。')
    return collection


def check_version(collection: VideoCollection, expected_version: int) -> None:
    if collection.version != expected_version:
        raise AppError(409, 'COLLECTION_VERSION_CONFLICT', '合集已变化，请刷新后再操作。')


def collection_items(session: Session, collection_id: str) -> list[VideoCollectionItem]:
    return list(session.scalars(select(VideoCollectionItem).where(
        VideoCollectionItem.collection_id == collection_id).order_by(VideoCollectionItem.position)))


def touch_collection(collection: VideoCollection) -> None:
    collection.version += 1
    collection.updated_at = datetime.now(UTC)


def append_members(session: Session, collection: VideoCollection, video_ids: list[str]) -> set[str]:
    members = collection_items(session, collection.id)
    known = {m.video_id for m in members}
    position = max((m.position for m in members), default=-1) + 1
    added = set()
    for video_id in dict.fromkeys(video_ids):
        if video_id in known:
            continue
        if session.get(Video, video_id) is None:
            raise AppError(404, 'VIDEO_NOT_FOUND', '找不到要加入合集的视频。')
        session.add(VideoCollectionItem(collection_id=collection.id, video_id=video_id, position=position))
        known.add(video_id)
        added.add(video_id)
        position += 1
    if added:
        touch_collection(collection)
        session.flush()
    return added


def collection_response(session: Session, collection: VideoCollection, *, detail=False):
    members = collection_items(session, collection.id)
    repository = VideoRepository(session)
    videos = [repository.get(m.video_id) for m in members]
    summary = CollectionResponse.model_validate(collection)
    summary.total_count = len(members)
    summary.ready_count = sum(v.status == 'ready' for v in videos)
    summary.thumbnail_url = next((v.thumbnail_url for v in videos if v.thumbnail_url), None)
    if not detail:
        return summary
    return CollectionDetailResponse(**summary.model_dump(), items=[
        CollectionMemberResponse(id=m.id, position=i,
                                 video=video_response(v, repository.get_latest_job(v.id)))
        for i, (m, v) in enumerate(zip(members, videos))])


def list_collections(session: Session):
    return [collection_response(session, c) for c in session.scalars(select(VideoCollection).order_by(
        VideoCollection.updated_at.desc(), VideoCollection.id.desc()))]


def create_collection(session: Session, payload: CollectionCreate):
    with session.begin():
        collection = VideoCollection(**payload.model_dump())
        session.add(collection)
        session.flush()
        result = collection_response(session, collection, detail=True)
    return result


def patch_collection(session: Session, collection_id: str, payload: CollectionPatch):
    with session.begin():
        acquire_import_write_lock(session)
        collection = require_collection(session, collection_id)
        check_version(collection, payload.expected_version)
        for field in payload.model_fields_set - {'expected_version'}:
            setattr(collection, field, getattr(payload, field))
        touch_collection(collection)
        session.flush()
        result = collection_response(session, collection, detail=True)
    return result


def delete_collection(session: Session, collection_id: str, version: int):
    with session.begin():
        acquire_import_write_lock(session)
        collection = require_collection(session, collection_id)
        check_version(collection, version)
        session.delete(collection)


def add_members(session: Session, collection_id: str, video_ids: list[str], version: int):
    with session.begin():
        acquire_import_write_lock(session)
        collection = require_collection(session, collection_id)
        check_version(collection, version)
        append_members(session, collection, video_ids)
        result = collection_response(session, collection, detail=True)
    return result


def set_member_order(session: Session, members: list[VideoCollectionItem], ordered_ids: list[str]):
    by_id = {m.id: m for m in members}
    if len(ordered_ids) != len(members) or set(ordered_ids) != set(by_id):
        raise AppError(422, 'IMPORT_SELECTION_INVALID', '请提交完整且不重复的合集目录。')
    # Move above the existing range before swapping unique positions.
    offset = max((m.position for m in members), default=-1) + 1
    for i, member in enumerate(members):
        member.position = offset + i
    session.flush()
    for i, item_id in enumerate(ordered_ids):
        by_id[item_id].position = i
    session.flush()


def reorder_members(session: Session, collection_id: str, item_ids: list[str], version: int):
    with session.begin():
        acquire_import_write_lock(session)
        collection = require_collection(session, collection_id)
        check_version(collection, version)
        set_member_order(session, collection_items(session, collection_id), item_ids)
        touch_collection(collection)
        session.flush()
        result = collection_response(session, collection, detail=True)
    return result


def remove_member(session: Session, collection_id: str, item_id: str, version: int):
    with session.begin():
        acquire_import_write_lock(session)
        collection = require_collection(session, collection_id)
        check_version(collection, version)
        members = collection_items(session, collection_id)
        if item_id not in {m.id for m in members}:
            raise AppError(404, 'COLLECTION_ITEM_NOT_FOUND', '找不到这个合集中的视频。')
        session.execute(delete(VideoCollectionItem).where(VideoCollectionItem.id == item_id))
        remaining = [m for m in members if m.id != item_id]
        set_member_order(session, remaining, [m.id for m in remaining])
        touch_collection(collection)
