// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getVideos } from './api/videos';
import App from './App';

vi.mock('./api/videos', () => ({
  getVideos: vi.fn(),
  importVideo: vi.fn(),
}));

let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(getVideos).mockResolvedValue({ items: [] });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

it('identifies the M0.4 reader and explains the complete source fallback', async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><App /></MemoryRouter>
    </QueryClientProvider>,
  ));

  await vi.waitFor(() => expect(container.textContent).toContain('从一个想看懂的视频开始'));
  expect(container.querySelector('.edition')?.textContent).toBe('M0.4 · 英文字幕读器');
  expect(container.querySelector('#import-hint')?.textContent).toContain('都没有时在本机进行语音转写');
  queryClient.clear();
});
