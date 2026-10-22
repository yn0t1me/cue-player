// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { TranscriptMark, TranscriptQuestion } from '../../types/video';
import ReaderCollectionPanel from './ReaderCollectionPanel';

let root: Root;
let container: HTMLDivElement;
let writeText: ReturnType<typeof vi.fn>;
const current: TranscriptMark = {
  id: 'current-mark', video_id: 'video-id', revision_id: 'current', revision_number: 2,
  revision_origin: 'source_aligned', is_current: true, segment_id: 'current-segment',
  segment_sequence_index: 0, segment_start: 12, segment_end: 14,
  segment_text: 'A😀 this phrase.', start_offset: 3, end_offset: 7,
  selected_text: 'this', note: 'My note', created_at: '', updated_at: '',
};
const old: TranscriptMark = { ...current, id: 'old-mark', revision_id: 'old', revision_number: 1,
  revision_origin: 'generated', is_current: false, segment_id: 'old-segment', segment_start: 2,
  segment_text: 'An older sentence.', start_offset: 3, end_offset: 8, selected_text: 'older', note: null };
const question: TranscriptQuestion = { ...current, question: 'Why this wording?', answer: 'Because of the context.' };
const replay = vi.fn(() => true);
const remove = vi.fn().mockResolvedValue(undefined);
const editNote = vi.fn();
const editQuestion = vi.fn();
const editAnswer = vi.fn();
const common = { videoTitle: 'Video', loading: false, loadError: null, onRetry: vi.fn(),
  onReplay: replay, editingDisabled: false, onDelete: remove, relatedLoading: false, relatedError: null, onRetryRelated: vi.fn(), onEditQuestion: editQuestion, onEditAnswer: editAnswer };
const renderFavorites = (items = [old, current], props = {}) => act(async () => root.render(
  <ReaderCollectionPanel {...common} kind="favorites" items={items} onEditNote={editNote} relatedQuestions={[]} relatedLoading={false} relatedError={null}
    onRetryRelated={common.onRetry} onDeleteQuestion={remove} {...props} />));
const renderQuestions = (items = [question], props = {}) => act(async () => root.render(
  <ReaderCollectionPanel {...common} kind="questions" items={items} relatedMarks={[]}
    onEditQuestion={editQuestion} onEditAnswer={editAnswer} {...props} />));
const click = async (label: string, parent: ParentNode = container) => act(async () => {
  [...parent.querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent === label)!.click();
});
const checkbox = (label: string) => [...container.querySelectorAll('label')].find(node => node.textContent === label)!.querySelector('input')!;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.append(container); root = createRoot(container);
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.clearAllMocks(); vi.restoreAllMocks(); });

it('defaults to expressions, orders versions, expands original Unicode context and notes', async () => {
  await renderFavorites();
  expect([...container.querySelectorAll('blockquote')].map(node => node.textContent)).toEqual(['this', 'older']);
  expect(container.textContent).not.toContain('My note'); expect(container.querySelector('.collection-context')).toBeNull();
  await click('显示上下文');
  expect(container.querySelector('.collection-context')?.textContent).toBe('原句：A😀 this phrase.');
  expect(container.querySelector('.collection-context mark')?.textContent).toBe('this');
  expect(container.textContent).not.toContain('My note');
  await click('显示备注'); expect(container.textContent).toContain('My note'); expect(container.textContent).toContain('旧字幕版本');
  await click('显示上下文'); expect(container.querySelector('.collection-context')).toBeNull();
  expect(container.textContent).toContain('My note');
});

