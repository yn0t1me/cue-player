// @vitest-environment jsdom
import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as service from '../../api/collections';
import { getVideos } from '../../api/videos';
import { ApiError } from '../../api/client';
import ImportPanel from './ImportPanel';
import CollectionPage from '../../pages/CollectionPage';
import ImportBatchPage from '../../pages/ImportBatchPage';
import RetryVideoButton from './RetryVideoButton';
import type { Preview, CollectionDetail, ImportBatch } from '../../types/collections';
import type { Video } from '../../types/video';
import { IntentKey, batchItemLabel, moveItem } from './shared';
vi.mock('../../api/collections', () => ({ getCollections: vi.fn(), previewImport: vi.fn(), submitBatch: vi.fn(),
  getCollection: vi.fn(), updateCollection: vi.fn(), addMembers: vi.fn(), removeMember: vi.fn(), reorderMembers: vi.fn(),
  deleteCollection: vi.fn(), getBatch: vi.fn(), retryBatch: vi.fn(), retryVideo: vi.fn(), createCollection: vi.fn() }));
vi.mock('../../api/videos', () => ({ getVideos: vi.fn(), importVideo: vi.fn() }));
const video: Video = { id: 'v1', youtube_video_id: 'abcdefghijk', youtube_url: 'https://youtu.be/abcdefghijk',
  title: 'Lesson one', channel_title: 'Teacher', duration_seconds: 30, thumbnail_url: null, status: 'ready',
  subtitle_preference: 'manual_first', subtitle_source: 'youtube_manual', subtitle_language: 'en', created_at: '', processing: null };
const collection: CollectionDetail = { id: 'c1', name: 'English course', description: null, version: 3, source_playlist_id: null,
  source_playlist_url: null, created_at: '', updated_at: '', thumbnail_url: null, total_count: 2, ready_count: 2,
  items: [{ id: 'm1', position: 0, video }, { id: 'm2', position: 1, video: { ...video, id: 'v2', title: 'Lesson two' } }] };
const preview: Preview = { id: 'p1', expires_at: '2099-01-01T00:00:00Z', limits: { max_items: 200, expires_in_seconds: 1800 },
  source: { input_kind: 'multiple', title: null, playlist_id: null, url: null }, duplicate_count: 1,
  items: [{ id: 'a', source_position: 0, youtube_video_id: 'abcdefghijk', title: null, url: null, duration: null, thumbnail_url: null,
    selectable: true, existing_video_id: 'v1', error: null },
  { id: 'b', source_position: 1, youtube_video_id: 'lmnopqrstuv', title: 'New lesson', url: null, duration: null, thumbnail_url: null,
    selectable: true, existing_video_id: null, error: null },
  { id: 'bad', source_position: 3, youtube_video_id: null, title: null, url: null, duration: null, thumbnail_url: null,
    selectable: false, existing_video_id: null, error: { code: 'INVALID', message: '链接无效' } }] };
const failedJob = { id: 'old-job', stage: 'failed' as const, status: 'failed' as const, progress: 0, error_code: 'FAIL', error_message: '无法获取视频信息' };
const batch: ImportBatch = { id: 'b1', preview_id: 'p1', collection_id: 'c1', collection_name_snapshot: 'English course',
  subtitle_preference: 'manual_first', created_at: '', status: 'completed_with_errors',
  counts: { total: 1, ready: 0, failed: 1, waiting: 0, running: 0, unavailable: 0 }, items: [
    { id: 'item1', preview_item_id: 'a', position: 0, youtube_video_id: video.youtube_video_id, disposition: 'created',
      video: { ...video, status: 'ready', processing: { ...failedJob, id: 'new-job', status: 'completed', stage: 'completed' } }, job: failedJob, error: null }] };
let root: Root, container: HTMLDivElement, client: QueryClient;
beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.mocked(service.getCollections).mockResolvedValue({ items: [collection] });
  vi.mocked(service.previewImport).mockResolvedValue(preview);
  vi.mocked(service.getCollection).mockResolvedValue(collection);
  vi.mocked(service.getBatch).mockResolvedValue(batch);
  vi.mocked(getVideos).mockResolvedValue({ items: [video, { ...video, id: 'v3', title: 'Other' }] });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); client.clear(); vi.resetAllMocks(); });
