import { expect, it } from 'vitest';
import type { TranscriptSegment } from '../../types/video';
import { findActiveSegmentIndex } from './findActiveSegmentIndex';

function segment(sequence: number, start: number, end: number): TranscriptSegment {
  return { id: String(sequence), sequence_index: sequence, start, end, text: `Segment ${sequence}` };
}

const segments = [segment(0, 2, 4), segment(1, 5, 7), segment(2, 10, 12)];

it.each([
  ['before the first segment', 1.999, -1],
  ['at an exact start', 2, 0],
  ['in the middle', 3, 0],
  ['at an exact end', 4, -1],
  ['in a gap', 8, -1],
  ['after the final segment', 12, -1],
] as const)('finds the active segment %s', (_label, time, expected) => {
  expect(findActiveSegmentIndex(segments, time)).toBe(expected);
});

it('selects the latest-starting segment when active ranges overlap', () => {
  const overlapping = [segment(0, 0, 20), segment(1, 5, 8), segment(2, 5, 10)];
  expect(findActiveSegmentIndex(overlapping, 6)).toBe(2);
  expect(findActiveSegmentIndex(overlapping, 9)).toBe(2);
  expect(findActiveSegmentIndex(overlapping, 11)).toBe(0);
});

it('uses time order for remote seeks even if source entries are not ordered by start', () => {
  const unordered = [segment(2, 20, 22), segment(0, 0, 2), segment(1, 10, 12)];
  expect(findActiveSegmentIndex(unordered, 20.5)).toBe(0);
  expect(findActiveSegmentIndex(unordered, 10.5)).toBe(2);
});

it('returns no match for empty input or a non-finite time', () => {
  expect(findActiveSegmentIndex([], 0)).toBe(-1);
  expect(findActiveSegmentIndex(segments, Number.NaN)).toBe(-1);
});
