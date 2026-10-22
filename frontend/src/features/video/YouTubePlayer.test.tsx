// @vitest-environment jsdom
import { act, createRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import YouTubePlayer, { type PlayerHandle } from './YouTubePlayer';
import { loadYouTubeApi } from './youtube-api';

vi.mock('./youtube-api', () => ({ loadYouTubeApi: vi.fn() }));
let root: Root;
let container: HTMLDivElement;
let events: any;
let fake: any;
let onTime: Mock<(seconds: number) => void>;
let ref: ReturnType<typeof createRef<PlayerHandle>>;
let constructor: ReturnType<typeof vi.fn>;

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  onTime = vi.fn();
  ref = createRef<PlayerHandle>();
  fake = { cueVideoById: vi.fn(), seekTo: vi.fn(), playVideo: vi.fn(), pauseVideo: vi.fn(),
    destroy: vi.fn(), getCurrentTime: vi.fn(() => 12.5) };
  constructor = vi.fn(function (_element: HTMLElement, options: any) { events = options.events; return fake; });
  vi.mocked(loadYouTubeApi).mockResolvedValue({ Player: constructor } as any);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.useRealTimers(); vi.clearAllMocks(); });

async function render(videoId = 'M7lc1UVf-VE') {
  await act(async () => root.render(<YouTubePlayer videoId={videoId} ref={ref} onTimeChange={onTime} />));
}

it('gates commands until ready and reports real time every 200ms', async () => {
  await render();
  expect(ref.current?.play()).toBe(false);
  expect(ref.current?.seekTo(2)).toBe(false);
  await act(async () => events.onReady({ target: fake }));
  expect(ref.current?.seekTo(-1)).toBe(false);
  expect(ref.current?.seekTo(Number.NaN)).toBe(false);
  expect(ref.current?.seekTo(4)).toBe(true);
  expect(fake.seekTo).toHaveBeenCalledWith(4, true);
  expect(ref.current?.play()).toBe(true);
  expect(fake.playVideo).toHaveBeenCalledOnce();
  await act(async () => vi.advanceTimersByTime(200));
  expect(onTime).toHaveBeenLastCalledWith(12.5);
  expect(constructor.mock.calls[0][1].playerVars.autoplay).toBe(0);
});

it('prepares a return position without interrupting media loading or reporting it as loaded', async () => {
  await act(async () => root.render(<YouTubePlayer videoId="M7lc1UVf-VE"
    initialTime={42.75} ref={ref} onTimeChange={onTime} />));
  await act(async () => events.onReady({ target: fake }));
  expect(fake.cueVideoById).toHaveBeenCalledWith({ videoId: 'M7lc1UVf-VE', startSeconds: 42.75 });
  expect(fake.seekTo).not.toHaveBeenCalled();
  expect(fake.pauseVideo).not.toHaveBeenCalled();
  expect(fake.playVideo).not.toHaveBeenCalled();
  fake.getCurrentTime.mockReturnValue(0);
  await act(async () => {
    events.onStateChange({ target: fake, data: 5 });
    vi.advanceTimersByTime(1000);
  });
  expect(onTime).not.toHaveBeenCalled();
  fake.getCurrentTime.mockReturnValue(42.75);
  await act(async () => events.onStateChange({ target: fake, data: 1 }));
  expect(onTime).toHaveBeenLastCalledWith(42.75);
  await act(async () => vi.advanceTimersByTime(200));
  expect(onTime).toHaveBeenCalledTimes(2);
});

it.each([0, 0.25])('prepares a valid return position at %s seconds', async initialTime => {
  await act(async () => root.render(<YouTubePlayer videoId="M7lc1UVf-VE"
    initialTime={initialTime} ref={ref} />));
  await act(async () => events.onReady({ target: fake }));
  expect(fake.cueVideoById).toHaveBeenCalledWith({ videoId: 'M7lc1UVf-VE', startSeconds: initialTime });
  expect(fake.playVideo).not.toHaveBeenCalled();
});

it.each([undefined, -1, Number.NaN, Number.POSITIVE_INFINITY])('does not cue an absent or invalid return position (%s)', async initialTime => {
  await act(async () => root.render(<YouTubePlayer videoId="M7lc1UVf-VE"
    initialTime={initialTime} ref={ref} onTimeChange={onTime} />));
  await act(async () => events.onReady({ target: fake }));
  expect(fake.cueVideoById).not.toHaveBeenCalled();
  expect(fake.seekTo).not.toHaveBeenCalled();
  expect(fake.pauseVideo).not.toHaveBeenCalled();
  await act(async () => vi.advanceTimersByTime(200));
  expect(onTime).toHaveBeenLastCalledWith(12.5);
});

