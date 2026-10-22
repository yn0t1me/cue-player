// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useReaderFavorites } from './ReaderNotesControls';
import type { TranscriptMark } from '../../types/video';

let root: Root;
let container: HTMLDivElement;
const item = { id: 'new-favorite' } as TranscriptMark;
const deleteFavorite = vi.fn();
function Harness() {
  const notes = useReaderFavorites({ createFavorite: async () => ({ item, created: true }),
    deleteFavorite, onConflict: vi.fn() });
  return <><button onClick={event => notes.openSelection({ anchor: { revision_id: 'revision',
    segment_id: 'segment', start_offset: 0, end_offset: 4, selected_text: 'word' },
    trigger: event.currentTarget, rect: event.currentTarget.getBoundingClientRect(), keyboard: false })}>选择</button>{notes.controls}</>;
}
beforeEach(async () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers(); deleteFavorite.mockReset(); deleteFavorite.mockResolvedValue(undefined);
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  await act(async () => root.render(<Harness />));
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.useRealTimers(); });
async function favorite() {
  await act(async () => container.querySelector('button')!.click());
  await act(async () => (container.querySelector('.reader-selection-menu button') as HTMLButtonElement).click());
}
async function advance(ms: number) { await act(async () => vi.advanceTimersByTime(ms)); }
it('automatically dismisses success and its undo action after five seconds', async () => {
  await favorite(); expect(container.querySelector('.reader-notice')?.textContent).toContain('撤销');
  await advance(4999); expect(container.querySelector('.reader-notice')).not.toBeNull();
  await advance(1); expect(container.querySelector('.reader-notice')).toBeNull();
  expect(deleteFavorite).not.toHaveBeenCalled();
});
it('gives keyboard users time to undo while the notice has focus', async () => {
  await favorite();
  const undo = container.querySelector('.reader-notice button') as HTMLButtonElement;
  await act(async () => undo.focus());
  await advance(6000); expect(container.querySelector('.reader-notice')).not.toBeNull();
  await act(async () => undo.click());
  expect(deleteFavorite).toHaveBeenCalledWith('new-favorite');
  await act(async () => container.querySelector('button')!.focus());
  await advance(5000); expect(container.querySelector('.reader-notice')).toBeNull();
});
it('keeps a failed undo visible for retry', async () => {
  deleteFavorite.mockRejectedValue(new Error('网络故障，请重试'));
  await favorite();
  await act(async () => (container.querySelector('.reader-notice button') as HTMLButtonElement).click());
  await advance(10000);
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('网络故障');
});
