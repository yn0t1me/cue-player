import type { TranscriptMark } from '../../types/video';

export interface TextSelection {
  startOffset: number;
  endOffset: number;
  selectedText: string;
}

export function readTextSelection(element: HTMLElement, text: string,
                                  selection: Selection | null): TextSelection | null {
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return null;
  const range = selection.getRangeAt(0);
  if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return null;
  const before = range.cloneRange();
  before.selectNodeContents(element);
  before.setEnd(range.startContainer, range.startOffset);
  const startOffset = Array.from(before.toString()).length;
  const selectedText = range.toString();
  const endOffset = startOffset + Array.from(selectedText).length;
  if (!selectedText.trim()
      || Array.from(text).slice(startOffset, endOffset).join('') !== selectedText) return null;
  return { startOffset, endOffset, selectedText };
}

export function markedTextParts(text: string, marks: TranscriptMark[]):
  Array<{ text: string; marked: boolean }> {
  if (marks.length === 0) return [{ text, marked: false }];
  const characters = Array.from(text);
  const boundaries = new Set([0, characters.length]);
  for (const mark of marks) {
    boundaries.add(Math.max(0, Math.min(characters.length, mark.start_offset)));
    boundaries.add(Math.max(0, Math.min(characters.length, mark.end_offset)));
  }
  const sorted = [...boundaries].sort((a, b) => a - b);
  return sorted.slice(0, -1).map((start, index) => {
    const end = sorted[index + 1];
    return {
      text: characters.slice(start, end).join(''),
      marked: marks.some(mark => mark.start_offset < end && mark.end_offset > start),
    };
  }).filter(part => part.text.length > 0);
}

export function readableTextParts(text: string, marks: TranscriptMark[], chunkBoundaries: number[]):
  Array<{ text: string; marked: boolean; chunkBoundary: boolean }> {
  const characters = Array.from(text);
  const boundaries = new Set([0, characters.length]);
  for (const mark of marks) {
    boundaries.add(Math.max(0, Math.min(characters.length, mark.start_offset)));
    boundaries.add(Math.max(0, Math.min(characters.length, mark.end_offset)));
  }
  const validChunkBoundaries = new Set(chunkBoundaries.filter(offset =>
    offset > 0 && offset < characters.length && characters[offset] === ' '));
  for (const offset of validChunkBoundaries) {
    boundaries.add(offset);
    boundaries.add(offset + 1);
  }
  const sorted = [...boundaries].sort((a, b) => a - b);
  return sorted.slice(0, -1).map((start, index) => {
    const end = sorted[index + 1];
    return {
      text: characters.slice(start, end).join(''),
      marked: marks.some(mark => mark.start_offset < end && mark.end_offset > start),
      chunkBoundary: validChunkBoundaries.has(start) && end === start + 1,
    };
  }).filter(part => part.text.length > 0);
}
