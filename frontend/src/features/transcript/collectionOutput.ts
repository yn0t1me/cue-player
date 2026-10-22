import type { TranscriptMark, TranscriptQuestion } from '../../types/video';
import { hasContent, questionsBySelection, selectionKey } from './noteRelations';

export type CollectionEntry = TranscriptMark | TranscriptQuestion;
export type CollectionKind = 'favorites' | 'questions';
export interface OutputOptions { context: boolean; notes: boolean; questions: boolean; answers: boolean; }
export const defaultOutputOptions = (): OutputOptions => ({
  context: true, notes: false, questions: false, answers: false,
});

// Same order as the API; never mutate query-cache arrays.
export function orderedEntries<T extends CollectionEntry>(items: T[]): T[] {
  return [...items].sort((a, b) => Number(b.is_current) - Number(a.is_current)
    || b.revision_number - a.revision_number || a.segment_start - b.segment_start
    || a.segment_sequence_index - b.segment_sequence_index || a.start_offset - b.start_offset
    || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}

interface OutputQuestion { question: string; answer?: string; }
interface OutputGroup { expression: string; context?: string; notes: string[]; questions: OutputQuestion[]; }
export interface RelatedOutputData { marks?: TranscriptMark[]; questions?: TranscriptQuestion[]; }

// Build only from the requested records. Complete caches supply relations, never extra scope.
function outputGroups(items: CollectionEntry[], kind: CollectionKind, options: OutputOptions,
  related: RelatedOutputData): OutputGroup[] {
  const grouped = new Map<string, CollectionEntry[]>();
  for (const item of orderedEntries(items)) {
    const key = selectionKey(item);
    const group = grouped.get(key) ?? [];
    group.push(item); grouped.set(key, group);
  }
  const linked = questionsBySelection(related.questions ?? []);
  return [...grouped.entries()].map(([key, entries]) => {
    const first = entries[0];
    const marks = kind === 'favorites' ? entries.filter((item): item is TranscriptMark => !('question' in item))
      : orderedEntries((related.marks ?? []).filter(mark => selectionKey(mark) === key));
    const questions = kind === 'questions' ? entries.filter((item): item is TranscriptQuestion => 'question' in item)
      : orderedEntries(linked.get(key) ?? []).filter(question => options.questions || (options.answers && hasContent(question.answer)));
    return {
      expression: first.selected_text,
      context: options.context ? first.segment_text : undefined,
      // Historical duplicate favorites remain independent; preserve each distinct saved note.
      notes: options.notes ? [...new Set(marks.map(mark => mark.note).filter(hasContent))] : [],
      questions: questions.map(question => ({ question: question.question,
        ...(options.answers && hasContent(question.answer) ? { answer: question.answer } : {}) })),
    };
  });
}

function markdownText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/([\\`*_[\]{}#!|~=])/g, '\\$1').replace(/^([ \t]*)([-+.])/gm, '$1\\$2').replace(/^([ \t]*\d+)([.)])/gm, '$1\\$2');
}

export function formatCollection(items: CollectionEntry[], kind: CollectionKind, videoTitle: string,
  options: OutputOptions, format: 'text' | 'markdown' = 'text', related: RelatedOutputData = {}): string {
  const markdown = format === 'markdown';
  const field = (label: string, value: string) => markdown
    ? `**${label}**\n\n> ${markdownText(value).replace(/\r\n?/g, '\n').replace(/\n/g, '\n> ')}`
    : `${label}：${value}`;
  const title = markdown ? `# ${markdownText(videoTitle).replace(/\r\n?/g, ' ')}` : videoTitle;
  const sections = outputGroups(items, kind, options, related).map((group, index) => {
    const body = [field('表达', group.expression),
      ...(group.context !== undefined ? [field('原句', group.context)] : []),
      ...group.notes.map(note => field('备注', note)),
      ...group.questions.flatMap(question => [field('问题', question.question),
        ...(question.answer !== undefined ? [field('解答', question.answer)] : [])])];
    return [markdown ? `## ${index + 1}. 表达` : `${index + 1}.`, ...body].join(markdown ? '\n\n' : '\n');
  });
  return [title, ...sections].join('\n\n') + (markdown ? '\n' : '');
}

export function downloadCollection(content: string, kind: CollectionKind, videoTitle: string): void {
  const safeTitle = Array.from(videoTitle.replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').trim()).slice(0, 80).join('') || 'video';
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  try {
    link.href = url; link.download = `context-english-${safeTitle}-${kind}.md`;
    document.body.append(link); link.click();
  } finally {
    link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}
