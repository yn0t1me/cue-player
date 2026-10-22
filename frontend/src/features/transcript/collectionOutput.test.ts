// @vitest-environment jsdom
import { expect, it, vi, afterEach } from 'vitest';
import type { TranscriptMark, TranscriptQuestion } from '../../types/video';
import { formatCollection, downloadCollection, defaultOutputOptions } from './collectionOutput';
const mark: TranscriptMark = { id: 'm', video_id: 'v', revision_id: 'r', revision_number: 1,
  revision_origin: 'generated', is_current: false, segment_id: 's', segment_sequence_index: 0,
  segment_start: 3661.9, segment_end: 3665, segment_text: 'A😀 *word*.', start_offset: 3, end_offset: 9,
  selected_text: '*word*', note: 'First line\n\n[link](https://example.com) <script> & text', created_at: '', updated_at: '' };
const question: TranscriptQuestion = { ...mark, question: 'Why?\nHow?', answer: null };
afterEach(() => vi.restoreAllMocks());

it('creates one Markdown download with a safe filename and cleans up the URL and element', async () => {
  vi.useFakeTimers();
  const create = vi.fn().mockReturnValue('blob:export'); const revoke = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
  const downloads: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download); });
  try {
    downloadCollection('# 收藏 · 中文\n', 'favorites', '../中文: "title"');
    expect(create.mock.calls[0][0].type).toBe('text/markdown;charset=utf-8');
    expect(downloads).toEqual(['context-english-..-中文- -title--favorites.md']);
    expect(document.querySelector('a[download]')).toBeNull();
    vi.runAllTimers(); expect(revoke).toHaveBeenCalledWith('blob:export');
  } finally { vi.useRealTimers(); }
});


it('keeps user-supplied list numbering as literal Markdown text', () => {
  const result = formatCollection([{ ...question, question: '7. Original list item\n- bullet\n``` code' }],
    'questions', 'Video', defaultOutputOptions(), 'markdown');
  expect(result).toContain('> 7\\. Original list item\n> \\- bullet\n> \\`\\`\\` code');
});


it('uses shared content defaults with compulsory expressions/questions and no internal metadata or instructions', () => {
  expect(defaultOutputOptions()).toEqual({ context: true, notes: false, questions: false, answers: false });
  const favorite = formatCollection([mark], 'favorites', 'Title', defaultOutputOptions());
  expect(favorite).toBe('Title\n\n1.\n表达：*word*\n原句：A😀 *word*.');
  const questions = formatCollection([question], 'questions', 'Title', defaultOutputOptions());
  expect(questions).toBe(favorite + '\n问题：Why?\nHow?');
  for (const text of [favorite, questions]) {
    expect(text).not.toMatch(/字幕版本|旧版|1:01:01|generated|Prompt|Skill|练习指令/);
    expect(text).not.toContain('备注'); expect(text).not.toContain('解答');
  }
  expect(formatCollection([question], 'questions', 'Title', { ...defaultOutputOptions(), context: false }))
    .toBe('Title\n\n1.\n表达：*word*\n问题：Why?\nHow?');
});

it('groups only identical selections, numbers groups in version/time order and includes the original once', () => {
  const same = { ...question, id: 'q2', question: 'Second question', answer: 'Second answer' };
  const other = { ...question, id: 'q3', start_offset: 10, end_offset: 16, question: 'Another position' };
  const revision = { ...question, id: 'q4', revision_id: 'new', revision_number: 2, is_current: true };
  const text = formatCollection([question, other, same, revision], 'questions', 'Title',
    { ...defaultOutputOptions(), answers: true });
  expect(text.match(/原句：/g)).toHaveLength(3);
  expect(text.match(/表达：/g)).toHaveLength(3);
  expect(text.match(/Title/g)).toHaveLength(1);
  expect(text.indexOf('1.')).toBeLessThan(text.indexOf('2.'));
  expect(text.indexOf('Second question')).toBeLessThan(text.indexOf('解答：Second answer'));
  expect(text.indexOf('解答：Second answer')).toBeLessThan(text.indexOf('3.'));
});

it('never expands a requested question range using the full cache, even at the same selection', () => {
  const outside = { ...question, id: 'outside', question: 'Outside the filter', answer: 'Hidden answer' };
  const text = formatCollection([question], 'questions', 'Title',
    { ...defaultOutputOptions(), answers: true }, 'text', { questions: [question, outside], marks: [mark] });
  expect(text).toContain(question.question); expect(text).not.toContain('Outside');
  expect(text).not.toContain('Hidden answer'); expect(text).not.toContain('备注');
});

