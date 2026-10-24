// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import TranscriptExportPanel from './TranscriptExportPanel';
import type { ChunkLayout, Transcript } from '../../types/video';
let root: Root; let container: HTMLDivElement;
const writeText = vi.fn(); const onRetry = vi.fn();
const transcript: Transcript = { video_id: 'v', revision_id: 'r', origin: 'source_aligned', normalization_version: null,
  segments: [{ id: 's', sequence_index: 0, start: 0, end: 1, text: 'Hello world', translation_zh: '你好世界' }] };
const layout: ChunkLayout = { id: 'l', revision_id: 'r', created_at: '', updated_at: '', content_sha256: '',
  segments: [{ ...transcript.segments[0], segment_id: 's', boundary_offsets: [5], chunks: ['Hello', 'world'] }] };
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  writeText.mockReset().mockResolvedValue(undefined); onRetry.mockReset();
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function render(t = transcript, l: ChunkLayout | null = layout, loading = false, error: string | null = null) {
  await act(async () => root.render(<TranscriptExportPanel transcript={t} videoTitle="Video"
    layout={l} loading={loading} error={error} onRetry={onRetry} />));
}
async function click(label: string) { await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === label)!.click()); }
it('selects translation and chunks independently of English and downloads the same material', async () => {
  await render(); await click('复制完整字幕'); expect(writeText).toHaveBeenLastCalledWith('Video\n\nHello world');
  const boxes = container.querySelectorAll<HTMLInputElement>('input');
  await act(async () => boxes[0].click()); await click('复制完整字幕');
  expect(writeText.mock.lastCall?.[0]).toContain('中文：你好世界'); expect(writeText.mock.lastCall?.[0]).not.toContain('词块');
  await act(async () => boxes[1].click()); await click('复制完整字幕');
  expect(writeText.mock.lastCall?.[0]).toContain('词块：Hello / world');
  const createObjectURL = vi.fn((_blob: Blob) => 'blob:test'); const revokeObjectURL = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
  let filename = '';
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { filename = this.download; });
  await click('导出字幕 Markdown');
  const blob = createObjectURL.mock.calls[0]?.[0];
  expect(filename).toBe('cue-player-Video-transcript.md');
  expect(blob).toBeInstanceOf(Blob); expect(anchorClick).toHaveBeenCalledOnce();
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:test'); expect(document.querySelector('a[download]')).toBeNull();
  const read = new FileReader(); const content = await new Promise<string>(resolve => { read.onload = () => resolve(String(read.result)); read.readAsText(blob!); });
  expect(content).toContain('Hello world'); expect(content).toContain('你好世界'); expect(content).toContain('Hello / world');
});
it('exports English directly without missing-content explanations or options', async () => {
  await render({ ...transcript, segments: [{ ...transcript.segments[0], translation_zh: null }] }, null);
  expect(container.querySelector('input')).toBeNull(); expect(container.textContent).not.toMatch(/缺少|无中文|无词块|加工|原因/);
  await click('复制完整字幕'); expect(writeText).toHaveBeenCalledWith('Video\n\nHello world');
});
it('never offers stale chunks, reports clipboard failure and allows retry', async () => {
  await render(transcript, { ...layout, revision_id: 'old' });
  expect(container.textContent).not.toContain('包含词块'); writeText.mockRejectedValueOnce(new Error('denied'));
  await click('复制完整字幕'); expect(container.querySelector('[role="alert"]')?.textContent).toContain('复制失败');
  await click('复制完整字幕'); expect(writeText).toHaveBeenCalledTimes(2);
});
it('waits for queries and offers retry on actual read errors', async () => {
  await render(transcript, null, true); expect(container.querySelector('button')?.disabled).toBe(true);
  await render(transcript, null, false, '读取失败'); await click('重试读取'); expect(onRetry).toHaveBeenCalledOnce();
  expect(writeText).not.toHaveBeenCalled();
});
