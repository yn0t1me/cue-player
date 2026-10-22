import { useState } from 'react';
import type { ChunkLayout, Transcript } from '../../types/video';
import { hasCurrentChunkLayout } from './TranscriptViewSwitch';
import { downloadCollection, formatTranscript } from './collectionOutput';

interface Props {
  transcript: Transcript;
  videoTitle: string;
  layout?: ChunkLayout | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}
export default function TranscriptExportPanel({ transcript, videoTitle, layout, loading, error, onRetry }: Props) {
  const [translation, setTranslation] = useState(false);
  const [chunks, setChunks] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [outputError, setOutputError] = useState<string | null>(null);
  const translationAvailable = transcript.segments.some(segment => Boolean(segment.translation_zh?.trim()));
  const chunksAvailable = hasCurrentChunkLayout(transcript, layout);
  const send = async (download: boolean) => {
    if (loading || error || !transcript.segments.length) return;
    setMessage(null); setOutputError(null);
    try {
      const content = formatTranscript(transcript, videoTitle,
        { translation: translationAvailable && translation, chunks: chunksAvailable && chunks }, layout,
        download ? 'markdown' : 'text');
      if (download) downloadCollection(content, 'transcript', videoTitle);
      else await navigator.clipboard.writeText(content);
      setMessage(download ? '已发起 Markdown 下载。' : '已复制完整字幕。');
    } catch { setOutputError(download ? '导出失败，请重试。' : '复制失败。请检查浏览器剪贴板权限后重试。'); }
  };
  return <div className="transcript-export-tools" aria-label="完整字幕导出">
    {translationAvailable && <label><input type="checkbox" checked={translation}
      onChange={event => setTranslation(event.target.checked)} />包含中文</label>}
    {chunksAvailable && <label><input type="checkbox" checked={chunks}
      onChange={event => setChunks(event.target.checked)} />包含词块</label>}
    <button disabled={loading || !!error || !transcript.segments.length} onClick={() => void send(false)}>复制完整字幕</button>
    <button disabled={loading || !!error || !transcript.segments.length} onClick={() => void send(true)}>导出字幕 Markdown</button>
    {error && <p role="alert">{error}<button onClick={onRetry}>重试读取</button></p>}
    {outputError && <p role="alert">{outputError}</p>}{message && <p role="status">{message}</p>}
  </div>;
}
