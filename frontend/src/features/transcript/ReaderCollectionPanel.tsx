import { useState } from 'react';
import type { TranscriptMark } from '../../types/video';
import { formatTranscriptTime } from './TranscriptPanel';
import { downloadCollection, formatCollection, orderedEntries } from './collectionOutput';

interface Props {
  items: TranscriptMark[];
  videoTitle: string;
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
  onReplay: (time: number) => boolean;
  onDelete: (id: string) => Promise<unknown>;
  editingDisabled?: boolean;
}
export default function ReaderCollectionPanel({ items, videoTitle, loading, loadError, onRetry,
  onReplay, onDelete, editingDisabled = false }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const disabled = loading || !!loadError || busyId !== null;
  const sendOutput = async (records: TranscriptMark[], download: boolean) => {
    if (disabled || !records.length) return;
    setMessage(null); setError(null);
    try {
      const content = formatCollection(records, videoTitle, download ? 'markdown' : 'text');
      if (download) downloadCollection(content, 'favorites', videoTitle);
      else await navigator.clipboard.writeText(content);
      setMessage(download ? '已发起 Markdown 下载。' : '已复制收藏表达。');
    } catch { setError(download ? '导出失败，请重试。' : '复制失败。请检查浏览器剪贴板权限后重试。'); }
  };
  const remove = async (id: string) => {
    if (disabled || editingDisabled) return;
    setBusyId(id); setMessage(null); setError(null);
    try { await onDelete(id); setConfirmId(null); setMessage('已取消收藏。'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '取消收藏失败，请重试。'); }
    finally { setBusyId(null); }
  };
  const groups = new Map<string, TranscriptMark[]>();
  for (const item of [...items].sort((a, b) => Number(b.is_current) - Number(a.is_current)
    || b.revision_number - a.revision_number || a.segment_start - b.segment_start || a.start_offset - b.start_offset)) {
    const group = groups.get(item.revision_id) ?? []; group.push(item); groups.set(item.revision_id, group);
  }
  return <aside className="collection-panel favorites-panel" aria-labelledby="collection-title-favorites">
    <div className="collection-heading"><h2 id="collection-title-favorites">我的收藏</h2><span>{items.length}</span></div>
    <div className="collection-output-tools">
      <button disabled={disabled || !items.length} onClick={() => void sendOutput(orderedEntries(items), false)}>复制全部收藏</button>
      <button disabled={disabled || !items.length} onClick={() => void sendOutput(orderedEntries(items), true)}>导出全部 Markdown</button>
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    {loadError && <div role="alert">{loadError}<button onClick={onRetry}>重试读取</button></div>}
    {loading && <p role="status">正在读取收藏…</p>}
    {!loading && !loadError && !items.length && <p className="collection-empty">还没有收藏。在字幕中选中表达即可收藏。</p>}
    {!loading && !loadError && [...groups.values()].map(group => <section className="collection-group" key={group[0].revision_id}
      aria-label={`字幕版本 ${group[0].revision_number}${group[0].is_current ? '，当前' : '，旧版'}`}>
      <div className="collection-group-heading"><h3>字幕版本 #{group[0].revision_number}</h3>
        <span>{group[0].is_current ? '当前字幕' : '旧字幕版本'}</span></div>
      <ol>{group.map(item => <li className="collection-card" key={item.id} data-record-id={item.id}>
        <time dateTime={`PT${item.segment_start}S`}>{formatTranscriptTime(item.segment_start)}</time>
        <blockquote>{item.selected_text}</blockquote><p className="collection-context-block">{item.segment_text}</p>
        <div className="collection-card-actions">
          <button onClick={() => setError(onReplay(item.segment_start) ? null : '播放器尚未就绪，请等待加载完成或先处理播放错误。')}>回听{item.is_current ? '' : '旧版'}</button>
          <button disabled={disabled} onClick={() => void sendOutput([item], false)}>复制</button>
          <button disabled={disabled} onClick={() => void sendOutput([item], true)}>导出 Markdown</button>
          {confirmId === item.id ? <>
            <button disabled={disabled || editingDisabled} onClick={() => void remove(item.id)}>确认取消收藏</button>
            <button disabled={busyId !== null} onClick={() => setConfirmId(null)}>保留收藏</button>
          </> : <button disabled={disabled || editingDisabled} onClick={() => setConfirmId(item.id)}>取消收藏</button>}
        </div>
      </li>)}</ol>
    </section>)}
  </aside>;
}
