import type { ChunkLayout, Transcript, TranscriptMark } from '../../types/video';
import { hasCurrentChunkLayout } from './TranscriptViewSwitch';

export function orderedEntries(items: TranscriptMark[]): TranscriptMark[] {
  return [...items].sort((a, b) => a.segment_start - b.segment_start
    || a.segment_sequence_index - b.segment_sequence_index || a.start_offset - b.start_offset
    || a.revision_number - b.revision_number || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}
function markdownText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/([\\`*_[\]{}#!|~=])/g, '\\$1').replace(/^([ \t]*)([-+.])/gm, '$1\\$2')
    .replace(/^([ \t]*\d+)([.)])/gm, '$1\\$2');
}
type Format = 'text' | 'markdown';
function heading(title: string, format: Format): string {
  return format === 'markdown' ? `# ${markdownText(title).replace(/\r\n?/g, ' ')}` : title;
}
function field(label: string, value: string, format: Format): string {
  return format === 'markdown' ? `**${label}**\n\n> ${markdownText(value).replace(/\r\n?/g, '\n').replace(/\n/g, '\n> ')}`
    : `${label}：${value}`;
}
export function formatCollection(items: TranscriptMark[], videoTitle: string, format: Format = 'text'): string {
  const seen = new Set<string>();
  const groups = orderedEntries(items).filter(item => {
    const key = JSON.stringify([item.revision_id, item.segment_id, item.start_offset, item.end_offset]);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  }).map((item, index) => [format === 'markdown' ? `## ${index + 1}. 表达` : `${index + 1}.`,
    field('表达', item.selected_text, format), field('原句', item.segment_text, format)].join(format === 'markdown' ? '\n\n' : '\n'));
  return [heading(videoTitle, format), ...groups].join('\n\n') + (format === 'markdown' ? '\n' : '');
}
export interface TranscriptOutputOptions { translation: boolean; chunks: boolean; }
export function formatTranscript(transcript: Transcript, videoTitle: string, options: TranscriptOutputOptions,
  layout?: ChunkLayout | null, format: Format = 'text'): string {
  const chunks = new Map(hasCurrentChunkLayout(transcript, layout)
    ? layout!.segments.map(segment => [segment.segment_id, segment.chunks]) : []);
  const segments = [...transcript.segments].sort((a, b) => a.sequence_index - b.sequence_index).map(segment => [
    format === 'markdown' ? markdownText(segment.text) : segment.text,
    ...(options.translation && segment.translation_zh?.trim() ? [field('中文', segment.translation_zh, format)] : []),
    ...(options.chunks && chunks.has(segment.id) ? [field('词块', chunks.get(segment.id)!.join(' / '), format)] : []),
  ].join('\n\n'));
  return [heading(videoTitle, format), ...segments].join('\n\n') + (format === 'markdown' ? '\n' : '');
}
export function downloadCollection(content: string, kind: 'favorites' | 'transcript', videoTitle: string): void {
  const safeTitle = Array.from(videoTitle.replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').trim()).slice(0, 80).join('') || 'video';
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  try {
    link.href = url; link.download = `cue-player-${safeTitle}-${kind}.md`;
    document.body.append(link); link.click();
  } finally { link.remove(); URL.revokeObjectURL(url); }
}
