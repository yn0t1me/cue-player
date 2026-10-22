from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, event

from app.core.config import Settings
from app.core.enums import JobStatus, VideoStatus
from app.db.models import (
    Video, ProcessingJob, VideoCollection, VideoCollectionItem, VideoImportPreview,
    VideoImportBatch, VideoImportBatchItem,
)
from app.main import create_app
from app.services.youtube.playlists import PlaylistEntry, PlaylistSnapshot, PlaylistFetchError, PlaylistLimitError

IDS = ['abcdefghijk', 'lmnopqrstuv', 'zyxwvutsrqp']


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "collections.db"}')
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path))) as c:
        # Persistence-only tests hold execution; scheduler behavior has separate integration tests.
        c.portal.call(c.app.state.video_import_scheduler.stop)
        yield c


def preview(client, ids=IDS):
    response = client.post('/api/video-import-previews', json={
        'input_kind': 'multiple', 'urls': [f'https://youtu.be/{i}' for i in ids]})
    assert response.status_code == 200, response.text
    return response.json()


def batch_payload(p, *, target=None, key='request-1'):
    return dict(preview_id=p['id'], selected_item_ids=[i['id'] for i in p['items'] if i['selectable']],
                target=target or {'kind': 'new', 'name': 'Lessons'}, idempotency_key=key,
                subtitle_preference='auto_only')


def submit(client, p=None, **kwargs):
    response = client.post('/api/video-import-batches', json=batch_payload(p or preview(client), **kwargs))
    assert response.status_code == 202, response.text
    return response.json()


def detail(client, cid):
    response = client.get(f'/api/collections/{cid}')
    assert response.status_code == 200, response.text
    return response.json()


def db_counts(client):
    with client.app.state.session_factory() as s:
        return [s.scalar(select(func.count()).select_from(m)) for m in (
            Video, ProcessingJob, VideoCollection, VideoCollectionItem, VideoImportBatch, VideoImportBatchItem)]


def test_preview_is_read_only_and_persistent(client):
    p = preview(client, [IDS[0], IDS[0], 'invalid'])
    assert p['duplicate_count'] == 1
    assert [i['source_position'] for i in p['items']] == [0, 2]
    assert p['items'][0]['title'] is None
    assert p['items'][1]['error']['code'] == 'INVALID_YOUTUBE_URL'
    assert not p['items'][1]['selectable']
    assert db_counts(client) == [0] * 6
    with client.app.state.session_factory() as s:
        row = s.get(VideoImportPreview, p['id'])
        assert row.items == p['items']
        assert row.expires_at > datetime.now(UTC)


def test_submit_is_atomic_idempotent_and_snapshot_bound(client):
    p = preview(client, [IDS[0], IDS[1], 'bad'])
    payload = batch_payload(p)
    payload['selected_item_ids'].reverse()
    response = client.post('/api/video-import-batches', json=payload)
    assert response.status_code == 202
    b = response.json()
    assert b['counts'] == dict(total=3, ready=0, waiting=2, running=0, failed=0, unavailable=1)
    assert [i['disposition'] for i in b['items']] == ['created', 'created', 'unavailable']
    c = detail(client, b['collection_id'])
    assert [i['video']['youtube_video_id'] for i in c['items']] == [IDS[1], IDS[0]]
    assert all(i['video']['subtitle_preference'] == 'auto_only' for i in c['items'])
    assert db_counts(client) == [2, 2, 1, 2, 1, 3]
    with client.app.state.session_factory() as s:
        s.get(VideoImportPreview, p['id']).expires_at = datetime.now(UTC) - timedelta(hours=1)
        s.commit()
    repeated = client.post('/api/video-import-batches', json=payload)
    assert repeated.status_code == 200 and repeated.json() == b
    changed = payload | {'subtitle_preference': 'manual_first'}
    assert client.post('/api/video-import-batches', json=changed).json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert db_counts(client) == [2, 2, 1, 2, 1, 3]
    assert client.get('/api/video-import-batches/' + b['id']).json() == b


def test_reuse_preserves_preference_and_multiple_memberships(client):
    p = preview(client, [IDS[0]])
    first = submit(client, p)
    payload = batch_payload(p, key='different', target={'kind': 'new', 'name': 'Other'})
    payload['subtitle_preference'] = 'manual_first'
    second = client.post('/api/video-import-batches', json=payload).json()
    assert second['items'][0]['disposition'] == 'reused'
    assert second['items'][0]['video']['subtitle_preference'] == 'auto_only'
    third = submit(client, p, key='third', target={'kind': 'existing', 'collection_id': first['collection_id']})
    assert third['items'][0]['disposition'] == 'already_member'
    assert db_counts(client) == [1, 1, 2, 2, 3, 3]