it('allows sentence replay to replace a prepared return position', async () => {
  await act(async () => root.render(<YouTubePlayer videoId="M7lc1UVf-VE"
    initialTime={42} ref={ref} onTimeChange={onTime} />));
  await act(async () => events.onReady({ target: fake }));
  expect(ref.current?.seekTo(10)).toBe(true);
  expect(ref.current?.play()).toBe(true);
  expect(fake.seekTo).toHaveBeenCalledWith(10, true);
  expect(fake.playVideo).toHaveBeenCalledOnce();
  fake.getCurrentTime.mockReturnValue(10);
  await act(async () => events.onStateChange({ target: fake, data: 1 }));
  expect(onTime).toHaveBeenLastCalledWith(10);
});

it('destroys the instance and stops time reporting when removed', async () => {
  await render();
  await act(async () => events.onReady({ target: fake }));
  await act(async () => root.render(null));
  expect(fake.destroy).toHaveBeenCalledOnce();
  const count = onTime.mock.calls.length;
  await act(async () => vi.advanceTimersByTime(1000));
  expect(onTime.mock.calls).toHaveLength(count);
  expect(ref.current).toBeNull();
});

it('ignores an SDK resolving after unmount', async () => {
  let resolve!: (value: any) => void;
  vi.mocked(loadYouTubeApi).mockReturnValue(new Promise(r => { resolve = r; }));
  await render();
  await act(async () => root.render(null));
  await act(async () => resolve({ Player: constructor }));
  expect(constructor).not.toHaveBeenCalled();
});

it('shows embed error and prevents further commands', async () => {
  await render();
  await act(async () => events.onReady({ target: fake }));
  await act(async () => events.onError({ data: 150 }));
  expect(container.textContent).toContain('不允许嵌入播放');
  expect(ref.current?.play()).toBe(false);
  await act(async () => vi.advanceTimersByTime(1000));
  expect(onTime).not.toHaveBeenCalled();
});

it('times out if the iframe never becomes ready', async () => {
  await render();
  await act(async () => vi.advanceTimersByTime(15000));
  expect(container.textContent).toContain('超时');
});

it('destroys the previous video on a videoId change', async () => {
  await render();
  const previousEvents = events;
  await render('jNQXAC9IVRw');
  expect(fake.destroy).toHaveBeenCalledOnce();
  await act(async () => previousEvents.onReady({ target: fake }));
  expect(ref.current?.play()).toBe(false);
  expect(constructor).toHaveBeenCalledTimes(2);
});


it('does not accept a ready event after a timeout', async () => {
  await render();
  await act(async () => vi.advanceTimersByTime(15000));
  await act(async () => events.onReady({ target: fake }));
  expect(ref.current?.play()).toBe(false);
  expect(container.textContent).toContain('超时');
});

it('updates the time callback without recreating the player', async () => {
  await render();
  await act(async () => events.onReady({ target: fake }));
  const next = vi.fn();
  await act(async () => root.render(<YouTubePlayer videoId="M7lc1UVf-VE" ref={ref} onTimeChange={next} />));
  await act(async () => vi.advanceTimersByTime(200));
  expect(next).toHaveBeenCalledWith(12.5);
  expect(constructor).toHaveBeenCalledOnce();
});

it('retries after a script load failure', async () => {
  vi.mocked(loadYouTubeApi).mockRejectedValueOnce(new Error('网络不可用'));
  await render();
  expect(container.textContent).toContain('网络不可用');
  await act(async () => container.querySelector('button')!.click());
  expect(constructor).toHaveBeenCalledOnce();
  await act(async () => events.onReady({ target: fake }));
  expect(ref.current?.play()).toBe(true);
  expect(container.textContent).not.toContain('网络不可用');
});

it('reports readiness on load, error and retry without accepting stale state events', async () => {
  const onReadyChange = vi.fn();
  await act(async () => root.render(<YouTubePlayer videoId="M7lc1UVf-VE"
    onReadyChange={onReadyChange} onTimeChange={onTime} />));
  expect(onReadyChange).toHaveBeenLastCalledWith(false);
  await act(async () => events.onReady({ target: fake }));
  expect(onReadyChange).toHaveBeenLastCalledWith(true);
  await act(async () => events.onStateChange({ target: fake, data: 2 }));
  expect(onTime).toHaveBeenLastCalledWith(12.5);
  await act(async () => events.onError({ data: 150 }));
  expect(onReadyChange).toHaveBeenLastCalledWith(false);
  const previous = events;
  await act(async () => container.querySelector('button')!.click());
  await act(async () => previous.onStateChange({ target: fake, data: 1 }));
  expect(onTime).toHaveBeenCalledOnce();
  await act(async () => events.onReady({ target: fake }));
  expect(onReadyChange).toHaveBeenLastCalledWith(true);
});
