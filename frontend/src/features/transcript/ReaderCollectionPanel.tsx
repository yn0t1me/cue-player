import { useState } from 'react';
import type { TranscriptMark, TranscriptQuestion } from '../../types/video';
import { formatTranscriptTime } from './TranscriptPanel';
import { defaultOutputOptions, downloadCollection, formatCollection, orderedEntries,
  type CollectionEntry } from './collectionOutput';
import { filterQuestions, hasAnswer, questionFilterLabels, questionsBySelection, selectionKey,
  type QuestionFilter } from './noteRelations';

interface CommonProps {
  videoTitle: string;
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
  onReplay: (start: number) => boolean;
  editingDisabled: boolean;
  onDelete: (id: string) => Promise<void>;
  relatedLoading: boolean;
  relatedError: string | null;
  onRetryRelated: () => void;
  onEditQuestion: (item: TranscriptQuestion, trigger: HTMLElement) => void;
  onEditAnswer: (item: TranscriptQuestion, trigger: HTMLElement) => void;
}
type Props = CommonProps & ({
  kind: 'favorites'; items: TranscriptMark[];
  relatedQuestions: TranscriptQuestion[];
  onDeleteQuestion: (id: string) => Promise<void>;
  onEditNote: (item: TranscriptMark, trigger: HTMLElement) => void;
} | {
  kind: 'questions'; items: TranscriptQuestion[]; relatedMarks: TranscriptMark[];
});

function Context({ item }: { item: CollectionEntry }) {
  const characters = Array.from(item.segment_text);
  return <p className="collection-context">原句：{characters.slice(0, item.start_offset).join('')}
    <mark>{characters.slice(item.start_offset, item.end_offset).join('')}</mark>
    {characters.slice(item.end_offset).join('')}</p>;
}