function Destination() { return <p data-destination>{useLocation().pathname}</p>; }
async function render(element: ReactNode, entry = '/') {
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><Routes>
    <Route path="/" element={element} /><Route path="/collections/:id" element={entry.startsWith('/collections') ? element : <Destination />} />
    <Route path="/imports/:batchId" element={entry.startsWith('/imports') ? element : <Destination />} />
  </Routes></MemoryRouter></QueryClientProvider>));
}
async function click(text: string) {
  await act(async () => [...container.querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent?.includes(text))!.click());
}
async function fill(selector: string, value: string) {
  const element = container.querySelector(selector)!;
  await act(async () => {
    const prototype = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, value);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
async function select(index: number, value: string) {
  await act(async () => { const element = container.querySelectorAll('select')[index]; element.value = value; element.dispatchEvent(new Event('change', { bubbles: true })); });
}
async function parse() {
  await click('多个链接'); await fill('#batch-links', 'https://youtu.be/abcdefghijk\nhttps://youtu.be/lmnopqrstuv\nwrong');
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(container.querySelector('.import-preview')).not.toBeNull());
}
it('previews invalid and duplicate items, submits the chosen order and existing target, preserves key after lost response', async () => {
  vi.mocked(service.submitBatch).mockRejectedValueOnce(new Error('响应丢失')).mockResolvedValueOnce(batch);
  await render(<ImportPanel />); await parse();
  expect(service.previewImport).toHaveBeenCalledWith('multiple', ['https://youtu.be/abcdefghijk', 'https://youtu.be/lmnopqrstuv', 'wrong']);
  expect(container.textContent).toContain('重复 1 条已合并'); expect(container.textContent).toContain('链接无效');
  expect(container.querySelectorAll<HTMLInputElement>('.preview-list input')[2].disabled).toBe(true);
  await act(async () => (container.querySelector('[aria-label="上移第2项"]') as HTMLButtonElement).click());
  await select(0, 'auto_only'); await select(1, 'c1');
  await click('确认导入'); await vi.waitFor(() => expect(container.textContent).toContain('响应丢失'));
  await click('确认导入'); await vi.waitFor(() => expect(container.querySelector('[data-destination]')?.textContent).toBe('/imports/b1'));
  const requests = vi.mocked(service.submitBatch).mock.calls.map(call => call[0]);
  expect(requests[0]).toMatchObject({ selected_item_ids: ['b', 'a'], subtitle_preference: 'auto_only', target: { kind: 'existing', collection_id: 'c1' } });
  expect(requests[0]).toEqual(requests[1]);
});
it('does not submit empty selection, creates a new collection only at confirmation, cancel is read-only', async () => {
  await render(<ImportPanel />); await parse(); await click('取消全选');
  expect([...container.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent === '确认导入')!.disabled).toBe(true);
  await click('全选可导入项'); await select(1, 'new'); await fill('.collection-fields input', ' My course ');
  vi.mocked(service.submitBatch).mockResolvedValue(batch);
  await click('确认导入'); await vi.waitFor(() => expect(service.submitBatch).toHaveBeenCalledOnce());
  expect(vi.mocked(service.submitBatch).mock.calls[0][0].target).toEqual({ kind: 'new', name: 'My course', description: null });
  expect(service.createCollection).not.toHaveBeenCalled();
});
it('cancels a preview without creating a batch or collection', async () => {
  await render(<ImportPanel />); await parse(); await click('取消预览');
  expect(container.querySelector('.import-preview')).toBeNull(); expect(service.submitBatch).not.toHaveBeenCalled(); expect(service.createCollection).not.toHaveBeenCalled();
});
it.each(['single', 'playlist'] as const)('requires explicit scope for a mixed link and previews %s from a collection', async scope => {
  await render(<ImportPanel collectionId="c1" />);
  await fill('#batch-links', 'https://www.youtube.com/watch?v=abcdefghijk&list=PLcourse');
  expect([...container.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent === '解析预览')!.disabled).toBe(true);
  await act(async () => (container.querySelectorAll<HTMLInputElement>('[name=batch-scope]')[scope === 'single' ? 0 : 1]).click());
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(service.previewImport).toHaveBeenCalledWith(scope, expect.any(Array)));
  await vi.waitFor(() => expect(container.querySelectorAll('select')[1].value).toBe('c1'));
});
it('shows an empty playlist without enabling confirmation', async () => {
  vi.mocked(service.previewImport).mockResolvedValue({ ...preview, items: [] });
  await render(<ImportPanel />); await parse(); expect(container.textContent).toContain('列表为空');
  expect([...container.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent === '确认导入')!.disabled).toBe(true);
});
it('keeps failed preview input available for correction', async () => {
  vi.mocked(service.previewImport).mockRejectedValue(new ApiError('超过200条', 422, 'IMPORT_LIMIT_EXCEEDED'));
  await render(<ImportPanel />); await click('播放列表'); await fill('#batch-links', 'https://youtube.com/playlist?list=PLtest');
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(container.textContent).toContain('超过200条')); expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toContain('PLtest');
});
it('refreshes a collection version conflict without silently resubmitting stale order', async () => {
  vi.mocked(service.reorderMembers).mockRejectedValue(new ApiError('目录已变化', 409, 'COLLECTION_VERSION_CONFLICT'));
  await render(<CollectionPage />, '/collections/c1'); await vi.waitFor(() => expect(container.querySelectorAll('.episode-list li')).toHaveLength(2));
  await act(async () => (container.querySelector('[aria-label="下移第1集"]') as HTMLButtonElement).click());
  await vi.waitFor(() => expect(container.textContent).toContain('已重新读取目录'));
  expect(service.reorderMembers).toHaveBeenCalledExactlyOnceWith('c1', ['m2', 'm1'], 3);
  expect(service.getCollection).toHaveBeenCalledTimes(2);
});
it('edits collection metadata and adds only videos outside its existing members', async () => {
  vi.mocked(service.updateCollection).mockResolvedValue(collection); vi.mocked(service.addMembers).mockResolvedValue(collection);
  await render(<CollectionPage />, '/collections/c1'); await vi.waitFor(() => expect(container.querySelector('h1')).not.toBeNull());
  await click('编辑合集'); await fill('.collection-fields input', 'Renamed');
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(service.updateCollection).toHaveBeenCalledWith('c1', 'Renamed', null, 3));
  await click('加入已有视频'); await vi.waitFor(() => expect(container.querySelectorAll('.existing-videos input')).toHaveLength(1));
  await act(async () => (container.querySelector('.existing-videos input') as HTMLInputElement).click()); await click('加入所选');
  await vi.waitFor(() => expect(service.addMembers).toHaveBeenCalledWith('c1', ['v3'], 3));
});
it('removes a member and confirms collection deletion without calling any video deletion', async () => {
  vi.mocked(service.removeMember).mockResolvedValue(); vi.mocked(service.deleteCollection).mockResolvedValue();
  await render(<CollectionPage />, '/collections/c1'); await vi.waitFor(() => expect(container.querySelectorAll('.episode-list li')).toHaveLength(2));
  await act(async () => (container.querySelector('[aria-label="移出第1集"]') as HTMLButtonElement).click());
  await vi.waitFor(() => expect(service.removeMember).toHaveBeenCalledWith('c1', 'm1', 3));
  await click('删除合集'); expect(service.deleteCollection).not.toHaveBeenCalled(); expect(container.textContent).toContain('视频、字幕与笔记会保留');
  await click('确认删除合集'); await vi.waitFor(() => expect(service.deleteCollection).toHaveBeenCalledWith('c1', 3));
});
it('shows historical failures separately from ready video state and reports per-item retry rejection', async () => {
  vi.mocked(service.retryBatch).mockResolvedValue({ batch_id: 'b1', items: [{ item_id: 'item1', video_id: 'v1', previous_job_id: 'old-job', status: 'rejected', job: null,
    error: { code: 'VIDEO_RETRY_CONFLICT', message: '最新任务已变化' } }] });
  await render(<ImportBatchPage />, '/imports/b1'); await vi.waitFor(() => expect(container.textContent).toContain('本次处理失败'));
  expect(container.textContent).toContain('视频当前已就绪'); expect(container.textContent).toContain('无法获取视频信息');
  await click('重试全部'); await vi.waitFor(() => expect(container.textContent).toContain('最新任务已变化'));
  expect(vi.mocked(service.retryBatch).mock.calls[0]).toEqual(['b1', { item_ids: ['item1'], expected_job_ids: { item1: 'old-job' }, idempotency_key: expect.any(String) }]);
});
it('retains the single retry key across connection failures and refreshes actual progress', async () => {
  vi.mocked(service.retryVideo).mockRejectedValueOnce(new Error('离线')).mockResolvedValueOnce({ video_id: 'v1', previous_job_id: 'old-job', job: { ...failedJob, id: 'retry', status: 'pending', stage: 'fetching_metadata' } });
  await render(<RetryVideoButton videoId="v1" jobId="old-job" />); await click('重试导入'); await vi.waitFor(() => expect(container.textContent).toContain('离线'));
  await click('重试导入'); await vi.waitFor(() => expect(container.textContent).toContain('重试已接受'));
  expect(vi.mocked(service.retryVideo).mock.calls[0]).toEqual(vi.mocked(service.retryVideo).mock.calls[1]);
});
it('keeps intent keys for revisited payloads, ordering boundaries and bound task semantics', () => {
  const keys = new IntentKey(), a = keys.for({ items: ['a'] });
  expect(keys.for({ items: ['b'] })).not.toBe(a); expect(keys.for({ items: ['a'] })).toBe(a);
  expect(moveItem(['a', 'b'], 0, -1)).toEqual(['a', 'b']);
  expect(batchItemLabel(batch.items[0])).toBe('本次处理失败');
});

it('requires an explicit video-only choice for mixed links in multiple mode', async () => {
  await render(<ImportPanel />); await click('多个链接');
  await fill('#batch-links', 'https://youtube.com/watch?v=abcdefghijk&list=PLcourse');
  expect([...container.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent === '解析预览')!.disabled).toBe(true);
  await act(async () => (container.querySelector('[name=multiple-scope]') as HTMLInputElement).click());
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(service.previewImport).toHaveBeenCalledWith('multiple', ['https://youtube.com/watch?v=abcdefghijk&list=PLcourse']));
});
