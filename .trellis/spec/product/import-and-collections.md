# Import and Collections

Status: current behavior, updated 2026-10-21. Collections, batch import and bounded failed-import retry are the effective product scope. Input normalization, default preference and ordering mechanics are engineering baselines, not individual user field approvals.

## Import and Source Selection

Support single video links, multiple video links (one per line), and a YouTube playlist. A link containing both video and playlist identity offers an explicit choice of one video or the playlist. Multi-link input preserves first-occurrence order and removes duplicate videos; playlist preview preserves source order and permits selection/reordering. One preview uses one input mode; multiple playlist expansion in a multi-link list is outside the current workflow. The current engineering limit is 200 entries; oversized playlists must be rejected rather than silently truncated.

Before confirmation, show new/existing entries and invalid/unavailable reasons. Unavailable entries cannot be selected; missing metadata uses an identifier/placeholder rather than an invented title. Cancelling preview does not create videos, processing jobs or collections; temporary preview persistence is not a submitted batch.

Subtitle preference is manual-first (engineering default) or automatic. Manual-first selects eligible manual English captions, then eligible automatic English captions; automatic preference does not select manual captions. When discovery succeeds with no eligible preferred source, use local STT. Discovery/download failures remain failures instead of being misrepresented as absent captions. The actual source, not the requested preference, determines later subtitle processing.

Duplicate imports open/reuse the same video and preserve saved preference, Raw and source. They neither switch source nor retry a failure. A batch applies its preference only to new videos. Single-video shortcut enters its detail view; batch flow reviews selection/order/destination before submission and then shows collection/batch progress.

## Collections and Batches

Collections support create, rename, description edits, adding existing videos, ordering, removal and deletion. Names may repeat. One video can belong to multiple collections; a collection contains it once. Episode numbers are positions, not video identities. Reimporting an existing member does not reorder it. New members append to an existing collection; deleting a collection/member preserves the videos, subtitles and notes.

Batch destinations are library only, a new collection or an existing collection; a collection is not mandatory. A batch records one submission and counts ready/processing/waiting/failed outcomes, with unavailable preview entries separate. Do not turn aggregate stage percentages into an ETA. Processing is serial; one item failure does not block the others. Closing the page does not cancel backend processing; refresh reads persisted progress. Restart recovery does not promise that every interrupted job will resume.

## Retry and Viewing

Explicit single/batch retry is available for eligible failed first imports, creates a new job and preserves the failed attempt/source evidence. Pending/running, already-ready/published, or inconsistent data are not blindly restarted. Retry is separate from source switching or Reprocess.

The library offers collections and all videos; collection membership does not hide a video from all videos. A collection view has ordered entries and status. Opening through a collection preserves that viewing context and provides a collapsible episode directory plus previous/next navigation. Opening independently does not select a collection automatically. Episode switching starts the new video at its beginning for manual playback; collapsing the directory does not rebuild the current player. Draft protection and old-player cleanup apply across navigation. Missing collection context does not make a saved video inaccessible.

## Source and Verification References

- `frontend/src/features/collections/ImportPanel.tsx`, `frontend/src/pages/LibraryPage.tsx`, `CollectionPage.tsx`, `ImportBatchPage.tsx`, and `frontend/src/features/collections/EpisodeDirectory.tsx` implement the visible flows.
- `backend/app/services/youtube/captions.py::select_best_caption`, `services/processing/video_import.py`, `services/video_collections.py` and `services/import_retries.py` establish source choice and persistent operations (services/ paths are under backend/app).
- `backend/tests/test_video_api.py` covers duplicates and failures; `test_video_collections_api.py`, `test_import_retries.py` and `test_import_scheduler.py` cover collection identity, retry and recovery. `frontend/src/features/collections/Collections.test.tsx` covers UI behavior. These are source references, not a claim that the tests were executed during documentation work.
