import { expect, it, vi } from 'vitest';
import type { ChunkLayout, Transcript, TranscriptMark } from '../../types/video';
import { downloadCollection, formatCollection, formatTranscript } from './collectionOutput';

const mark: TranscriptMark = { id: 'mark', video_id: 'video', revision_id: 'old', revision_number: 1,
  revision_origin: 'generated', is_current: false, segment_id: 'segment', segment_sequence_index: 0,
  segment_start: 12, segment_end: 13, segment_text: 'half a sentence', start_offset: 0, end_offset: 4,
  selected_text: 'half', created_at: '', updated_at: '' };
const transcript: Transcript = { video_id: 'video', revision_id: 'current', origin: 'source_aligned', normalization_version: null,
  segments: [{ id: 'two', sequence_index: 1, start: 1, end: 2, text: 'Next line.', translation_zh: null },
    { id: 'one', sequence_index: 0, start: 0, end: 1, text: 'Hello 😀 world.', translation_zh: '你好世界。' }] };
const layout: ChunkLayout = { id: 'layout', revision_id: 'current', content_sha256: '', created_at: '', updated_at: '',
  segments: transcript.segments.map(segment => ({ ...segment, segment_id: segment.id, boundary_offsets: [], chunks: [segment.text] })) };
it('exports old expression and its exact subtitle without neighboring lines or metadata', () => {
  expect(formatCollection([mark], 'Video')).toBe('Video\n\n1.\n表达：half\n原句：half a sentence');
  expect(formatCollection([mark], 'Video')).not.toMatch(/old|12|版本|问题|指令/);
});
it('orders across versions by video time and keeps equal words at different positions', () => {
  const earlier = { ...mark, id: 'earlier', is_current: true, revision_id: 'current', segment_start: 1, start_offset: 7, end_offset: 11 };
  const content = formatCollection([mark, earlier, { ...mark, id: 'duplicate' }], 'Video');
  expect(content.match(/表达：half/g)).toHaveLength(2);
  expect(content.indexOf('1.')).toBeLessThan(content.indexOf('2.'));
});
it('exports current English in subtitle order without optional placeholders', () => {
  expect(formatTranscript(transcript, 'Video', { translation: false, chunks: false })).toBe('Video\n\nHello 😀 world.\n\nNext line.');
});
it('independently includes Chinese and chunks and omits absent translations', () => {
  const both = formatTranscript(transcript, 'Video', { translation: true, chunks: true }, layout);
  expect(both).toContain('中文：你好世界。'); expect(both).toContain('词块：Hello 😀 world.');
  expect(both.match(/中文：/g)).toHaveLength(1); expect(both).not.toContain('无中文');
  expect(formatTranscript(transcript, 'Video', { translation: false, chunks: true }, layout)).not.toContain('中文：');
  expect(formatTranscript(transcript, 'Video', { translation: true, chunks: false }, layout)).not.toContain('词块：');
});
it('never mixes a stale or incomplete chunk layout into current output', () => {
  for (const bad of [{ ...layout, revision_id: 'old' }, { ...layout, segments: layout.segments.slice(1) }]) {
    expect(formatTranscript(transcript, 'Video', { translation: true, chunks: true }, bad)).not.toContain('词块：');
  }
});
it('escapes user Markdown and preserves Unicode and line breaks', () => {
  const content = formatCollection([{ ...mark, selected_text: '[词]*😀', segment_text: '<tag>\nnext' }], '# title', 'markdown');
  expect(content).toContain('# \\# title'); expect(content).toContain('\\[词\\]\\*😀');
  expect(content).toContain('&lt;tag&gt;\n> next');
});