def test_collection_manage_sort_remove_delete_preserves_videos_and_batch(client):
    b = submit(client)
    cid = b['collection_id']
    c = detail(client, cid)
    changed = client.patch('/api/collections/' + cid, json={
        'name': ' New name ', 'description': 'About', 'expected_version': c['version']}).json()
    assert changed['name'] == 'New name' and changed['version'] == c['version'] + 1
    stale = client.patch('/api/collections/' + cid, json={'name': 'Stale', 'expected_version': c['version']})
    assert stale.status_code == 409
    order = [i['id'] for i in reversed(c['items'])]
    sorted_response = client.patch(f'/api/collections/{cid}/order', json={
        'item_ids': order, 'expected_version': changed['version']})
    assert sorted_response.status_code == 200, sorted_response.text
    sorted_c = sorted_response.json()
    assert [i['id'] for i in sorted_c['items']] == order
    assert [i['position'] for i in sorted_c['items']] == [0, 1, 2]
    invalid_order = client.patch(f'/api/collections/{cid}/order', json={
        'item_ids': [order[0]] * 3, 'expected_version': sorted_c['version']})
    assert invalid_order.status_code == 422
    removed = client.delete(f'/api/collections/{cid}/items/{order[1]}', params={'expected_version': sorted_c['version']})
    assert removed.status_code == 204
    current = detail(client, cid)
    assert [i['position'] for i in current['items']] == [0, 1]
    assert client.delete(f'/api/collections/{cid}', params={'expected_version': current['version']}).status_code == 204
    assert client.get('/api/collections').json() == {'items': []}
    historical = client.get('/api/video-import-batches/' + b['id']).json()
    assert historical['collection_id'] is None and historical['collection_name_snapshot'] == 'Lessons'
    assert db_counts(client) == [3, 3, 0, 0, 1, 3]


def test_add_existing_members_and_rollback_unknown_video(client):
    b = submit(client, target={'kind': 'none'})
    c = client.post('/api/collections', json={'name': 'Empty'}).json()
    cid = c['id']
    video_ids = [i['video']['id'] for i in b['items']]
    bad = client.post(f'/api/collections/{cid}/items', json={
        'video_ids': [video_ids[0], 'missing'], 'expected_version': 1})
    assert bad.status_code == 404 and detail(client, cid)['items'] == []
    added = client.post(f'/api/collections/{cid}/items', json={
        'video_ids': [video_ids[0], video_ids[0], video_ids[1]], 'expected_version': 1}).json()
    assert added['total_count'] == 2 and added['version'] == 2
    again = client.post(f'/api/collections/{cid}/items', json={
        'video_ids': video_ids[:2], 'expected_version': 2}).json()
    assert again['version'] == 2 and again['total_count'] == 2


@pytest.mark.parametrize('change,code', [
    ('expired', 'IMPORT_PREVIEW_EXPIRED'), ('foreign', 'IMPORT_SELECTION_INVALID'),
    ('duplicate', 'IMPORT_SELECTION_INVALID'), ('unavailable', 'IMPORT_SELECTION_INVALID'),
    ('missing_collection', 'COLLECTION_NOT_FOUND'), ('missing_preview', 'IMPORT_PREVIEW_NOT_FOUND'),
])
def test_invalid_batch_does_not_create_anything(client, change, code):
    p = preview(client, [IDS[0], 'bad'])
    payload = batch_payload(p)
    if change == 'expired':
        with client.app.state.session_factory() as s:
            s.get(VideoImportPreview, p['id']).expires_at = datetime.now(UTC) - timedelta(seconds=1)
            s.commit()
    elif change == 'foreign': payload['selected_item_ids'] = ['foreign']
    elif change == 'duplicate': payload['selected_item_ids'] *= 2
    elif change == 'unavailable': payload['selected_item_ids'] = [p['items'][1]['id']]
    elif change == 'missing_collection': payload['target'] = {'kind': 'existing', 'collection_id': 'missing'}
    else: payload['preview_id'] = 'missing'
    assert client.post('/api/video-import-batches', json=payload).json()['error']['code'] == code
    assert db_counts(client) == [0] * 6


def test_late_database_failure_rolls_back_entire_batch(client):
    p = preview(client)
    engine = client.app.state.session_factory.kw['bind']
    def fail(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith('INSERT INTO video_collection_items'):
            raise RuntimeError('injected late failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected late failure'):
            client.post('/api/video-import-batches', json=batch_payload(p))
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    assert db_counts(client) == [0] * 6
    assert submit(client, p)['counts']['waiting'] == 3


def test_concurrent_same_submission_has_one_batch(client):
    payload = batch_payload(preview(client))
    barrier = Barrier(2)
    def post():
        barrier.wait()
        r = client.post('/api/video-import-batches', json=payload)
        return r.status_code, r.json()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(post) for _ in range(2)]
        results = [f.result(timeout=15) for f in futures]
    assert sorted(status for status, _ in results) == [200, 202]
    assert results[0][1]['id'] == results[1][1]['id']
    assert db_counts(client) == [3, 3, 1, 3, 1, 3]


def test_concurrent_sort_rejects_stale_version(client):
    b = submit(client)
    c = detail(client, b['collection_id'])
    barrier = Barrier(2)
    def reorder(order):
        barrier.wait()
        return client.patch(f'/api/collections/{c["id"]}/order', json={
            'item_ids': order, 'expected_version': c['version']}).status_code
    ids = [i['id'] for i in c['items']]
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(reorder, order) for order in (ids[::-1], ids[1:] + ids[:1])]
        assert sorted(f.result(timeout=15) for f in futures) == [200, 409]