it('keeps question context and answers independently visible without changing output defaults', async () => {
  await renderQuestions(); await click('全部（1）');
  expect(container.querySelector('.collection-context')).toBeNull(); expect(container.querySelector('.collection-answer')).toBeNull();
  await click('显示解答'); expect(container.querySelector('.collection-answer')?.textContent).toContain(question.answer);
  expect(container.querySelector('.collection-context')).toBeNull();
  await click('显示上下文'); expect(container.querySelector('.collection-context mark')?.textContent).toBe('this');
  await click('显示解答'); expect(container.querySelector('.collection-answer')).toBeNull();
  expect(container.querySelector('.collection-context')).not.toBeNull();
  await click('复制');
  expect(writeText.mock.lastCall?.[0]).toContain('表达：this'); expect(writeText.mock.lastCall?.[0]).toContain('原句：A😀 this phrase.');
  expect(writeText.mock.lastCall?.[0]).toContain(question.question); expect(writeText.mock.lastCall?.[0]).not.toContain(question.answer);
  await click('显示上下文'); expect(checkbox('包含上下文').checked).toBe(true);
});

it('uses independent output settings for single and bulk copies regardless of favorite display state', async () => {
  await renderFavorites(); await click('显示上下文'); await click('复制');
  expect(writeText.mock.lastCall?.[0]).toContain('原句：A😀 this phrase.'); expect(writeText.mock.lastCall?.[0]).not.toContain('My note');
  await click('显示上下文');
  await act(async () => checkbox('包含备注').click());
  await click('复制全部收藏');
  const content = writeText.mock.lastCall?.[0];
  expect(content).toContain('Video'); expect(content).toContain('1.\n表达：this');
  expect(content).toContain('2.\n表达：older'); expect(content).not.toContain('字幕版本'); expect(content).toContain('原句：A😀 this phrase.'); expect(content).toContain('备注：My note');
  expect(container.querySelector('.collection-note')).toBeNull();
});

it('includes a hidden answer only when requested, and re-reads updated answers', async () => {
  await renderQuestions(); await click('全部（1）'); await act(async () => checkbox('包含解答').click());
  await click('复制'); expect(writeText.mock.lastCall?.[0]).toContain(question.answer);
  expect(container.querySelector('.collection-answer')).toBeNull();
  await renderQuestions([{ ...question, answer: 'Updated answer' }]);
  await click('显示解答'); expect(container.querySelector('.collection-answer')?.textContent).toContain('Updated answer');
  await renderQuestions([{ ...question, answer: null }]);
  expect(container.querySelector('.collection-answer')?.textContent).toContain('尚未添加');
  expect(container.textContent).toContain('添加解答');
});

it('replays the old record at its original time and reports unavailable playback', async () => {
  await renderFavorites(); await click('显示上下文');
  await click('回听旧版'); expect(replay).toHaveBeenCalledWith(2);
  replay.mockReturnValueOnce(false); await click('回听旧版');
  expect(container.querySelector('[role=alert]')?.textContent).toContain('播放器尚未就绪');
});

it('routes editing to the fixed editor and confirms deletion, retains failed delete for retry', async () => {
  await renderFavorites([current]); await click('编辑备注'); expect(editNote).toHaveBeenCalledWith(current, expect.any(HTMLButtonElement));
  expect(container.querySelector('textarea')).toBeNull();
  await click('取消收藏'); expect(remove).not.toHaveBeenCalled();
  remove.mockRejectedValueOnce(new Error('Delete failed'));
  await click('确认取消收藏'); expect(container.querySelector('[role=alert]')?.textContent).toContain('Delete failed');
  await click('确认取消收藏'); expect(remove).toHaveBeenCalledWith('current-mark');
  expect(container.textContent).toContain('已取消收藏');
});

it('edits independent questions and answers and deletes only the chosen question', async () => {
  await renderQuestions(); await click('全部（1）'); await click('编辑问题'); expect(editQuestion).toHaveBeenCalledWith(question, expect.any(HTMLButtonElement));
  await click('编辑解答'); expect(editAnswer).toHaveBeenCalledWith(question, expect.any(HTMLButtonElement));
  await click('删除问题'); await click('取消删除'); expect(remove).not.toHaveBeenCalled();
  await click('删除问题'); await click('确认删除问题'); expect(remove).toHaveBeenCalledWith(question.id);
});

