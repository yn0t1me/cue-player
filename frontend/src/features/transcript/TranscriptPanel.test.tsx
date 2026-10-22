// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { TranscriptMark } from '../../types/video';
import TranscriptPanel, { formatTranscriptTime } from './TranscriptPanel';

let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  HTMLElement.prototype.scrollTo = vi.fn(function (this: HTMLElement) {
    this.dispatchEvent(new Event('scroll'));
  });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.restoreAllMocks(); });

it('renders ordered learning segments and their source-derived start times', async () => {
  await act(async () => root.render(<TranscriptPanel currentTime={10.5} onPlaySegment={() => true} transcript={{
    video_id: 'video-id', revision_id: 'revision-id', origin: 'generated', normalization_version: 1,
    segments: [
      { id: 'one', sequence_index: 0, start: 10.349, end: 12, text: 'First sentence.' },
      { id: 'two', sequence_index: 1, start: 65, end: 67, text: 'Second sentence.' },
    ],
  }} />));
  expect([...container.querySelectorAll('time')].map(node => node.textContent)).toEqual(['00:10', '01:05']);
  expect([...container.querySelectorAll('.segment-readable')].map(node => node.textContent)).toEqual([
    'First sentence.', 'Second sentence.']);
  expect(container.textContent).toContain('2 段 · v1');
  expect(container.textContent).toContain('时间来自原始字幕');
  expect(container.textContent).not.toContain('原始人工字幕');
  expect(container.textContent).toContain('点击时间或正文可回听');
  expect(container.querySelectorAll('.transcript-segment')[0].getAttribute('aria-current')).toBe('true');
  expect(container.querySelectorAll('.transcript-segment')[1].hasAttribute('aria-current')).toBe(false);
});

it('labels source-aligned subtitle timing', async () => {
  await act(async () => root.render(<TranscriptPanel currentTime={0} onPlaySegment={() => true} transcript={{
    video_id: 'video-id', revision_id: 'imported-id', origin: 'source_aligned',
    normalization_version: null,
    segments: [{ id: 'new-line', sequence_index: 0, start: 1, end: 2,
      text: 'Externally corrected.' }],
  }} />));
  expect(container.textContent).toContain('原字幕时间重建');
  expect(container.textContent).toContain('时间来自原始字幕');
  expect(container.textContent).not.toContain('vnull');
});

it('plays the selected segment and reports when the player is unavailable', async () => {
  const transcript = { video_id: 'video-id', revision_id: 'revision-id', origin: 'generated' as const, normalization_version: 1, segments: [
    { id: 'one', sequence_index: 0, start: 10, end: 12, text: 'Replay me.' },
  ] };
  let selected = -1;
  await act(async () => root.render(<TranscriptPanel
    currentTime={0}
    transcript={transcript}
    onPlaySegment={segment => { selected = segment.start; return true; }}
  />));
  await act(async () => (container.querySelector('.transcript-segment button') as HTMLButtonElement).click());
  expect(selected).toBe(10);
  expect(container.textContent).not.toContain('播放器尚未就绪');

  await act(async () => root.render(<TranscriptPanel
    currentTime={0}
    transcript={transcript}
    onPlaySegment={() => false}
  />));
  await act(async () => (container.querySelector('.transcript-segment button') as HTMLButtonElement).click());
  expect(container.textContent).toContain('播放器尚未就绪');
});

it('follows active segments, pauses for manual scroll, and restores without playing', async () => {
  const onPlaySegment = vi.fn(() => true);
  const transcript = { video_id: 'video-id', revision_id: 'revision-id', origin: 'generated' as const, normalization_version: 1, segments: [
    { id: 'one', sequence_index: 0, start: 10, end: 12, text: 'First.' },
    { id: 'two', sequence_index: 1, start: 20, end: 22, text: 'Second.' },
  ] };
  await act(async () => root.render(<TranscriptPanel
    currentTime={10.5} transcript={transcript} onPlaySegment={onPlaySegment}
  />));
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(1);
  expect(container.textContent).not.toContain('返回当前字幕');

  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 20)); });
  const list = container.querySelector('.transcript-list') as HTMLOListElement;
  await act(async () => list.dispatchEvent(new WheelEvent('wheel', { bubbles: true })));
  expect(container.textContent).toContain('返回当前字幕');
  await act(async () => root.render(<TranscriptPanel
    currentTime={20.5} transcript={transcript} onPlaySegment={onPlaySegment}
  />));
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(1);

  await act(async () => (container.querySelector('.transcript-follow-control button') as HTMLButtonElement).click());
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(2);
  expect(container.textContent).not.toContain('返回当前字幕');
  expect(onPlaySegment).not.toHaveBeenCalled();
});

