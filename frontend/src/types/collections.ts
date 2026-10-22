import type { Video, ProcessingJob, SubtitlePreference } from './video';
export interface Collection {
  id: string; name: string; description: string | null; version: number;
  source_playlist_id: string | null; source_playlist_url: string | null;
  created_at: string; updated_at: string; thumbnail_url: string | null;
  total_count: number; ready_count: number;
}
export interface CollectionDetail extends Collection {
  items: Array<{ id: string; position: number; video: Video }>;
}
export type InputKind = 'single' | 'multiple' | 'playlist';
export interface Preview {
  id: string; expires_at: string; limits: { max_items: number; expires_in_seconds: number };
  source: { input_kind: InputKind; playlist_id: string | null; url: string | null; title: string | null };
  duplicate_count: number;
  items: Array<{ id: string; source_position: number; youtube_video_id: string | null; url: string | null;
    title: string | null; duration: number | null; thumbnail_url: string | null;
    selectable: boolean; existing_video_id: string | null; error: { code: string; message: string } | null }>;
}
export type ImportTarget = { kind: 'none' } | { kind: 'existing'; collection_id: string }
  | { kind: 'new'; name: string; description?: string | null };
export interface BatchRequest {
  preview_id: string; selected_item_ids: string[]; subtitle_preference: SubtitlePreference;
  target: ImportTarget; idempotency_key: string;
}
export interface BatchItem {
  id: string; preview_item_id: string; position: number; youtube_video_id: string | null;
  disposition: 'created' | 'reused' | 'already_member' | 'unavailable';
  video: Video | null; job: ProcessingJob | null; error: { code: string; message: string } | null;
}
export interface ImportBatch {
  id: string; preview_id: string; collection_id: string | null; collection_name_snapshot: string | null;
  subtitle_preference: SubtitlePreference; created_at: string;
  status: 'pending' | 'running' | 'completed' | 'completed_with_errors';
  counts: { total: number; ready: number; waiting: number; running: number; failed: number; unavailable: number };
  items: BatchItem[];
}
export interface BatchRetryRequest {
  item_ids: string[]; expected_job_ids: Record<string, string | null>; idempotency_key: string;
}
export interface BatchRetryResult {
  batch_id: string; items: Array<{ item_id: string; video_id: string | null; previous_job_id: string | null;
    status: 'accepted' | 'skipped' | 'rejected'; job: ProcessingJob | null; error: { code: string; message: string } | null }>;
}