it('reports clipboard failures and retains records and output settings', async () => {
  writeText.mockRejectedValueOnce(new Error('Denied')); await renderQuestions(); await click('全部（1）'); await click('复制');
  expect(container.querySelector('[role=alert]')?.textContent).toContain('剪贴板权限');
  expect(container.querySelector('.collection-question')?.textContent).toBe(question.question);
  expect(checkbox('包含上下文').checked).toBe(true); await click('复制'); expect(container.querySelector('[role=alert]')).toBeNull();
});

it('disables mutations during editing and outputs while loading, empty or unreadable', async () => {
  await renderQuestions([{ ...question, answer: null }], { editingDisabled: true });
  for (const label of ['编辑问题', '添加解答', '删除问题']) expect([...container.querySelectorAll('button')].find(button => button.textContent === label)?.disabled).toBe(true);
  await renderQuestions([], { loading: true }); expect(container.textContent).toContain('正在读取提问');
  expect([...container.querySelectorAll('button')].find(button => button.textContent === '复制待解答问题')?.disabled).toBe(true);
  await renderQuestions([], { loadError: 'Unavailable' }); await click('重试读取'); expect(common.onRetry).toHaveBeenCalledOnce();
  await renderQuestions([]); expect(container.textContent).toContain('还没有保存的提问');
});

it('always shows the questioned expression beside the question, independently of context and answers', async () => {
  await renderQuestions([{ ...question, selected_text: 'dismantled', question: '什么意思',
    segment_text: 'The old you is being dismantled.', start_offset: 21, end_offset: 31 }]); await click('全部（1）');
  const expression = () => [...container.querySelectorAll('.collection-card .collection-expression')].map(node => node.textContent);
  expect(expression()).toEqual(['dismantled']);
  expect(container.querySelector('.collection-question-line')?.textContent).toBe('dismantled 什么意思');
  expect(container.querySelector('.collection-question')?.textContent).toBe('什么意思');
  expect(container.querySelector('.collection-context')).toBeNull();
  await click('显示上下文');
  expect(container.querySelector('.collection-context')?.textContent).toBe('原句：The old you is being dismantled.');
  expect(expression()).toEqual(['dismantled']);
  await click('显示解答'); await click('显示上下文');
  expect(container.querySelector('.collection-context')).toBeNull();
  expect(expression()).toEqual(['dismantled']);
  expect(container.querySelector('.collection-question')?.textContent).toBe('什么意思');
  expect(container.querySelector('.collection-answer')?.textContent).toContain(question.answer);
});

it('defaults to unanswered, counts questions rather than selections and treats whitespace as empty', async () => {
  const records = [question, { ...question, id: 'pending', answer: null },
    { ...question, id: 'blank', answer: ' \u3000\n' }];
  await renderQuestions(records);
  expect(container.querySelector('.collection-filters [aria-pressed=true]')?.textContent).toBe('待解答（2）');
  expect([...container.querySelectorAll('.collection-card')].map(node => node.getAttribute('data-record-id'))).toEqual(['blank', 'pending']);
  await click('已有解答（1）');
  expect(container.querySelectorAll('.collection-card')).toHaveLength(1);
  await click('全部（3）'); expect(container.querySelectorAll('.collection-card')).toHaveLength(3);
  await renderQuestions(records.map(item => ({ ...item, answer: null })));
  await click('已有解答（0）');
  expect(container.textContent).toContain('没有已有解答的问题');
  expect([...container.querySelectorAll('button')].find(button => button.textContent === '复制已有解答问题')?.disabled).toBe(true);
});

it('limits existing bulk output to the current question filter while single output remains one question', async () => {
  await renderQuestions([question, { ...question, id: 'pending', question: 'Pending question', answer: null }]);
  await click('复制待解答问题');
  expect(writeText.mock.lastCall?.[0]).toContain('Pending question');
  expect(writeText.mock.lastCall?.[0]).not.toContain(question.question);
  await click('全部（2）'); await click('复制');
  expect(writeText.mock.lastCall?.[0]).toContain(question.question);
  expect(writeText.mock.lastCall?.[0]).not.toContain('Pending question');
});

