// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  delete (window as any).YT;
  delete (window as any).onYouTubeIframeAPIReady;
  document.head.innerHTML = '';
});
afterEach(() => vi.useRealTimers());

it('shares one script and one promise for concurrent callers', async () => {
  const { loadYouTubeApi } = await import('./youtube-api');
  const first = loadYouTubeApi();
  expect(loadYouTubeApi()).toBe(first);
  expect(document.querySelectorAll('script')).toHaveLength(1);
  const api = { Player: vi.fn() };
  (window as any).YT = api;
  (window as any).onYouTubeIframeAPIReady();
  await expect(first).resolves.toBe(api);
});

it('clears a failed attempt so the next call can retry', async () => {
  const { loadYouTubeApi } = await import('./youtube-api');
  const first = loadYouTubeApi();
  const rejected = expect(first).rejects.toThrow();
  document.querySelector('script')!.dispatchEvent(new Event('error'));
  await rejected;
  const retry = loadYouTubeApi();
  expect(retry).not.toBe(first);
  const resolved = expect(retry).resolves.toBeDefined();
  (window as any).YT = { Player: vi.fn() };
  (window as any).onYouTubeIframeAPIReady();
  await resolved;
});

it('rejects a stalled script after 15 seconds', async () => {
  const { loadYouTubeApi } = await import('./youtube-api');
  const result = expect(loadYouTubeApi()).rejects.toThrow('超时');
  await vi.advanceTimersByTimeAsync(15000);
  await result;
  expect(document.querySelectorAll('script')).toHaveLength(0);
});
