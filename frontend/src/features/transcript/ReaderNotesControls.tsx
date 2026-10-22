import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../../api/client';
import type { CreateTranscriptMark, TranscriptMark, TranscriptQuestion } from '../../types/video';

export interface ReaderSelection {
  anchor: CreateTranscriptMark;
  trigger: HTMLElement;
  rect: DOMRect;
  keyboard: boolean;
}
type Editor = { kind: 'note'; anchor: CreateTranscriptMark; mark?: TranscriptMark }
  | { kind: 'question'; anchor: CreateTranscriptMark; record?: TranscriptQuestion; answerOnly?: boolean };
interface Options {
  marks: TranscriptMark[];
  createFavorite: (anchor: CreateTranscriptMark) => Promise<{ item: TranscriptMark; created: boolean }>;
  updateNote: (id: string, note: string | null) => Promise<unknown>;
  deleteFavorite: (id: string) => Promise<unknown>;
  createQuestion: (anchor: CreateTranscriptMark, question: string, answer: string | null) => Promise<unknown>;
  updateQuestion: (id: string, patch: { question?: string; answer?: string | null }) => Promise<unknown>;
  onConflict: () => void;
}
function anchorOf(record: TranscriptMark | TranscriptQuestion): CreateTranscriptMark {
  return { revision_id: record.revision_id, segment_id: record.segment_id,
    start_offset: record.start_offset, end_offset: record.end_offset, selected_text: record.selected_text };
}
export function useReaderNotes(options: Options) {
  const [selection, setSelection] = useState<ReaderSelection | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [text, setText] = useState('');
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [undoId, setUndoId] = useState<string | null>(null);
  const [pending, setPending] = useState<(() => void) | null>(null);
  const original = useRef({ text: '', answer: '' });
  const trigger = useRef<HTMLElement | null>(null);
  const dirty = !!editor && (text !== original.current.text || answer !== original.current.answer);
  const restoreFocus = () => window.requestAnimationFrame(() => {
    if (trigger.current?.isConnected) trigger.current.focus({ preventScroll: true });
    else document.getElementById('reading-tab-transcript')?.focus({ preventScroll: true });
  });
  const clear = () => { setEditor(null); setSelection(null); setError(null); window.getSelection()?.removeAllRanges(); };
  const guard = (action: () => void): boolean => {
    if (busy) return false;
    if (dirty) { setPending(() => action); return false; }
    clear(); action(); return true;
  };
  const close = () => guard(restoreFocus);
  useEffect(() => {
    if (!dirty) return;
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [dirty]);
  const fail = (reason: unknown) => {
    setError(reason instanceof Error ? reason.message : '保存失败，请重试。');
    if (reason instanceof ApiError && reason.code === 'TRANSCRIPT_REVISION_CONFLICT') options.onConflict();
  };
  const startEditor = (next: Editor, source: HTMLElement) => guard(() => {
    trigger.current = source;
    const initialText = next.kind === 'note' ? next.mark?.note ?? '' : next.record?.question ?? '';
    const initialAnswer = next.kind === 'question' ? next.record?.answer ?? '' : '';
    original.current = { text: initialText, answer: initialAnswer };
    setText(initialText); setAnswer(initialAnswer); setEditor(next); setNotice(null); setUndoId(null);
  });
  const quickFavorite = async () => {
    if (!selection || busy) return;
    setBusy(true); setError(null); setUndoId(null);
    try {
      const result = await options.createFavorite(selection.anchor);
      setNotice(result.created ? '已收藏。' : '已收藏过这段文字，原备注已保留。');
      if (result.created) setUndoId(result.item.id);
      clear(); restoreFocus();
    } catch (reason) { fail(reason); } finally { setBusy(false); }
  };
  const save = async () => {
    if (!editor || busy) return;
    if (editor.kind === 'question' && !text.trim()) { setError('请填写问题。'); return; }
    setBusy(true); setError(null);
    try {
      if (editor.kind === 'note') {
        if (editor.mark) await options.updateNote(editor.mark.id, text.trim() ? text : null);
        else {
          const result = await options.createFavorite({ ...editor.anchor, note: text.trim() ? text : null });
          // A concurrent create must never silently replace an existing note.
          if (!result.created) {
            setEditor({ ...editor, mark: result.item });
            setNotice('这段文字已收藏。你的草稿已保留，再次保存将修改现有备注。');
            return;
          }
          setUndoId(result.item.id);
        }
      } else if (editor.record) {
        await options.updateQuestion(editor.record.id, editor.answerOnly
          ? { answer: answer.trim() ? answer : null }
          : { question: text, answer: answer.trim() ? answer : null });
      } else await options.createQuestion(editor.anchor, text, answer.trim() ? answer : null);
      setNotice(editor.kind === 'note' ? '备注已保存。' : '提问和解答已保存。');
      clear(); restoreFocus();
    } catch (reason) { fail(reason); } finally { setBusy(false); }
  };
  const openSelection = (next: ReaderSelection) => {
    if (selection && selection.anchor.segment_id === next.anchor.segment_id
      && selection.anchor.start_offset === next.anchor.start_offset
      && selection.anchor.end_offset === next.anchor.end_offset) {
      if (next.keyboard) document.querySelector<HTMLButtonElement>('.reader-selection-menu button')?.focus();
      return;
    }
    guard(() => { trigger.current = next.trigger; setSelection(next); setNotice(null); setUndoId(null); });
  };
  useEffect(() => {
    if (!pending) return;
    const contain = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || event.target.closest('.reader-draft-decision')) return;
      event.preventDefault(); event.stopPropagation();
    };
    document.addEventListener('click', contain, true);
    return () => document.removeEventListener('click', contain, true);
  }, [pending]);
  const controls = <>
    {selection && <SelectionMenu selection={selection} busy={busy} error={error}
      onClose={close} onFavorite={() => void quickFavorite()}
      onNote={() => {
        const mark = options.marks.filter(item => item.revision_id === selection.anchor.revision_id
          && item.segment_id === selection.anchor.segment_id && item.start_offset === selection.anchor.start_offset
          && item.end_offset === selection.anchor.end_offset)
          .sort((a, b) => Number(!!b.note?.trim()) - Number(!!a.note?.trim())
            || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))[0];
        startEditor({ kind: 'note', anchor: selection.anchor, mark }, selection.trigger);
      }} onQuestion={() => startEditor({ kind: 'question', anchor: selection.anchor }, selection.trigger)} />}
    {editor && <FixedEditor editor={editor} text={text} answer={answer} busy={busy}
      error={error} notice={notice} onText={setText} onAnswer={setAnswer} onSave={() => void save()} onClose={close} />}
    {!editor && !selection && notice && <AutoDismissNotice notice={notice} paused={busy || !!error} onDismiss={() => { setNotice(null); setUndoId(null); }}>
      <span>{notice}</span>{undoId && <button disabled={busy} onClick={async () => {
        if (busy) return; setBusy(true); setError(null);
        try { await options.deleteFavorite(undoId); setUndoId(null); setNotice('已撤销本次收藏。'); }
        catch (reason) { fail(reason); } finally { setBusy(false); }
      }}>撤销</button>}
      <button disabled={busy} aria-label="关闭提示" onClick={() => { setNotice(null); setError(null); }}>×</button>
      {error && <p role="alert">{error}</p>}
    </AutoDismissNotice>}
    {pending && <DraftDecision onKeep={() => { setPending(null); }} onDiscard={() => {
      const action = pending; setPending(null); clear(); action();
    }} />}
  </>;
  return { controls, invalidSelection: () => guard(() => setNotice('一次只能选择同一条字幕内的文字，请重新选择。')), suspended: !!selection || !!editor, guard, openSelection,
    editNote: (mark: TranscriptMark, source: HTMLElement) => startEditor({ kind: 'note', anchor: anchorOf(mark), mark }, source),
    editQuestion: (record: TranscriptQuestion, source: HTMLElement, answerOnly = false) =>
      startEditor({ kind: 'question', anchor: anchorOf(record), record, answerOnly }, source) };
}