def test_batch_history_does_not_follow_another_created_job(client):
    b = submit(client, preview(client, [IDS[0]]))
    with client.app.state.session_factory() as s:
        item = b['items'][0]
        job = s.get(ProcessingJob, item['job']['id'])
        job.status = JobStatus.FAILED
        video = s.get(Video, item['video']['id'])
        video.status = VideoStatus.READY
        newer = ProcessingJob(video_id=video.id, stage='completed', status='completed', progress=100,
                              created_at=datetime.now(UTC) + timedelta(seconds=1))
        s.add(newer); s.commit()
    result = client.get('/api/video-import-batches/' + b['id']).json()
    assert result['counts']['failed'] == 1
    assert result['items'][0]['job']['status'] == 'failed'
    assert result['items'][0]['video']['status'] == 'ready'
    reused = submit(client, preview(client, [IDS[0]]), key='reuse', target={'kind': 'none'})
    assert reused['counts']['ready'] == 1


def test_playlist_preview_and_safe_errors(client):
    async def fetch(url):
        return PlaylistSnapshot('PLtest', url, 'Series', [
            PlaylistEntry(IDS[0], 'One', 10, None),
            PlaylistEntry(IDS[1], None, None, None, True),
            PlaylistEntry(IDS[0], 'duplicate', 10, None),
            PlaylistEntry(IDS[2], None, None, None),
        ])
    client.app.state.playlist_fetcher = fetch
    payload = {'input_kind': 'playlist', 'urls': ['https://www.youtube.com/watch?v=abcdefghijk&list=PLtest']}
    response = client.post('/api/video-import-previews', json=payload)
    assert response.status_code == 200, response.text
    p = response.json()
    assert p['source']['url'] == 'https://www.youtube.com/playlist?list=PLtest'
    assert p['duplicate_count'] == 1
    assert [i['selectable'] for i in p['items']] == [True, False, True]
    assert db_counts(client) == [0] * 6
    b = submit(client, p)
    assert b['counts']['unavailable'] == 1
    for exc, status in [(PlaylistFetchError('secret upstream'), 502), (PlaylistLimitError('limit'), 422), (TimeoutError('secret'), 502)]:
        async def fail(url): raise exc
        client.app.state.playlist_fetcher = fail
        response = client.post('/api/video-import-previews', json=payload)
        assert response.status_code == status and 'secret' not in response.text


@pytest.mark.parametrize('payload', [
    {'name': ''}, {'name': '   '}, {'name': 'x', 'extra': 1}, {'name': 'x' * 201},
])
def test_strict_collection_create(client, payload):
    assert client.post('/api/collections', json=payload).status_code == 422


@pytest.mark.parametrize('payload', [
    {'name': None, 'expected_version': 1}, {'expected_version': 1},
    {'name': 'x', 'expected_version': True}, {'description': 'x' * 2001, 'expected_version': 1},
])
def test_strict_patch(client, payload):
    c = client.post('/api/collections', json={'name': 'x'}).json()
    assert client.patch('/api/collections/' + c['id'], json=payload).status_code == 422


def test_concurrent_different_batches_share_video_identity(client):
    p = preview(client)
    c = client.post('/api/collections', json={'name': 'Shared'}).json()
    barrier = Barrier(2)
    def post(key):
        payload = batch_payload(p, key=key, target={'kind': 'existing', 'collection_id': c['id']})
        barrier.wait()
        r = client.post('/api/video-import-batches', json=payload)
        assert r.status_code == 202, r.text
        return r.json()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(post, key) for key in ('first', 'second')]
        results = [f.result(timeout=15) for f in futures]
    assert db_counts(client) == [3, 3, 1, 3, 2, 6]
    assert sorted({i['disposition'] for i in r['items']}.pop() for r in results) == ['already_member', 'created']


def test_foreign_member_and_unknown_batches_are_not_exposed(client):
    a = submit(client)
    b = client.post('/api/collections', json={'name': 'Other'}).json()
    member_id = detail(client, a['collection_id'])['items'][0]['id']
    r = client.delete(f'/api/collections/{b["id"]}/items/{member_id}', params={'expected_version': 1})
    assert r.status_code == 404
    assert detail(client, a['collection_id'])['total_count'] == 3
    assert client.get('/api/video-import-batches/unknown').status_code == 404


def test_expired_preview_can_only_replay_existing_submission(client):
    p = preview(client)
    b = submit(client, p)
    with client.app.state.session_factory() as s:
        s.get(VideoImportPreview, p['id']).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        s.commit()
    assert client.post('/api/video-import-batches', json=batch_payload(p, key='other')).status_code == 409
    assert client.get('/api/video-import-batches/' + b['id']).status_code == 200


def test_new_collection_downgrade_refuses_data_loss(client, monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "collections.db"}')
    client.post('/api/collections', json={'name': 'Preserve'})
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with pytest.raises(RuntimeError, match='Cannot downgrade'):
        command.downgrade(config, '011_bilingual_subtitles')
    assert client.get('/api/collections').json()['items'][0]['name'] == 'Preserve'
