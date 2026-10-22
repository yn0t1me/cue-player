import { api } from './client';
import type { BatchRequest, BatchRetryRequest, BatchRetryResult, Collection, CollectionDetail, ImportBatch, InputKind, Preview } from '../types/collections';
import type { ProcessingJob } from '../types/video';
const path = (id: string) => `/collections/${encodeURIComponent(id)}`;
export async function getCollections(signal?: AbortSignal) {
  return (await api.get<{ items: Collection[] }>('/collections', { signal })).data;
}
export async function getCollection(id: string, signal?: AbortSignal) {
  return (await api.get<CollectionDetail>(path(id), { signal })).data;
}
export async function createCollection(name: string, description: string | null) {
  return (await api.post<CollectionDetail>('/collections', { name, description })).data;
}
export async function updateCollection(id: string, name: string, description: string | null, expected_version: number) {
  return (await api.patch<CollectionDetail>(path(id), { name, description, expected_version })).data;
}
export async function deleteCollection(id: string, expected_version: number) {
  await api.delete(path(id), { params: { expected_version } });
}
export async function addMembers(id: string, video_ids: string[], expected_version: number) {
  return (await api.post<CollectionDetail>(`${path(id)}/items`, { video_ids, expected_version })).data;
}
export async function removeMember(id: string, itemId: string, expected_version: number) {
  await api.delete(`${path(id)}/items/${encodeURIComponent(itemId)}`, { params: { expected_version } });
}
export async function reorderMembers(id: string, item_ids: string[], expected_version: number) {
  return (await api.patch<CollectionDetail>(`${path(id)}/order`, { item_ids, expected_version })).data;
}
export async function previewImport(input_kind: InputKind, urls: string[]) {
  // Playlist extraction has a server-side total budget of 50 seconds.
  return (await api.post<Preview>('/video-import-previews', { input_kind, urls }, { timeout: 60000 })).data;
}
export async function submitBatch(payload: BatchRequest) {
  return (await api.post<ImportBatch>('/video-import-batches', payload)).data;
}
export async function getBatch(id: string, signal?: AbortSignal) {
  return (await api.get<ImportBatch>(`/video-import-batches/${encodeURIComponent(id)}`, { signal })).data;
}
export async function retryBatch(id: string, payload: BatchRetryRequest) {
  return (await api.post<BatchRetryResult>(`/video-import-batches/${encodeURIComponent(id)}/retry`, payload)).data;
}
export async function retryVideo(id: string, expected_job_id: string, idempotency_key: string) {
  return (await api.post<{ video_id: string; previous_job_id: string; job: ProcessingJob }>(
    `/videos/${encodeURIComponent(id)}/retry`, { expected_job_id, idempotency_key })).data;
}
