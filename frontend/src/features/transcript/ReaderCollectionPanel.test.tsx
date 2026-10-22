// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import ReaderCollectionPanel from './ReaderCollectionPanel';
import type { TranscriptMark } from '../../types/video';
let root: Root; let container: HTMLDivElement;
const writeText = vi.fn(); const onDelete = vi.fn(); const onReplay = vi.fn();
const item: TranscriptMark = { id: 'old', video_id: 'video', revision_id: 'old-revision', revision_number: 1,
  revision_origin: 'generated', is_current: false, segment_id: 's', segment_sequence_index: 0,
  segment_start: 5, segment_end: 6, segment_text: 'Old half sentence', start_offset: 0, end_offset: 3,
  selected_text: 'Old', created_at: '', updated_at: '' };
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  writeText.mockReset().mockResolvedValue(undefined); onDelete.mockReset().mockResolvedValue(undefined); onReplay.mockReset().mockReturnValue(true);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function render(items = [item]) { await act(async () => root.render(<ReaderCollectionPanel items={items} videoTitle="Video"
  loading={false} loadError={null} onRetry={vi.fn()} onReplay={onReplay} onDelete={onDelete} />)); }
async function click(label: string) { await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === label)!.click()); }
it('shows old subtitle context and exports expression only with that subtitle', async () => {
  await render(); expect(container.textContent).toContain('旧字幕版本'); expect(container.textContent).toContain('Old half sentence');
  expect(container.textContent).not.toMatch(/备注|问题|解答/);
  await click('复制全部收藏'); expect(writeText).toHaveBeenCalledWith('Video\n\n1.\n表达：Old\n原句：Old half sentence');
  await click('回听旧版'); expect(onReplay).toHaveBeenCalledWith(5);
});
it('requires explicit cancel confirmation and surfaces failure for retry', async () => {
  await render(); onDelete.mockRejectedValueOnce(new Error('网络故障'));
  await click('取消收藏'); expect(onDelete).not.toHaveBeenCalled();
  await click('确认取消收藏'); expect(container.querySelector('[role="alert"]')?.textContent).toContain('网络故障');
  await click('确认取消收藏'); expect(onDelete).toHaveBeenCalledTimes(2);
});
it('keeps records after clipboard failure and allows retry', async () => {
  await render(); writeText.mockRejectedValueOnce(new Error('denied'));
  await click('复制全部收藏'); expect(container.querySelector('[role="alert"]')?.textContent).toContain('复制失败');
  await click('复制全部收藏'); expect(writeText).toHaveBeenCalledTimes(2); expect(onDelete).not.toHaveBeenCalled();
});
it('does not export an empty collection', async () => {
  await render([]); expect([...container.querySelectorAll('button')].every(button => button.disabled)).toBe(true);
});
