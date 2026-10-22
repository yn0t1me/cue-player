import { api } from './client';
import type {
  LearningSource,
  SourceLearningPreview,
  ImportVideoResponse,
  ChunkLayoutState,
  CreateTranscriptMark,
  LearningTranscriptPublishResult,
  Transcript,
  TranscriptMark,
  TranscriptQuestion,
  TranscriptRevision,
  Video, SubtitlePreference,
} from '../types/video';

export async function importVideo(url: string, subtitlePreference: SubtitlePreference = 'manual_first'): Promise<ImportVideoResponse> {
  return (await api.post<ImportVideoResponse>('/videos', { url, subtitle_preference: subtitlePreference })).data;
}

export async function getVideos(signal?: AbortSignal): Promise<{ items: Video[] }> {
  return (await api.get<{ items: Video[] }>('/videos', { signal })).data;
}

export async function getVideo(id: string, signal?: AbortSignal): Promise<Video> {
  return (await api.get<Video>(`/videos/${encodeURIComponent(id)}`, { signal })).data;
}

export async function getTranscript(id: string, signal?: AbortSignal): Promise<Transcript> {
  return (await api.get<Transcript>(`/videos/${encodeURIComponent(id)}/transcript`, { signal })).data;
}

export async function getTranscriptMarks(
  id: string, signal?: AbortSignal,
): Promise<{ items: TranscriptMark[] }> {
  return (await api.get<{ items: TranscriptMark[] }>(
    `/videos/${encodeURIComponent(id)}/marks`, { signal })).data;
}

export async function getTranscriptQuestions(
  id: string, signal?: AbortSignal,
): Promise<{ items: TranscriptQuestion[] }> {
  return (await api.get<{ items: TranscriptQuestion[] }>(
    `/videos/${encodeURIComponent(id)}/questions`, { signal })).data;
}

export async function createTranscriptFavorite(id: string, payload: CreateTranscriptMark) {
  const response = await api.post<TranscriptMark>(`/videos/${encodeURIComponent(id)}/marks`, payload);
  return { item: response.data, created: response.status === 201 };
}

export async function createTranscriptQuestion(id: string, anchor: CreateTranscriptMark,
  question: string, answer: string | null): Promise<TranscriptQuestion> {
  return (await api.post<TranscriptQuestion>(`/videos/${encodeURIComponent(id)}/questions`,
    { ...anchor, question, answer })).data;
}

export async function updateTranscriptQuestion(id: string, questionId: string,
  patch: { question?: string; answer?: string | null }): Promise<TranscriptQuestion> {
  return (await api.patch<TranscriptQuestion>(
    `/videos/${encodeURIComponent(id)}/questions/${encodeURIComponent(questionId)}`, patch)).data;
}

export async function updateTranscriptMarkNote(
  id: string, markId: string, note: string | null,
): Promise<TranscriptMark> {
  return (await api.patch<TranscriptMark>(
    `/videos/${encodeURIComponent(id)}/marks/${encodeURIComponent(markId)}`, { note })).data;
}

export async function deleteTranscriptMark(id: string, markId: string): Promise<void> {
  await api.delete(`/videos/${encodeURIComponent(id)}/marks/${encodeURIComponent(markId)}`);
}

export async function deleteTranscriptQuestion(id: string, questionId: string): Promise<void> {
  await api.delete(`/videos/${encodeURIComponent(id)}/questions/${encodeURIComponent(questionId)}`);
}

export async function getRawSrt(id: string): Promise<string> {
  return (await api.get<string>(`/videos/${encodeURIComponent(id)}/transcript/export.srt`,
    { responseType: 'text' })).data;
}

export async function getTranscriptRevisions(
  id: string, signal?: AbortSignal,
): Promise<{ items: TranscriptRevision[] }> {
  return (await api.get<{ items: TranscriptRevision[] }>(
    `/videos/${encodeURIComponent(id)}/transcript/revisions`, { signal })).data;
}

export async function getTranscriptRevision(
  id: string, revisionId: string, signal?: AbortSignal,
): Promise<Transcript> {
  return (await api.get<Transcript>(
    `/videos/${encodeURIComponent(id)}/transcript/revisions/${encodeURIComponent(revisionId)}`,
    { signal })).data;
}

export async function getChunkLayout(
  id: string, signal?: AbortSignal,
): Promise<ChunkLayoutState> {
  return (await api.get<ChunkLayoutState>(
    `/videos/${encodeURIComponent(id)}/transcript/chunk-layout`, { signal })).data;
}

export async function getLearningSource(id: string, signal?: AbortSignal): Promise<LearningSource> {
  return (await api.get<LearningSource>(
    `/videos/${encodeURIComponent(id)}/transcript/learning-source`, { signal })).data;
}

export async function previewSourceLearning(id: string, result: string): Promise<SourceLearningPreview> {
  return (await api.post<SourceLearningPreview>(
    `/videos/${encodeURIComponent(id)}/transcript/source-learning/preview`, { result })).data;
}

export async function publishSourceLearning(id: string, result: string,
  expectedRevisionId: string, previewDigest: string): Promise<LearningTranscriptPublishResult> {
  return (await api.post<LearningTranscriptPublishResult>(
    `/videos/${encodeURIComponent(id)}/transcript/source-learning`, {
      result, expected_revision_id: expectedRevisionId, preview_digest: previewDigest,
    })).data;
}

export async function getLearningSrt(id: string): Promise<string> {
  return (await api.get<string>(`/videos/${encodeURIComponent(id)}/transcript/learning-export.srt`,
    { responseType: 'text' })).data;
}