function SelectionMenu({ selection, busy, error, onClose, onFavorite, onNote, onQuestion }: {
  selection: ReaderSelection; busy: boolean; error: string | null;
  onClose: () => void; onFavorite: () => void; onNote: () => void; onQuestion: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 8, top: 48 });
  useLayoutEffect(() => {
    const element = ref.current;
    const host = element?.parentElement;
    if (!element || !host) return;
    const place = () => {
      const bounds = host.getBoundingClientRect();
      const menu = element.getBoundingClientRect();
      const viewport = window.visualViewport;
      const minY = Math.max(bounds.top + 46, viewport?.offsetTop ?? 0);
      const maxY = Math.min(bounds.bottom, (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight));
      const below = selection.rect.bottom + 6;
      const top = below + menu.height <= maxY - 8 ? below : selection.rect.top - menu.height - 6;
      setPosition({ left: Math.max(8, Math.min(selection.rect.left - bounds.left, bounds.width - menu.width - 8)),
        top: Math.max(minY + 8, Math.min(top, maxY - menu.height - 8)) - bounds.top });
    };
    place(); window.addEventListener('resize', place); window.visualViewport?.addEventListener('resize', place);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(place);
    observer?.observe(element); observer?.observe(host);
    if (selection.keyboard) element.querySelector('button')?.focus();
    return () => { observer?.disconnect(); window.removeEventListener('resize', place);
      window.visualViewport?.removeEventListener('resize', place); };
  }, [selection]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); onClose(); } };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  });
  return <div ref={ref} className="reader-selection-menu" role="dialog" aria-label={`已选：${selection.anchor.selected_text}`}
    style={position} onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const buttons = [...event.currentTarget.querySelectorAll('button')];
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : (index + (event.key === 'ArrowLeft' ? buttons.length - 1 : 1)) % buttons.length;
      event.preventDefault(); buttons[next]?.focus();
    }}>
    <p title={selection.anchor.selected_text}>已选「{selection.anchor.selected_text}」</p>
    <div><button disabled={busy} onClick={onFavorite}>收藏</button><button disabled={busy} onClick={onNote}>做笔记</button>
      <button disabled={busy} onClick={onQuestion}>提问</button><button disabled={busy} aria-label="关闭选字菜单" onClick={onClose}>×</button></div>
    {error && <p role="alert">{error}</p>}
  </div>;
}
function FixedEditor({ editor, text, answer, busy, error, notice, onText, onAnswer, onSave, onClose }: {
  editor: Editor; text: string; answer: string; busy: boolean; error: string | null; notice: string | null;
  onText: (text: string) => void; onAnswer: (text: string) => void; onSave: () => void; onClose: () => void;
}) {
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => { ref.current?.querySelector('textarea')?.focus({ preventScroll: true }); }, [editor.kind, editor.kind === 'question' && editor.answerOnly]);
  useLayoutEffect(() => {
    const element = ref.current;
    const host = element?.parentElement;
    if (!element || !host) return;
    const measure = () => {
      const bounds = host.getBoundingClientRect();
      const viewport = window.visualViewport;
      const top = Math.max(bounds.top + 48, (viewport?.offsetTop ?? 0) + 8);
      const bottom = Math.min(bounds.bottom - 10, (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight) - 8);
      element.style.top = `${top - bounds.top}px`;
      element.style.maxHeight = `${Math.max(0, bottom - top)}px`;
    };
    measure(); window.addEventListener('resize', measure); window.visualViewport?.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('scroll', measure);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(host);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('resize', measure); window.visualViewport?.removeEventListener('scroll', measure); };
  }, []);
  const title = editor.kind === 'note' ? '编辑备注' : editor.answerOnly ? '编辑解答' : '编辑问题';
  return <form ref={ref} className="reader-fixed-editor" role="dialog" aria-labelledby="reader-editor-title"
    onSubmit={event => { event.preventDefault(); onSave(); }}
    onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); onClose(); } }}>
    <div className="reader-editor-heading"><h2 id="reader-editor-title">{title}</h2>
      <button type="button" disabled={busy} aria-label="关闭编辑" onClick={onClose}>×</button></div>
    <blockquote>{editor.anchor.selected_text}</blockquote>
    {editor.kind === 'question' && editor.answerOnly ? <p className="reader-original-question">{text}</p>
      : <label>{editor.kind === 'note' ? '备注（可选）' : '问题'}
        <textarea value={text} maxLength={10000} rows={3} required={editor.kind === 'question'}
          disabled={busy} onChange={event => onText(event.target.value)} /></label>}
    {editor.kind === 'question' && <label>解答（可选，可清空）
      <textarea value={answer} maxLength={100000} rows={3} disabled={busy} onChange={event => onAnswer(event.target.value)} /></label>}
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    <div className="reader-editor-actions"><button type="submit" disabled={busy}>{busy ? '正在保存…' : '保存'}</button>
      <button type="button" disabled={busy} onClick={onClose}>取消</button><small>编辑时暂停字幕跟随</small></div>
  </form>;
}
function DraftDecision({ onKeep, onDiscard }: { onKeep: () => void; onDiscard: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector('button')?.focus();
    return () => { if (previous?.isConnected) previous.focus({ preventScroll: true }); };
  }, []);
  return <div className="reader-draft-backdrop"><div ref={ref} role="alertdialog" aria-modal="true"
    aria-labelledby="reader-draft-title" className="reader-draft-decision" onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onKeep(); }
      if (event.key === 'Tab') {
        event.preventDefault(); const buttons = [...event.currentTarget.querySelectorAll('button')];
        buttons[document.activeElement === buttons[0] ? 1 : 0]?.focus();
      }
    }}><h2 id="reader-draft-title">保留未保存的草稿？</h2><p>离开编辑会丢弃当前输入。</p>
      <button onClick={onKeep}>继续编辑</button><button onClick={onDiscard}>放弃草稿并继续</button>
    </div></div>;
}

function AutoDismissNotice({ notice, paused, onDismiss, children }: {
  notice: string; paused: boolean; onDismiss: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;
  useEffect(() => {
    const updateFocus = () => setFocused(!!ref.current?.contains(document.activeElement));
    document.addEventListener('focusin', updateFocus);
    document.addEventListener('focusout', updateFocus);
    return () => {
      document.removeEventListener('focusin', updateFocus);
      document.removeEventListener('focusout', updateFocus);
    };
  }, []);
  useEffect(() => {
    if (paused || hovered || focused) return;
    const timer = window.setTimeout(() => dismiss.current(), 5000);
    return () => window.clearTimeout(timer);
  }, [notice, paused, hovered, focused]);
  return <div ref={ref} className="reader-notice" role="status"
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>{children}</div>;
}
