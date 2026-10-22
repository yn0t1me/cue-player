import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.processing.audio_acquisition import AudioAcquirer
from app.services.processing.audio_store import AudioDownloadTarget, AudioStore
from app.services.youtube.audio import AudioDownloadError, DownloadedAudio


def test_store_uses_internal_uuid_and_atomically_hands_off_actual_extension(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())
    target = store.prepare(video_id)
    downloaded = target.directory / 'source.webm'
    downloaded.write_bytes(b'valid audio bytes')

    artifact = store.finalize(video_id, target, downloaded)

    assert artifact.path == tmp_path / 'videos' / video_id / 'audio' / 'source.webm'
    assert artifact.path.read_bytes() == b'valid audio bytes'
    assert (artifact.extension, artifact.size_bytes) == ('webm', 17)
    assert not target.directory.exists()
    assert store.load(video_id) == artifact


@pytest.mark.parametrize('video_id', ['../outside', 'BaW_jenozKc', str(uuid4()).upper()])
def test_store_rejects_noncanonical_internal_video_ids(tmp_path, video_id):
    with pytest.raises(ValueError, match='internal video id'):
        AudioStore(tmp_path).prepare(video_id)


def test_store_rejects_escape_empty_missing_and_unexpected_files(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())
    target = store.prepare(video_id)
    outside = tmp_path / 'outside.webm'
    outside.write_bytes(b'audio')
    with pytest.raises(ValueError, match='outside'):
        store.finalize(video_id, target, outside)

    empty = target.directory / 'source.webm'
    empty.touch()
    with pytest.raises(ValueError, match='empty'):
        store.finalize(video_id, target, empty)
    empty.unlink()
    with pytest.raises(FileNotFoundError):
        store.finalize(video_id, target, target.directory / 'source.m4a')

    unexpected = target.directory / 'third-party-title.webm'
    unexpected.write_bytes(b'audio')
    with pytest.raises(ValueError, match='unexpected name'):
        store.finalize(video_id, target, unexpected)


def test_store_rejects_forged_target_and_symlinked_video_directory(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())
    target = store.prepare(video_id)
    forged = AudioDownloadTarget(video_id, target.token, tmp_path, tmp_path / 'source.%(ext)s')
    with pytest.raises(ValueError, match='does not belong'):
        store.discard(video_id, forged)

    other_root = tmp_path / 'outside'
    other_root.mkdir()
    linked_id = str(uuid4())
    videos = tmp_path / 'videos'
    (videos / linked_id).symlink_to(other_root, target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic link'):
        store.prepare(linked_id)


def test_store_rejects_audio_directory_linked_to_another_video(tmp_path):
    store = AudioStore(tmp_path)
    first_id = str(uuid4())
    second_id = str(uuid4())
    second_audio = tmp_path / 'videos' / second_id / 'audio'
    second_audio.mkdir(parents=True)
    first_video = tmp_path / 'videos' / first_id
    first_video.mkdir()
    (first_video / 'audio').symlink_to(second_audio, target_is_directory=True)

    with pytest.raises(ValueError, match='symbolic link'):
        store.prepare(first_id)


def test_cleanup_is_idempotent_and_preserves_unmanaged_and_other_video_files(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())
    other_id = str(uuid4())
    target = store.prepare(video_id)
    (target.directory / 'source.webm.part').write_bytes(b'partial')
    audio_dir = store.audio_dir_for(video_id)
    (audio_dir / 'source.m4a').write_bytes(b'audio')
    (audio_dir / 'notes.txt').write_text('keep')
    other = store.audio_dir_for(other_id)
    other.mkdir(parents=True)
    (other / 'source.webm').write_bytes(b'other audio')

    store.cleanup(video_id)
    store.cleanup(video_id)

    assert (audio_dir / 'notes.txt').read_text() == 'keep'
    assert not (audio_dir / 'source.m4a').exists()
    assert not target.directory.exists()
    assert (other / 'source.webm').read_bytes() == b'other audio'


def test_load_rejects_missing_empty_or_ambiguous_managed_audio(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())
    with pytest.raises(FileNotFoundError):
        store.load(video_id)
    audio_dir = store.audio_dir_for(video_id)
    audio_dir.mkdir(parents=True)
    (audio_dir / 'source.webm').touch()
    with pytest.raises(ValueError, match='empty'):
        store.load(video_id)
    (audio_dir / 'source.webm').write_bytes(b'audio')
    (audio_dir / 'source.m4a').write_bytes(b'audio')
    with pytest.raises(ValueError, match='Multiple'):
        store.load(video_id)


def test_startup_cleanup_removes_only_stale_staging_for_valid_video_ids(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())
    target = store.prepare(video_id)
    (target.directory / 'source.webm.part').write_bytes(b'partial')
    audio_dir = store.audio_dir_for(video_id)
    (audio_dir / 'source.webm').write_bytes(b'handed off')
    (audio_dir / '.download-not-a-uuid').mkdir()
    invalid = tmp_path / 'videos/not-a-video/audio' / f'.download-{uuid4()}'
    invalid.mkdir(parents=True)

    assert store.cleanup_stale_staging() == 1
    assert not target.directory.exists()
    assert (audio_dir / 'source.webm').read_bytes() == b'handed off'
    assert (audio_dir / '.download-not-a-uuid').is_dir()
    assert invalid.is_dir()


def test_acquirer_cleans_staging_after_failure_and_cancellation(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())

    async def fail(_url, output_template):
        output_template.parent.joinpath('source.webm.part').write_bytes(b'partial')
        raise AudioDownloadError('failed')

    with pytest.raises(AudioDownloadError):
        asyncio.run(AudioAcquirer(store, fail).acquire(video_id, 'https://youtube.test/video'))
    assert not store.audio_dir_for(video_id).exists()

    started = asyncio.Event()

    async def wait_forever(_url, output_template):
        output_template.parent.joinpath('source.webm.part').write_bytes(b'partial')
        started.set()
        await asyncio.Future()

    async def cancel():
        task = asyncio.create_task(
            AudioAcquirer(store, wait_forever).acquire(video_id, 'https://youtube.test/video'))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert not store.audio_dir_for(video_id).exists()


def test_acquirer_returns_artifact_and_cleanup_removes_it(tmp_path):
    store = AudioStore(tmp_path)
    video_id = str(uuid4())

    async def download(_url, output_template):
        path = Path(str(output_template).replace('%(ext)s', 'm4a'))
        path.write_bytes(b'audio')
        return DownloadedAudio(path, 'm4a', '140', 'mp4a.40.2')

    artifact = asyncio.run(
        AudioAcquirer(store, download).acquire(video_id, 'https://youtube.test/video'))
    assert artifact.path.exists()
    store.cleanup(video_id)
    store.cleanup(video_id)
    assert not artifact.path.exists()