it.each([
  ['wheel', () => new WheelEvent('wheel', { bubbles: true })],
  ['touch movement', () => new Event('touchmove', { bubbles: true })],
  ['direct scroll', () => new Event('scroll')],
  ['keyboard scrolling', () => new KeyboardEvent('keydown', { key: 'PageDown', bubbles: true })],
])('pauses following for %s but not for programmatic scroll events', async (_label, event) => {
  const transcript = { video_id: 'video-id', revision_id: 'revision-id', origin: 'generated' as const, normalization_version: 1, segments: [
    { id: 'one', sequence_index: 0, start: 1, end: 3, text: 'First.' },
  ] };
  await act(async () => root.render(<TranscriptPanel
    currentTime={2} transcript={transcript} onPlaySegment={() => true}
  />));
  expect(container.textContent).not.toContain('返回当前字幕');

  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 20)); });
  const list = container.querySelector('.transcript-list') as HTMLOListElement;
  await act(async () => list.dispatchEvent(event()));
  expect(container.textContent).toContain('返回当前字幕');
});

it('formats hour-long timestamps without rounding into the next second', () => {
  expect(formatTranscriptTime(3661.999)).toBe('1:01:01');
  expect(formatTranscriptTime(-1)).toBe('00:00');
});

it('selects text without playing and freezes Unicode offsets for the floating menu', async () => {
  const onPlaySegment = vi.fn(() => true);
  const onSelect = vi.fn().mockResolvedValue(undefined);
  await act(async () => root.render(<TranscriptPanel currentTime={0} onPlaySegment={onPlaySegment}
    onSelect={onSelect} transcript={{ video_id: 'video-id', revision_id: 'current',
      origin: 'source_aligned', normalization_version: null, segments: [
        { id: 'one', sequence_index: 0, start: 1, end: 3, text: 'A😀 phrase.' },
      ] }} />));
  const readable = container.querySelector('.segment-readable') as HTMLElement;
  const textNode = readable.querySelector('span')!.firstChild!;
  const range = document.createRange();
  range.setStart(textNode, 1);
  range.setEnd(textNode, 3);
  window.getSelection()!.removeAllRanges();
  window.getSelection()!.addRange(range);
  await act(async () => {
    readable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    readable.click();
  });
  expect(onPlaySegment).not.toHaveBeenCalled();
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ anchor: {
    revision_id: 'current', segment_id: 'one', start_offset: 1, end_offset: 2, selected_text: '😀',
  } }));
  expect(container.querySelector('form')).toBeNull();
  expect(onPlaySegment).not.toHaveBeenCalled();
});

it('highlights only marks attached to the current subtitle version', async () => {
  const mark = (revision_id: string): TranscriptMark => ({ id: revision_id, video_id: 'video-id',
    revision_id, revision_number: 1, revision_origin: 'generated', is_current: revision_id === 'current',
    segment_id: 'one', segment_sequence_index: 0, segment_start: 1, segment_end: 3,
    segment_text: 'Remember this.', start_offset: 0, end_offset: 8, selected_text: 'Remember',
    created_at: '', updated_at: '' });
  await act(async () => root.render(<TranscriptPanel currentTime={0} onPlaySegment={() => true}
    marks={[mark('old'), mark('current')]} transcript={{ video_id: 'video-id', revision_id: 'current',
      origin: 'generated', normalization_version: 1, segments: [
        { id: 'one', sequence_index: 0, start: 1, end: 3, text: 'Remember this.' },
      ] }} />));
  expect(container.querySelectorAll('mark')).toHaveLength(1);
  expect(container.querySelector('mark')?.textContent).toBe('Remember');
});

it('keeps canonical text and Unicode offsets when selecting across chunk boundaries', async () => {
  const onSelect = vi.fn().mockResolvedValue(undefined);
  const transcript = { video_id: 'video-id', revision_id: 'current', origin: 'generated' as const,
    normalization_version: 2, segments: [
      { id: 'one', sequence_index: 0, start: 1, end: 3, text: 'keep me in the loop' },
    ] };
  await act(async () => root.render(<TranscriptPanel currentTime={0} onPlaySegment={() => true}
    onSelect={onSelect} transcript={transcript} chunkLayout={{
      id: 'layout', revision_id: 'current', content_sha256: 'digest',
      created_at: '', updated_at: '', segments: [{
        segment_id: 'one', sequence_index: 0, start: 1, end: 3,
        text: 'keep me in the loop', boundary_offsets: [7], chunks: ['keep me', 'in the loop'],
      }],
    }} />));
  await act(async () => (Array.from(container.querySelectorAll('button'))
    .find(button => button.textContent === '词块') as HTMLButtonElement).click());
  const readable = container.querySelector('.segment-readable') as HTMLElement;
  expect(readable.textContent).toBe('keep me in the loop');
  expect(readable.querySelector('.chunk-boundary')?.textContent).toBe(' ');
  const spans = readable.querySelectorAll('span');
  const range = document.createRange();
  range.setStart(spans[0].firstChild!, 5);
  range.setEnd(spans[2].firstChild!, 2);
  window.getSelection()!.removeAllRanges();
  window.getSelection()!.addRange(range);
  await act(async () => readable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true })));
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ anchor: {
    revision_id: 'current', segment_id: 'one', start_offset: 5, end_offset: 10, selected_text: 'me in',
  } }));

});