export default function ReaderCollectionPanel(props: Props) {
  const { kind, items, videoTitle, loading, loadError, onRetry, onReplay, editingDisabled, onDelete } = props;
  const favorite = kind === 'favorites';
  const label = favorite ? '收藏' : '提问';
  const [showContext, setShowContext] = useState(false);
  const [showAnswers, setShowAnswers] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [showQuestions, setShowQuestions] = useState(false);
  const [filter, setFilter] = useState<QuestionFilter>('unanswered');
  const visibleItems = props.kind === 'questions' ? filterQuestions(props.items, filter) : items;
  const related = questionsBySelection(props.kind === 'favorites' ? props.relatedQuestions : []);
  const counts = props.kind === 'questions' ? {
    all: props.items.length, answered: props.items.filter(hasAnswer).length,
    unanswered: props.items.filter(item => !hasAnswer(item)).length,
  } : null;
  const [output, setOutput] = useState(() => defaultOutputOptions());
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const groups = new Map<string, CollectionEntry[]>();
  for (const item of orderedEntries<CollectionEntry>(visibleItems)) {
    const group = groups.get(item.revision_id) ?? [];
    group.push(item); groups.set(item.revision_id, group);
  }
  const outputNeedsRelated = favorite ? output.questions || output.answers : output.notes;
  const outputRelatedUnavailable = outputNeedsRelated && (props.relatedLoading || !!props.relatedError);
  const outputDisabled = outputRelatedUnavailable || loading || !!loadError || visibleItems.length === 0;
  const editDisabled = editingDisabled || busyId !== null;
  const sendOutput = async (records: CollectionEntry[], download: boolean) => {
    if (outputDisabled) return;
    setMessage(null); setError(null);
    try {
      const content = formatCollection(records, kind, videoTitle, output, download ? 'markdown' : 'text',
        props.kind === 'favorites' ? { questions: props.relatedQuestions } : { marks: props.relatedMarks });
      if (download) downloadCollection(content, kind, videoTitle);
      else await navigator.clipboard.writeText(content);
      setMessage(download ? '已发起 Markdown 下载。' : `已复制${records.length > 1 ? '所选' : '这条'}${label}。`);
    } catch {
      setError(download ? '导出失败，请重试。' : '复制失败。请检查浏览器剪贴板权限后重试。');
    }
  };
  const remove = async (id: string, linkedQuestion = false) => {
    if (editDisabled) return;
    setBusyId(id); setError(null); setMessage(null);
    try {
      if (linkedQuestion && props.kind === 'favorites') await props.onDeleteQuestion(id);
      else await onDelete(id);
      setConfirmDeleteId(null); setMessage(linkedQuestion ? '问题已删除。' : favorite ? '已取消收藏。' : '提问已删除。');
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : '删除失败，请重试。'); }
    finally { setBusyId(null); }
  };
  const questionActions = (item: TranscriptQuestion, linked = false) => <div className="collection-card-actions">
    <button type="button" disabled={editDisabled} onClick={event => props.onEditQuestion(item, event.currentTarget)}>编辑问题</button>
    <button type="button" disabled={editDisabled} onClick={event => props.onEditAnswer(item, event.currentTarget)}>{hasAnswer(item) ? '编辑解答' : '添加解答'}</button>
    {confirmDeleteId === item.id ? <>
      <button type="button" disabled={editDisabled} onClick={() => void remove(item.id, linked)}>确认删除问题</button>
      <button type="button" disabled={busyId !== null} onClick={() => setConfirmDeleteId(null)}>取消删除</button>
    </> : <button type="button" disabled={editDisabled} onClick={() => setConfirmDeleteId(item.id)}>删除问题</button>}
  </div>;
  return <aside className={`collection-panel ${kind}-panel`} aria-labelledby={`collection-title-${kind}`}>
    <div className="collection-heading"><h2 id={`collection-title-${kind}`}>我的{label}</h2>
      <span aria-label={`${items.length} 条${label}`}>{String(items.length).padStart(2, '0')}</span></div>
    {counts && <div className="collection-filters" role="group" aria-label="提问筛选" aria-busy={loading}>
      {(['all', 'unanswered', 'answered'] as const).map(value => <button type="button" key={value}
        aria-pressed={filter === value} disabled={editingDisabled || busyId !== null || loading || !!loadError}
        onClick={() => { setFilter(value); setConfirmDeleteId(null); setMessage(null); setError(null); }}>
        {questionFilterLabels[value]}（{loading || loadError ? '—' : counts[value]}）</button>)}
    </div>}
    <div className="collection-toolbar">
    <div className="collection-view-controls" aria-label={`${label}显示选项`}>
      <button type="button" aria-pressed={showContext} onClick={() => setShowContext(value => !value)}>显示上下文</button>
      {favorite && <>
        <button type="button" aria-pressed={showNotes} onClick={() => setShowNotes(value => !value)}>显示备注</button>
        <button type="button" aria-pressed={showQuestions} onClick={() => setShowQuestions(value => !value)}>显示问题</button>
      </>}
      <button type="button" aria-pressed={showAnswers} onClick={() => setShowAnswers(value => !value)}>显示解答</button>
    </div>
    <div className="collection-output-tools">
      <button type="button" disabled={outputDisabled} onClick={() => void sendOutput(visibleItems, false)}>{favorite ? '复制全部收藏' : `复制${questionFilterLabels[filter]}问题`}</button>
      <button type="button" disabled={outputDisabled} onClick={() => void sendOutput(visibleItems, true)}>{favorite ? '导出全部 Markdown' : `导出${questionFilterLabels[filter]}问题`}</button>
    </div>
    </div>
    <details className="collection-output-options"><summary>复制与导出选项</summary>
      <fieldset><legend>输出内容</legend>
        <label><input type="checkbox" checked={output.context}
          onChange={event => setOutput(value => ({ ...value, context: event.target.checked }))} />包含上下文</label>
        <label><input type="checkbox" checked={output.notes}
          onChange={event => setOutput(value => ({ ...value, notes: event.target.checked }))} />包含备注</label>
        {favorite && <label><input type="checkbox" checked={output.questions}
          onChange={event => setOutput(value => ({ ...value, questions: event.target.checked }))} />包含关联问题</label>}
        <label><input type="checkbox" checked={output.answers}
          onChange={event => setOutput(value => ({ ...value, answers: event.target.checked }))} />包含解答</label>
      </fieldset><p>表达{!favorite && '和问题'}始终包含；单条与批量共用选项，不受页面显隐影响。
        {favorite && '包含解答时会附带对应问题。'}</p>
    </details>
    {message && <p className="collection-message" role="status">{message}</p>}
    {error && <p className="collection-error" role="alert">{error}</p>}
    {loadError && <div className="collection-error" role="alert">{loadError}
      <button type="button" onClick={onRetry}>重试读取</button></div>}
    {loading && <p role="status">正在读取{label}…</p>}
    {!loading && !loadError && items.length === 0 && <p className="collection-empty">还没有保存的{label}。在字幕中选字或点“整句”开始记录。</p>}
    {!loading && !loadError && items.length > 0 && visibleItems.length === 0 &&
      <p className="collection-empty">没有{questionFilterLabels[filter]}的问题，可切换筛选查看。</p>}
    {((favorite && (showQuestions || showAnswers)) || outputNeedsRelated) && <>
      {props.relatedLoading && <p role="status">正在读取{favorite ? '关联问答' : '收藏备注'}…</p>}
      {props.relatedError && <div className="collection-error" role="alert">{favorite ? '关联问答' : '收藏备注'}读取失败：{props.relatedError}
        <button type="button" onClick={props.onRetryRelated}>{favorite ? '重试读取问答' : '重试读取收藏'}</button></div>}
    </>}
    {[...groups.values()].map(group => {
      const first = group[0];
      return <section className="collection-group" key={first.revision_id}
        aria-label={`字幕版本 ${first.revision_number}${first.is_current ? '，当前' : '，旧版'}`}>
        <div className="collection-group-heading"><h3>字幕版本 #{first.revision_number}</h3>
          <span>{first.is_current ? '当前字幕' : '旧字幕版本'}</span></div>
        <ol>{group.map(item => <li className="collection-card" key={item.id} data-record-id={item.id}>
          <time dateTime={`PT${item.segment_start}S`}>{formatTranscriptTime(item.segment_start)}</time>
          {'question' in item ? <p className="collection-question-line"><span className="collection-expression">{item.selected_text}</span>{' '}<span className="collection-question">{item.question}</span></p>
            : <blockquote>{item.selected_text}</blockquote>}
          {showContext && <div className="collection-context-block">
            <Context item={item} />
            <button type="button" aria-label={`从 ${formatTranscriptTime(item.segment_start)} 回听${first.is_current ? '' : '旧版'}${label}`}
              onClick={() => {
                if (!onReplay(item.segment_start)) setError('播放器尚未就绪，请等待加载完成或先处理播放错误。');
                else setError(null);
              }}>回听{first.is_current ? '' : '旧版'}</button>
          </div>}
          {!('question' in item) && showNotes && item.note && <p className="collection-note"><span>备注</span>{item.note}</p>}
          {props.kind === 'favorites' && (showQuestions || showAnswers) && !props.relatedLoading && !props.relatedError &&
            <div className="collection-linked-questions" aria-label="关联问答">
              {(related.get(selectionKey(item)) ?? []).length === 0 && <p>尚无关联问题。</p>}
              <ol>{orderedEntries(related.get(selectionKey(item)) ?? []).map(question => <li key={question.id} data-question-id={question.id}>
                <p className="collection-question">{question.question}</p>
                {showAnswers && <div className="collection-answer"><span>解答</span>
                  <p>{hasAnswer(question) ? question.answer : '尚未添加解答。'}</p></div>}
                {questionActions(question, true)}
              </li>)}</ol>
            </div>}
          {'question' in item && showAnswers && <div className="collection-answer">
            <span>解答</span><p>{hasAnswer(item) ? item.answer : '尚未添加解答。'}</p></div>}
          <div className="collection-card-actions">
            <button type="button" disabled={outputDisabled} onClick={() => void sendOutput([item], false)}>复制</button>
            <button type="button" disabled={outputDisabled} onClick={() => void sendOutput([item], true)}>导出 Markdown</button>
            {props.kind === 'favorites' && 'note' in item && <button type="button" disabled={editDisabled}
              onClick={event => props.onEditNote(item, event.currentTarget)}>编辑备注</button>}
            {!('question' in item) && (confirmDeleteId === item.id ? <>
              <button type="button" disabled={editDisabled} onClick={() => void remove(item.id)}>确认取消收藏</button>
              <button type="button" disabled={busyId !== null} onClick={() => setConfirmDeleteId(null)}>保留收藏</button>
            </> : <button type="button" disabled={editDisabled} onClick={() => setConfirmDeleteId(item.id)}>取消收藏</button>)}
          </div>
          {'question' in item && questionActions(item)}
        </li>)}</ol>
      </section>;
    })}
  </aside>;
}
