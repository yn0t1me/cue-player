// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { importVideo } from '../../api/videos';
import ImportVideoForm from './ImportVideoForm';
vi.mock('../../api/videos', () => ({ importVideo: vi.fn() }));
let root: Root, container: HTMLDivElement, client: QueryClient;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); client.clear(); vi.resetAllMocks(); });
function Destination() {
  const location = useLocation();
  return <p>{location.pathname} {location.state?.alreadyExists ? 'existing source retained' : 'new video'}</p>;
}
async function render() {
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter><Routes>
    <Route path="/" element={<ImportVideoForm />} /><Route path="/videos/:id" element={<Destination />} />
  </Routes></MemoryRouter></QueryClientProvider>));
  await act(async () => {
    const input = container.querySelector('input')!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'https://youtu.be/abcdefghijk');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
it.each(['manual_first', 'auto_only'] as const)('submits %s and opens existing records without replacing their source', async preference => {
  vi.mocked(importVideo).mockResolvedValue({ already_exists: true, video: { id: 'old', subtitle_preference: 'manual_first' }, job: null } as any);
  await render();
  expect((container.querySelector('select') as HTMLSelectElement).value).toBe('manual_first');
  await act(async () => {
    const select = container.querySelector('select')!; select.value = preference;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(container.textContent).toContain('/videos/old existing source retained'));
  expect(importVideo).toHaveBeenCalledExactlyOnceWith('https://youtu.be/abcdefghijk', preference);
});
it('keeps the selected source and URL when importing fails', async () => {
  vi.mocked(importVideo).mockRejectedValue(new Error('保存失败'));
  await render();
  const select = container.querySelector('select')!;
  await act(async () => { select.value = 'auto_only'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  await vi.waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toBe('保存失败'));
  expect(select.value).toBe('auto_only'); expect(container.querySelector('input')!.value).toContain('abcdefghijk');
  expect(container.textContent).toContain('自动模式只找自动英文字幕');
});
