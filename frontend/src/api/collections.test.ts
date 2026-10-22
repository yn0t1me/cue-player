import { afterEach, expect, it } from 'vitest';
import { api } from './client';
import { previewImport, deleteCollection, removeMember, reorderMembers, retryBatch, retryVideo, submitBatch } from './collections';
const original = api.defaults.adapter;
afterEach(() => { api.defaults.adapter = original; });
it('allows playlist extraction its server budget while preserving request mode', async () => {
  api.defaults.adapter = async config => {
    expect(config.timeout).toBe(60000);
    expect(JSON.parse(config.data)).toEqual({ input_kind: 'playlist', urls: ['https://youtube.com/playlist?list=PLtest'] });
    return { data: { id: 'preview' }, status: 200, statusText: 'OK', headers: {}, config };
  };
  await expect(previewImport('playlist', ['https://youtube.com/playlist?list=PLtest'])).resolves.toEqual({ id: 'preview' });
});
it('encodes collection member IDs and carries optimistic versions for destructive changes and complete order', async () => {
  const requests: unknown[] = [];
  api.defaults.adapter = async config => {
    requests.push({ url: config.url, params: config.params, data: config.data ? JSON.parse(config.data) : undefined });
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
  };
  await removeMember('c/id', 'm/id', 2); await reorderMembers('c/id', ['b', 'a'], 3); await deleteCollection('c/id', 4);
  expect(requests).toEqual([
    { url: '/collections/c%2Fid/items/m%2Fid', params: { expected_version: 2 }, data: undefined },
    { url: '/collections/c%2Fid/order', params: undefined, data: { item_ids: ['b', 'a'], expected_version: 3 } },
    { url: '/collections/c%2Fid', params: { expected_version: 4 }, data: undefined },
  ]);
});
it('sends acceptance intent and expected job binding without changing source preferences on retry', async () => {
  const requests: unknown[] = [];
  api.defaults.adapter = async config => {
    requests.push({ url: config.url, data: JSON.parse(config.data) });
    return { data: {}, status: 202, statusText: 'Accepted', headers: {}, config };
  };
  const payload = { preview_id: 'p', selected_item_ids: ['b', 'a'], subtitle_preference: 'auto_only' as const,
    target: { kind: 'none' as const }, idempotency_key: 'submit-key' };
  await submitBatch(payload); await retryVideo('v/id', 'old-job', 'retry-key');
  const retry = { item_ids: ['item'], expected_job_ids: { item: 'bound-job' }, idempotency_key: 'batch-retry-key' };
  await retryBatch('b/id', retry);
  expect(requests).toEqual([{ url: '/video-import-batches', data: payload },
    { url: '/videos/v%2Fid/retry', data: { expected_job_id: 'old-job', idempotency_key: 'retry-key' } },
    { url: '/video-import-batches/b%2Fid/retry', data: retry }]);
});
