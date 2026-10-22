import type { TranscriptMark, TranscriptQuestion } from '../../types/video';

export type QuestionFilter = 'all' | 'unanswered' | 'answered';
export const questionFilterLabels: Record<QuestionFilter, string> = {
  all: '全部', unanswered: '待解答', answered: '已有解答',
};

export function hasContent(value: string | null): value is string {
  // Match the backend's Python str.strip() semantics for preserved legacy answers.
  return value != null && !/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(value);
}

export function hasAnswer(question: TranscriptQuestion): boolean {
  return hasContent(question.answer);
}

// Text and timing cannot identify a selection, especially across revisions or repeated words.
export function selectionKey(item: TranscriptMark | TranscriptQuestion): string {
  return JSON.stringify([item.video_id, item.revision_id, item.segment_id, item.start_offset, item.end_offset]);
}

export function questionsBySelection(questions: TranscriptQuestion[]): Map<string, TranscriptQuestion[]> {
  const result = new Map<string, TranscriptQuestion[]>();
  for (const question of questions) {
    const key = selectionKey(question);
    const group = result.get(key) ?? [];
    group.push(question);
    result.set(key, group);
  }
  return result;
}

export function filterQuestions(questions: TranscriptQuestion[], filter: QuestionFilter): TranscriptQuestion[] {
  return questions.filter(question => filter === 'all' || hasAnswer(question) === (filter === 'answered'));
}