it('suspends following while hidden, follows on return, and retains manual reading on return', async () => {
  const transcript = { video_id: 'video-id', revision_id: 'revision-id', origin: 'generated' as const,
    normalization_version: 1, segments: [
      { id: 'one', sequence_index: 0, start: 10, end: 12, text: 'First.' },
      { id: 'two', sequence_index: 1, start: 20, end: 22, text: 'Second.' },
    ] };
  const renderPanel = async (time: number, visible: boolean) => {
    await act(async () => root.render(<TranscriptPanel transcript={transcript}
      currentTime={time} visible={visible} onPlaySegment={() => true} />));
  };
  await renderPanel(10.5, true);
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(1);
  await renderPanel(20.5, false);
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(1);
  await renderPanel(20.5, true);
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(2);
  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 20)); });
  await act(async () => container.querySelector('.transcript-list')!.dispatchEvent(new WheelEvent('wheel', { bubbles: true })));
  await renderPanel(10.5, false); await renderPanel(10.5, true);
  expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain('返回当前字幕');
});

it('does not replay after the selection consumer clears the browser range', async () => {
  const onPlaySegment = vi.fn(() => true);
  const onSelect = vi.fn(() => window.getSelection()!.removeAllRanges());
  await act(async () => root.render(<TranscriptPanel currentTime={0} onPlaySegment={onPlaySegment}
    onSelect={onSelect} transcript={{ video_id: 'video-id', revision_id: 'current',
      origin: 'source_aligned', normalization_version: null, segments: [
        { id: 'one', sequence_index: 0, start: 1, end: 3, text: 'Select this word.' },
      ] }} />));
  const readable = container.querySelector('.segment-readable') as HTMLElement;
  const range = document.createRange();
  range.setStart(readable.querySelector('span')!.firstChild!, 0);
  range.setEnd(readable.querySelector('span')!.firstChild!, 6);
  window.getSelection()!.removeAllRanges(); window.getSelection()!.addRange(range);
  await act(async () => {
    readable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    readable.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }));
  });
  expect(onSelect).toHaveBeenCalledOnce();
  expect(onPlaySegment).not.toHaveBeenCalled();
  await act(async () => {
    readable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    readable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    readable.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }));
  });
  expect(onPlaySegment).toHaveBeenCalledOnce();
});

it('keeps Chinese outside English selection anchors and replay handlers', async () => {
  const onPlay = vi.fn(() => true), onSelect = vi.fn();
  await act(async () => root.render(<TranscriptPanel currentTime={1} onPlaySegment={onPlay} onSelect={onSelect}
    showTranslation transcript={{ video_id: 'v', revision_id: 'r', origin: 'source_aligned', normalization_version: null,
      segments: [{ id: 's', sequence_index: 0, start: 0, end: 2, text: 'Hello world.', translation_zh: '你好，世界。' }] }} />));
  const chinese = container.querySelector('.segment-translation')!;
  const english = container.querySelector('.segment-readable')!;
  expect(english.textContent).toBe('Hello world.');
  expect(english.contains(chinese)).toBe(false);
  await act(async () => {
    chinese.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    chinese.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
  expect(onPlay).not.toHaveBeenCalled(); expect(onSelect).not.toHaveBeenCalled();
  await act(async () => (container.querySelector('.segment-mark-whole') as HTMLButtonElement).click());
  expect(onSelect.mock.lastCall?.[0].anchor).toEqual({ revision_id: 'r', segment_id: 's',
    start_offset: 0, end_offset: 12, selected_text: 'Hello world.' });
});

it('remeasures on Chinese changes while preserving manual scroll and suspended following', async () => {
  const transcript = { video_id: 'v', revision_id: 'r', origin: 'generated' as const, normalization_version: 2,
    segments: [{ id: 's', sequence_index: 0, start: 0, end: 2, text: 'Hello.', translation_zh: '你好。' }] };
  const render = async (showTranslation: boolean, followSuspended = false) => act(async () => root.render(
    <TranscriptPanel transcript={transcript} currentTime={1} onPlaySegment={() => true}
      showTranslation={showTranslation} followSuspended={followSuspended} />));
  await render(false); expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(1);
  await render(true); expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(2);
  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 20)); });
  const list = container.querySelector('.transcript-list')! as HTMLElement;
  await act(async () => { list.scrollTop = 45; list.dispatchEvent(new WheelEvent('wheel', { bubbles: true })); });
  await render(false); expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(2);
  expect(list.scrollTop).toBe(45); expect(container.textContent).toContain('返回当前字幕');
  await render(true, true); expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledTimes(2);
});
