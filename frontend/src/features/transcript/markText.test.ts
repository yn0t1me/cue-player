// @vitest-environment jsdom
import { expect, it } from 'vitest';
import type { TranscriptMark } from '../../types/video';
import { markedTextParts, readableTextParts, readTextSelection } from './markText';

function select(node: Node, start: number, end: number): Selection {
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, end);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  return selection;
}

it('uses Unicode code-point offsets even when text is split by highlights', () => {
  const line = document.createElement('div');
  line.innerHTML = '<span>A😀</span><mark> learn</mark><span> now</span>';
  document.body.append(line);
  const selected = select(line.querySelector('span')!.firstChild!, 1, 3);
  expect(readTextSelection(line, 'A😀 learn now', selected)).toEqual({
    startOffset: 1, endOffset: 2, selectedText: '😀',
  });
  const repeated = select(line.querySelector('span:last-child')!.firstChild!, 1, 4);
  expect(readTextSelection(line, 'A😀 learn now', repeated)).toEqual({
    startOffset: 9, endOffset: 12, selectedText: 'now',
  });
  line.remove();
});

it('rejects cross-line and whitespace-only selections', () => {
  const first = document.createElement('div');
  first.textContent = 'one ';
  const second = document.createElement('div');
  second.textContent = 'two';
  document.body.append(first, second);
  const range = document.createRange();
  range.setStart(first.firstChild!, 0);
  range.setEnd(second.firstChild!, 3);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  expect(readTextSelection(first, 'one ', selection)).toBeNull();
  expect(readTextSelection(first, 'one ', select(first.firstChild!, 3, 4))).toBeNull();
  first.remove();
  second.remove();
});

it('merges overlapping mark highlights without duplicating subtitle text', () => {
  const marks = [
    { start_offset: 1, end_offset: 3 },
    { start_offset: 2, end_offset: 4 },
  ] as TranscriptMark[];
  expect(markedTextParts('A😀BC', marks)).toEqual([
    { text: 'A', marked: false },
    { text: '😀', marked: true },
    { text: 'B', marked: true },
    { text: 'C', marked: true },
  ]);
});

it('isolates valid chunk-boundary spaces without changing the text', () => {
  const parts = readableTextParts('A😀 phrase here', [] as TranscriptMark[], [2, 9, 99]);
  expect(parts.map(part => part.text).join('')).toBe('A😀 phrase here');
  expect(parts.filter(part => part.chunkBoundary).map(part => part.text)).toEqual([' ', ' ']);
});
