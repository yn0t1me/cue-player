export interface ProcessingJob {
  id: string;
  stage: 'fetching_metadata' | 'fetching_captions' | 'downloading_audio' | 'transcribing' | 'normalizing' | 'completed' | 'failed';
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  error_code: string | null;
  error_message: string | null;
}

export type SubtitlePreference = 'manual_first' | 'auto_only';

export interface Video {
  id: string;
  youtube_video_id: string;
  youtube_url: string;
  title: string | null;
  channel_title: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
  status: 'processing' | 'ready' | 'failed';
  subtitle_preference: SubtitlePreference;
  subtitle_source: 'youtube_manual' | 'youtube_auto' | 'stt' | null;
  subtitle_language: string | null;
  created_at: string;
  processing: ProcessingJob | null;
}

export interface ImportVideoResponse {
  already_exists: boolean;
  video: Video;
  job: ProcessingJob | null;
}

export interface TranscriptSegment {
  id: string;
  sequence_index: number;
  start: number;
  end: number;
  text: string;
  translation_zh?: string | null;
}

export interface Transcript {
  video_id: string;
  revision_id: string;
  origin: 'generated' | 'source_aligned';
  normalization_version: number | null;
  segments: TranscriptSegment[];
}

export interface TranscriptMark {
  id: string;
  video_id: string;
  revision_id: string;
  revision_number: number;
  revision_origin: Transcript['origin'];
  is_current: boolean;
  segment_id: string;
  segment_sequence_index: number;
  segment_start: number;
  segment_end: number;
  segment_text: string;
  start_offset: number;
  end_offset: number;
  selected_text: string;
  created_at: string;
  updated_at: string;
}

export interface CreateTranscriptMark {
  revision_id: string;
  segment_id: string;
  start_offset: number;
  end_offset: number;
  selected_text: string;
}

export interface LearningCandidateSegment {
  sequence_index: number;
  start: number;
  end: number;
  text: string;
}

export interface TranscriptRevision {
  id: string;
  origin: Transcript['origin'];
  revision_number: number;
  created_at: string;
  normalization_version: number | null;
  segment_count: number;
  is_current: boolean;
}

export interface ChunkLayoutSegment {
  segment_id: string;
  sequence_index: number;
  start: number;
  end: number;
  text: string;
  boundary_offsets: number[];
  chunks: string[];
}

export interface ChunkLayout {
  id: string;
  revision_id: string;
  content_sha256: string;
  created_at: string;
  updated_at: string;
  segments: ChunkLayoutSegment[];
}

export interface ChunkLayoutState {
  video_id: string;
  revision_id: string;
  layout: ChunkLayout | null;
}

export interface LearningTranscriptCandidateSegment extends LearningCandidateSegment {
  boundary_offsets: number[];
  chunks: string[];
}

export interface LearningTranscriptPreview {
  video_id: string;
  base_revision_id: string;
  preview_digest: string;
  current_segments: TranscriptSegment[];
  segments: LearningTranscriptCandidateSegment[];
  summary: {
    current_count: number;
    candidate_count: number;
    text_changed: boolean;
    timing_changed: boolean;
    split_segment_count: number;
    chunk_count: number;
  };
  warnings: Array<{ code: string; start: number; end: number; message: string }>;
}

export interface LearningTranscriptPublishResult {
  transcript: Transcript;
  chunk_layout: ChunkLayoutState;
}

export interface LearningSource {
  format: 'learning-source-v2';
  source_type: 'youtube_manual' | 'youtube_auto';
  processing_mode: 'manual_cues' | 'auto_units';
  source_video_id: string;
  source_digest: string;
  extractor_version: string;
  units: Array<{ id: string; text: string; start_ms: number;
    time_basis: 'inline_timestamp' | 'cue_start' }>;
}

export interface SourceLearningPreview extends LearningTranscriptPreview {
  source_digest: string;
  extractor_version: string;
  segments: Array<LearningTranscriptCandidateSegment & {
    translation_zh: string | null;
    first_unit_id: string; last_unit_id: string; source_text: string;
    start_basis: 'inline_timestamp' | 'cue_start';
    end_basis: 'next_sentence_start' | 'source_cue_end';
  }>;
}

export function transcriptOriginLabel(origin: Transcript['origin']): string {
  return origin === 'source_aligned' ? '原字幕时间重建' : '初始字幕';
}