it('outputs linked questions and answers independently, pairing each answer with its question', () => {
  const answered = { ...question, id: 'a', answer: 'Saved answer' };
  const unanswered = { ...question, id: 'u', question: 'Pending question' };
  const related = { questions: [answered, unanswered, { ...answered, id: 'other', video_id: 'other', question: 'Wrong video' }] };
  const onlyQuestions = formatCollection([mark], 'favorites', 'Title',
    { ...defaultOutputOptions(), questions: true }, 'text', related);
  expect(onlyQuestions).toContain('Pending question'); expect(onlyQuestions).not.toContain('解答');
  const answers = formatCollection([mark], 'favorites', 'Title',
    { ...defaultOutputOptions(), answers: true }, 'text', related);
  expect(answers).toContain('问题：Why?\nHow?\n解答：Saved answer');
  expect(answers).not.toContain('问题：Pending question'); expect(answers).not.toContain('Wrong video');
  expect(answers).not.toContain('尚未');
  expect(answers.match(/原句：/g)).toHaveLength(1);
});

it('uses only currently existing exact-selection favorites for question notes and retains selected duplicate notes', () => {
  const other = { ...mark, id: 'other', revision_id: 'different', note: 'Unrelated note' };
  const options = { ...defaultOutputOptions(), notes: true };
  const text = formatCollection([question], 'questions', 'Title', options, 'text', { marks: [mark, other] });
  expect(text).toContain('备注：' + mark.note); expect(text).not.toContain('Unrelated');
  expect(formatCollection([question], 'questions', 'Title', options, 'text', { marks: [] })).not.toContain('备注');
  const duplicate = { ...mark, id: 'duplicate', note: 'Another historical note' };
  const output = formatCollection([mark, duplicate], 'favorites', 'Title', options);
  expect(output.match(/原句：/g)).toHaveLength(1);
  expect(output).toContain('Another historical note'); expect(output).toContain(mark.note);
  expect(formatCollection([mark], 'favorites', 'Title', options, 'text', { marks: [duplicate] })).not.toContain('Another historical');
});

it('omits null, empty and legacy Unicode whitespace fields without altering nonempty user text', () => {
  const options = { ...defaultOutputOptions(), notes: true, answers: true };
  const text = formatCollection([{ ...question, answer: '\u0085 \n' }], 'questions', 'Title', options,
    'text', { marks: [{ ...mark, note: '\u3000' }] });
  expect(text).not.toContain('解答'); expect(text).not.toContain('备注');
  const body = ' \n\ufeff😀\n\nPreserved spaces  ';
  expect(formatCollection([{ ...question, answer: body }], 'questions', 'Title', options)).toContain('解答：' + body);
});

it('preserves the same field structure in text and Markdown and escapes HTML, formatting and multiline user content', () => {
  const options = { ...defaultOutputOptions(), notes: true, answers: true };
  const item = { ...question, answer: '<script>alert(1)</script>\r\n# heading\n7. list\n- item\n```code\n\n\tindented & \u{1f600}' };
  const related = { marks: [mark] };
  const text = formatCollection([item], 'questions', 'Title', options, 'text', related);
  const markdown = formatCollection([item], 'questions', 'Title', options, 'markdown', related);
  expect(markdown).toContain('# Title\n\n## 1. 表达');
  expect(markdown).not.toContain('<script>'); expect(markdown).toContain('&lt;script&gt;');
  expect(markdown).toContain('> A😀 \\*word\\*.');
  expect(markdown).toContain('> First line\n> \n> \\[link\\](https://example.com) &lt;script&gt; &amp; text');
  expect(markdown).toContain('> \\# heading\n> 7\\. list\n> \\- item\n> \\`\\`\\`code');
  expect(text).toContain(item.answer);
  const labels = ['表达', '原句', '备注', '问题', '解答'];
  expect(text.split('\n').filter(line => labels.some(label => line.startsWith(label + '：'))).map(line => line.split('：')[0]))
    .toEqual([...markdown.matchAll(/\*\*(表达|原句|备注|问题|解答)\*\*/g)].map(match => match[1]));
  expect(markdown.endsWith('\n')).toBe(true);
});

it('does not mutate cache arrays or records when grouping and joining content', () => {
  const items = [Object.freeze({ ...question, id: 'z' }), Object.freeze({ ...question, id: 'a' })];
  const snapshot = JSON.stringify(items);
  Object.freeze(items);
  formatCollection(items, 'questions', 'Title', { ...defaultOutputOptions(), notes: true }, 'markdown', { marks: [mark] });
  expect(JSON.stringify(items)).toBe(snapshot);
});

it('cleans the download URL after a failure and allows retry without changing content', () => {
  vi.useFakeTimers();
  const revoke = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn().mockReturnValue('blob:retry') });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementationOnce(() => { throw Error('Download denied'); }).mockImplementation(() => {});
  try {
    expect(() => downloadCollection('内容😀', 'questions', 'Title')).toThrow('Download denied');
    expect(document.querySelector('a[download]')).toBeNull();
    vi.runAllTimers(); expect(revoke).toHaveBeenCalledWith('blob:retry');
    downloadCollection('内容😀', 'questions', 'Title'); expect(click).toHaveBeenCalledTimes(2);
  } finally { vi.runAllTimers(); vi.useRealTimers(); }
});
