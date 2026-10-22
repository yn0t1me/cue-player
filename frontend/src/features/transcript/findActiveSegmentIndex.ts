import type { TranscriptSegment } from '../../types/video';

interface TimelineEntry {
  originalIndex: number;
  segment: TranscriptSegment;
  maxEndThroughEntry: number;
}

const timelineCache = new WeakMap<readonly TranscriptSegment[], TimelineEntry[]>();

function getTimeline(segments: readonly TranscriptSegment[]): TimelineEntry[] {
  const cached = timelineCache.get(segments);
  if (cached) return cached;

  let maxEnd = Number.NEGATIVE_INFINITY;
  const timeline = segments
    .map((segment, originalIndex) => ({ segment, originalIndex }))
    .sort((left, right) => left.segment.start - right.segment.start
      || left.segment.sequence_index - right.segment.sequence_index
      || left.originalIndex - right.originalIndex)
    .map(({ segment, originalIndex }) => {
      maxEnd = Math.max(maxEnd, segment.end);
      return { segment, originalIndex, maxEndThroughEntry: maxEnd };
    });
  timelineCache.set(segments, timeline);
  return timeline;
}

/** Returns the source-array index of the latest-starting active segment, or -1. */
export function findActiveSegmentIndex(
  segments: readonly TranscriptSegment[],
  currentTime: number,
): number {
  if (segments.length === 0 || !Number.isFinite(currentTime)) return -1;

  const timeline = getTimeline(segments);
  let low = 0;
  let high = timeline.length;
  while (low < high) {
    const middle = low + Math.floor((high - low) / 2);
    if (timeline[middle].segment.start <= currentTime) low = middle + 1;
    else high = middle;
  }

  for (let index = low - 1; index >= 0; index -= 1) {
    const entry = timeline[index];
    if (currentTime < entry.segment.end) return entry.originalIndex;
    if (index === 0 || timeline[index - 1].maxEndThroughEntry <= currentTime) break;
  }
  return -1;
}
