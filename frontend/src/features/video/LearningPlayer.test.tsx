// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import LearningPlayer from './LearningPlayer';

let root: Root;
let container: HTMLDivElement;
let fullscreenElement: Element | null;
let request: ReturnType<typeof vi.fn>;
let exit: ReturnType<typeof vi.fn>;
let onFullscreenChange: Mock<(fullscreen: boolean) => void>;
let onOpenTools: Mock<() => void>;

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  fullscreenElement = null;
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => fullscreenElement });
  request = vi.fn(async function (this: HTMLElement) {
    fullscreenElement = this; document.dispatchEvent(new Event('fullscreenchange'));
  });
  exit = vi.fn(async () => { fullscreenElement = null; document.dispatchEvent(new Event('fullscreenchange')); });
  vi.stubGlobal('ResizeObserver', undefined);
  Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', { configurable: true, value: request });
  Object.defineProperty(document, 'exitFullscreen', { configurable: true, value: exit });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    return { height: this.classList.contains('player-frame') ? 360 : 40, width: this.classList.contains('player-frame') ? 640 : 220 } as DOMRect;
  });
  onFullscreenChange = vi.fn(); onOpenTools = vi.fn();
});
afterEach(async () => {
  await act(async () => root.unmount()); container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  delete (HTMLElement.prototype as any).requestFullscreen;
  delete (document as any).exitFullscreen;
  delete (document as any).fullscreenElement;
});

async function render(segment = { id: 'one', sequence_index: 0, start: 1, end: 3, text: 'Current sentence.' }) {
  await act(async () => root.render(<LearningPlayer segment={segment} layout={null} mode="sentence"
    onModeChange={() => {}} chunksAvailable={false} chunksLoading={false}
    onOpenTools={onOpenTools} onFullscreenChange={onFullscreenChange}>
    <div className="player-frame">Video</div>
  </LearningPlayer>));
}
function button(label: string) {
  return [...container.querySelectorAll('button')].find(element => element.textContent?.includes(label))!;
}

it('requests fullscreen for the host containing both video and subtitles, and handles Esc without remounting', async () => {
  await render();
  const frame = container.querySelector('.player-frame');
  const trigger = button('带字幕全屏');
  await act(async () => trigger.click());
  expect(fullscreenElement).toBe(container.querySelector('.learning-player'));
  expect(fullscreenElement?.contains(container.querySelector('.player-subtitle'))).toBe(true);
  expect(button('退出全屏')).toBe(document.activeElement);
  expect(onFullscreenChange).toHaveBeenLastCalledWith(true);
  await act(async () => { fullscreenElement = null; document.dispatchEvent(new Event('fullscreenchange')); });
  expect(onFullscreenChange).toHaveBeenLastCalledWith(false);
  expect(document.activeElement).toBe(trigger);
  expect(container.querySelector('.player-frame')).toBe(frame);
  await act(async () => trigger.click());
  await act(async () => button('退出全屏').click());
  expect(exit).toHaveBeenCalledOnce();
  expect(container.querySelector('.learning-player')?.classList.contains('is-fullscreen')).toBe(false);
});

it('keeps ordinary viewing when fullscreen rejects or is unsupported', async () => {
  await render(); request.mockRejectedValueOnce(new Error('denied'));
  await act(async () => button('带字幕全屏').click());
  expect(container.textContent).toContain('全屏切换失败');
  expect(container.querySelector('.is-fullscreen')).toBeNull();
  expect(button('带字幕全屏').disabled).toBe(false);
  Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', { configurable: true, value: undefined });
  await act(async () => button('带字幕全屏').click());
  expect(container.textContent).toContain('不支持带字幕全屏');
});

it('does not take over or exit another element’s fullscreen', async () => {
  await render(); fullscreenElement = document.body;
  await act(async () => button('带字幕全屏').click());
  expect(request).not.toHaveBeenCalled();
  expect(container.textContent).toContain('请先退出当前全屏');
  await act(async () => root.render(null));
  expect(exit).not.toHaveBeenCalled();
});

it('cleans up owned fullscreen, including a request resolving after removal', async () => {
  await render(); await act(async () => button('带字幕全屏').click());
  await act(async () => root.render(null));
  expect(exit).toHaveBeenCalledOnce();
  await render();
  let resolve!: () => void;
  const element = container.querySelector('.learning-player');
  request.mockImplementationOnce(() => new Promise<void>(done => { resolve = done; }));
  await act(async () => button('带字幕全屏').click());
  await act(async () => root.render(null));
  await act(async () => { fullscreenElement = element; resolve(); });
  expect(exit).toHaveBeenCalledTimes(2);
});