it('links all questions by exact video, revision, segment and Unicode range, independently of context and notes', async () => {
  const related = [question, { ...question, id: 'pending', question: 'Another question', answer: null },
    { ...question, id: 'video', video_id: 'other', question: 'Wrong video' },
    { ...question, id: 'revision', revision_id: 'other', question: 'Wrong revision' },
    { ...question, id: 'segment', segment_id: 'other', question: 'Wrong segment' },
    { ...question, id: 'start', start_offset: 9, end_offset: 13, question: 'Wrong position' },
    { ...question, id: 'end', end_offset: 8, question: 'Wrong end' }];
  await renderFavorites([current], { relatedQuestions: related });
  expect(container.querySelector('.collection-linked-questions')).toBeNull();
  await click('显示问题');
  expect(container.querySelectorAll('[data-question-id]')).toHaveLength(2);
  expect(container.textContent).not.toContain('Wrong');
  expect(container.querySelector('.collection-answer')).toBeNull();
  await click('显示备注'); await click('显示上下文'); await click('显示解答');
  expect(container.querySelectorAll('.collection-context')).toHaveLength(1);
  expect(container.querySelectorAll('.collection-answer')).toHaveLength(2);
  await click('显示问题'); await click('显示上下文');
  expect(container.querySelectorAll('[data-question-id]')).toHaveLength(2);
  expect(container.querySelector('.collection-note')?.textContent).toContain('My note');
  expect(container.querySelector('.collection-context')).toBeNull();
  await click('显示解答'); expect(container.querySelector('.collection-linked-questions')).toBeNull();
});

it('edits and deletes a linked question without cancelling its favorite, with failure retry', async () => {
  const deleteQuestion = vi.fn().mockRejectedValueOnce(new Error('Question delete failed')).mockResolvedValue(undefined);
  await renderFavorites([current], { relatedQuestions: [{ ...question, id: 'q' }], onDeleteQuestion: deleteQuestion });
  await click('显示问题');
  await click('编辑问题'); expect(editQuestion).toHaveBeenCalledWith(expect.objectContaining({ id: 'q' }), expect.any(HTMLButtonElement));
  await click('编辑解答'); expect(editAnswer).toHaveBeenCalledWith(expect.objectContaining({ id: 'q' }), expect.any(HTMLButtonElement));
  await click('删除问题'); await click('确认删除问题');
  expect(container.textContent).toContain('Question delete failed');
  await click('确认删除问题'); expect(deleteQuestion).toHaveBeenCalledWith('q');
  expect(remove).not.toHaveBeenCalled(); expect(container.querySelector('blockquote')?.textContent).toBe('this');
});

it('reports related-data loading and failures without hiding favorites or showing a false empty relation', async () => {
  await renderFavorites([current], { relatedLoading: true }); await click('显示问题');
  expect(container.textContent).toContain('正在读取关联问答');
  expect(container.textContent).not.toContain('尚无关联问题');
  await renderFavorites([current], { relatedError: 'Unavailable' });
  expect(container.textContent).toContain('关联问答读取失败');
  expect(container.querySelector('blockquote')?.textContent).toBe('this');
  await click('重试读取问答'); expect(common.onRetry).toHaveBeenCalled();
  await renderFavorites([current], { relatedQuestions: [{ ...question, id: 'q' }] });
  expect(container.querySelector('[data-question-id=q]')).not.toBeNull();
});

