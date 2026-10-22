import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../../api/client';
import type { CreateTranscriptMark, TranscriptMark } from '../../types/video';

export interface ReaderSelection {
  anchor: CreateTranscriptMark;
  trigger: HTMLElement;
  rect: DOMRect;
  keyboard: boolean;
}
interface Options {
  createFavorite: (anchor: CreateTranscriptMark) => Promise<{ item: TranscriptMark; created: boolean }>;
  deleteFavorite: (id: string) => Promise<unknown>;
  onConflict: () => void;
}
export function useReaderFavorites(options: Options) {
  const [selection, setSelection] = useState<ReaderSelection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [undoId, setUndoId] = useState<string | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const restoreFocus = () => window.requestAnimationFrame(() => {
    if (!alive.current) return;
    if (trigger.current?.isConnected) trigger.current.focus({ preventScroll: true });
    else document.getElementById('reading-tab-transcript')?.focus({ preventScroll: true });
  });
  const clear = () => { setSelection(null); setError(null); window.getSelection()?.removeAllRanges(); };
  const guard = (action: () => void): boolean => {
    if (busy) return false;
    clear(); action(); return true;
  };
  const fail = (reason: unknown) => {
    setError(reason instanceof Error ? reason.message : '保存失败，请重试。');
    if (reason instanceof ApiError && reason.code === 'TRANSCRIPT_REVISION_CONFLICT') options.onConflict();
  };
  const quickFavorite = async () => {
    if (!selection || busy) return;
    setBusy(true); setError(null); setUndoId(null);
    try {
      const result = await options.createFavorite(selection.anchor);
      if (!alive.current) return;
      setNotice(result.created ? '已收藏。' : '已收藏过这段文字。');
      if (result.created) setUndoId(result.item.id);
      clear(); restoreFocus();
    } catch (reason) { if (alive.current) fail(reason); }
    finally { if (alive.current) setBusy(false); }
  };
  const openSelection = (next: ReaderSelection) => {
    if (selection && selection.anchor.revision_id === next.anchor.revision_id
      && selection.anchor.segment_id === next.anchor.segment_id
      && selection.anchor.start_offset === next.anchor.start_offset
      && selection.anchor.end_offset === next.anchor.end_offset) {
      if (next.keyboard) document.querySelector<HTMLButtonElement>('.reader-selection-menu button')?.focus();
      return;
    }
    guard(() => { trigger.current = next.trigger; setSelection(next); setNotice(null); setUndoId(null); });
  };
  const controls = <>
    {selection && <SelectionMenu selection={selection} busy={busy} error={error}
      onClose={() => guard(restoreFocus)} onFavorite={() => void quickFavorite()} />}
    {!selection && notice && <AutoDismissNotice notice={notice} paused={busy || !!error}
      onDismiss={() => { setNotice(null); setUndoId(null); }}>
      <span>{notice}</span>{undoId && <button disabled={busy} onClick={async () => {
        if (busy) return;
        setBusy(true); setError(null);
        try {
          await options.deleteFavorite(undoId);
          if (alive.current) { setUndoId(null); setNotice('已撤销本次收藏。'); }
        } catch (reason) { if (alive.current) fail(reason); }
        finally { if (alive.current) setBusy(false); }
      }}>撤销</button>}
      <button disabled={busy} aria-label="关闭提示" onClick={() => { setNotice(null); setError(null); }}>×</button>
      {error && <p role="alert">{error}</p>}
    </AutoDismissNotice>}
  </>;
  return { controls, guard, openSelection, suspended: !!selection,
    invalidSelection: () => guard(() => setNotice('一次只能选择同一条字幕内的文字，请重新选择。')) };
}

function SelectionMenu({ selection, busy, error, onClose, onFavorite }: {
  selection: ReaderSelection; busy: boolean; error: string | null;
  onClose: () => void; onFavorite: () => void;
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
    <div><button disabled={busy} onClick={onFavorite}>收藏</button><button disabled={busy} aria-label="关闭选字菜单" onClick={onClose}>×</button></div>
    {error && <p role="alert">{error}</p>}
  </div>;
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