it('leaves fullscreen before opening the external chunk settings', async () => {
  await render(); await act(async () => button('带字幕全屏').click());
  await act(async () => button('设置词块').click());
  expect(exit).toHaveBeenCalledOnce(); expect(onOpenTools).toHaveBeenCalledOnce();
  expect(fullscreenElement).toBeNull();
});

it('docks an oversized subtitle without dropping any of its text', async () => {
  vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
    return { height: this.classList.contains('player-frame') ? 200 : 150 } as DOMRect;
  });
  const text = 'A long subtitle with all its words intact. '.repeat(20);
  await render({ id: 'long', sequence_index: 0, start: 1, end: 3, text });
  expect(container.querySelector('.has-docked-subtitle')).not.toBeNull();
  expect(container.querySelector('.player-subtitle-text')?.textContent).toBe(text);
  await act(async () => button('学习字幕').click());
  expect(container.querySelector('.player-subtitle')).toBeNull();
});

it('moves subtitles only while adjusting, clamps to the safe area, and resets without remounting video', async () => {
  await render();
  const frame = container.querySelector('.player-frame');
  const subtitle = container.querySelector('.player-subtitle') as HTMLElement;
  subtitle.setPointerCapture = vi.fn(); subtitle.hasPointerCapture = vi.fn(() => true);
  subtitle.releasePointerCapture = vi.fn();
  const pointer = (type: string, x: number, y: number) => {
    const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y });
    Object.defineProperty(event, 'pointerId', { value: 7 });
    subtitle.dispatchEvent(event);
  };
  const original = subtitle.style.top;
  await act(async () => { pointer('pointerdown', 100, 100); pointer('pointermove', 100, -500); });
  expect(subtitle.style.top).toBe(original);
  await act(async () => button('调整位置').click());
  expect(subtitle.classList.contains('is-adjusting')).toBe(true);
  expect(subtitle.tabIndex).toBe(0);
  await act(async () => { pointer('pointerdown', 100, 100); pointer('pointermove', 1000, -500); pointer('pointerup', 1000, -500); });
  expect(subtitle.style.top).toBe('48px');
  expect(subtitle.style.left).toBe('calc(100% - 110px)');
  expect(subtitle.releasePointerCapture).toHaveBeenCalledWith(7);
  await act(async () => button('带字幕全屏').click());
  expect(subtitle.style.top).toBe('48px');
  await act(async () => button('重置位置').click());
  expect(subtitle.style.top).toBe(original);
  await act(async () => subtitle.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true })));
  expect(parseFloat(subtitle.style.top)).toBeLessThan(parseFloat(original));
  await act(async () => button('完成调整').click());
  expect(subtitle.classList.contains('is-adjusting')).toBe(false);
  expect(container.querySelector('.player-frame')).toBe(frame);
});

it('measures English and Chinese together, docks long bilingual text, and retains Chinese after hiding subtitles', async () => {
  vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
    return { height: this.classList.contains('player-frame') ? 240 : this.querySelector('.player-subtitle-translation') ? 180 : 40,
      width: this.classList.contains('player-frame') ? 640 : 220 } as DOMRect;
  });
  await act(async () => root.render(<LearningPlayer segment={{ id: 's', sequence_index: 0, start: 1, end: 3,
    text: 'English sentence.', translation_zh: '中文整句。'.repeat(10) }} layout={null} mode="sentence"
    onModeChange={() => {}} chunksAvailable={false} chunksLoading={false}
    onOpenTools={onOpenTools} onFullscreenChange={onFullscreenChange} translationAvailable>
    <div className="player-frame">Video</div></LearningPlayer>));
  const frame = container.querySelector('.player-frame');
  const toggle = container.querySelector('input[type=checkbox]') as HTMLInputElement;
  expect(toggle.checked).toBe(false); expect(container.querySelector('.has-docked-subtitle')).toBeNull();
  await act(async () => toggle.click());
  expect(container.querySelector('.has-docked-subtitle')).not.toBeNull();
  expect(container.querySelector('.player-subtitle-text')?.textContent).toContain('中文整句。');
  expect(button('调整位置').disabled).toBe(true);
  await act(async () => button('带字幕全屏').click());
  expect(fullscreenElement?.querySelector('.player-subtitle-translation')).not.toBeNull();
  await act(async () => button('学习字幕').click());
  expect(container.querySelector('.player-subtitle')).toBeNull(); expect(toggle.checked).toBe(true);
  await act(async () => button('学习字幕').click());
  expect(container.querySelector('.player-subtitle-translation')).not.toBeNull();
  expect(container.querySelector('.player-frame')).toBe(frame);
  await act(async () => toggle.click());
  expect(container.querySelector('.has-docked-subtitle')).toBeNull();
});