it('uses backend whitespace semantics for legacy answer counts', async () => {
  await renderQuestions([{ ...question, answer: '\u0085\u001c\u001f' },
    { ...question, id: 'bom', answer: '\ufeff' }]);
  expect(container.querySelector('.collection-filters [aria-pressed=true]')?.textContent).toBe('待解答（1）');
  expect(container.querySelector('.collection-card')?.getAttribute('data-record-id')).toBe(question.id);
  await click('已有解答（1）');
  expect(container.querySelector('.collection-card')?.getAttribute('data-record-id')).toBe('bom');
});

it('keeps output options separate from display and reads complete associated questions for favorite output', async () => {
  const answered = { ...question, id: 'answered', answer: 'Saved answer' };
  const pending = { ...question, id: 'pending', question: 'Pending question', answer: null };
  await renderFavorites([current], { relatedQuestions: [answered, pending] });
  await act(async () => checkbox('包含解答').click());
  await click('复制');
  expect(writeText.mock.lastCall?.[0]).toContain('问题：Why this wording?\n解答：Saved answer');
  expect(writeText.mock.lastCall?.[0]).not.toContain('Pending question');
  expect(container.querySelector('.collection-linked-questions')).toBeNull();
  await act(async () => checkbox('包含关联问题').click());
  await click('复制全部收藏'); expect(writeText.mock.lastCall?.[0]).toContain('Pending question');
  expect(writeText.mock.lastCall?.[0].match(/原句：/g)).toHaveLength(1);
  expect(checkbox('包含备注').checked).toBe(false);
  await click('显示备注'); expect(checkbox('包含备注').checked).toBe(false);
});

it('always outputs the question expression and question when original context is deselected', async () => {
  await renderQuestions([{ ...question, answer: null }]);
  await act(async () => checkbox('包含上下文').click());
  await click('复制待解答问题');
  expect(writeText.mock.lastCall?.[0]).toBe('Video\n\n1.\n表达：this\n问题：Why this wording?');
  expect(container.querySelector('.collection-context')).toBeNull();
  expect([...container.querySelectorAll('label')].map(label => label.textContent)).toEqual(['包含上下文', '包含备注', '包含解答']);
});

it('re-reads associated favorite notes, and omits cancelled favorites without affecting question content', async () => {
  await renderQuestions([{ ...question, answer: null }], { relatedMarks: [current] });
  await act(async () => checkbox('包含备注').click()); await click('复制');
  expect(writeText.mock.lastCall?.[0]).toContain('备注：My note');
  await renderQuestions([{ ...question, answer: null }], { relatedMarks: [{ ...current, note: 'Updated note' }] });
  await click('复制'); expect(writeText.mock.lastCall?.[0]).toContain('备注：Updated note');
  await renderQuestions([{ ...question, answer: null }], { relatedMarks: [] });
  await click('复制'); expect(writeText.mock.lastCall?.[0]).not.toContain('备注');
  expect(writeText.mock.lastCall?.[0]).toContain(question.question);
});

it('blocks both single and bulk output when requested relations are unavailable and supports retry', async () => {
  const retry = vi.fn();
  await renderQuestions([{ ...question, answer: null }], { relatedError: 'Read failed', onRetryRelated: retry });
  await click('复制'); expect(writeText).toHaveBeenCalledOnce();
  await act(async () => checkbox('包含备注').click());
  expect(container.textContent).toContain('收藏备注读取失败');
  for (const text of ['复制', '导出 Markdown', '复制待解答问题', '导出待解答问题']) {
    expect([...container.querySelectorAll('button')].find(button => button.textContent === text)?.disabled).toBe(true);
  }
  await click('重试读取收藏'); expect(retry).toHaveBeenCalledOnce();
  await renderQuestions([{ ...question, answer: null }], { relatedMarks: [current] });
  await click('复制'); expect(writeText.mock.lastCall?.[0]).toContain('My note');
  await renderFavorites([current], { relatedLoading: true });
  await act(async () => checkbox('包含解答').click());
  expect(container.textContent).toContain('正在读取关联问答');
  expect([...container.querySelectorAll('button')].find(button => button.textContent === '复制')?.disabled).toBe(true);
});
