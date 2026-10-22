import { useQuery } from '@tanstack/react-query';
import { useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import {
  getRawSrt, getLearningSource, getLearningSrt, previewSourceLearning, publishSourceLearning,
  getTranscriptRevision,
  getTranscriptRevisions,
} from '../../api/videos';
import type {
  ChunkLayoutState,
  LearningTranscriptPublishResult,
  Transcript, SourceLearningPreview,
} from '../../types/video';
import { sourceLearningPrompt } from './chunkPrompt';
import { formatTranscriptTime } from './TranscriptPanel';

import { transcriptOriginLabel } from '../../types/video';

const MAX_RESULT_BYTES = 1_048_576;

interface Props {
  videoId: string;
  transcript: Transcript;
  chunkState?: ChunkLayoutState;
  chunkLoading: boolean;
  chunkError: string | null;
  onRetryChunks: () => void;
  onReview: (start: number) => boolean;
  onPublished: (result: LearningTranscriptPublishResult) => void;
}

function clock(seconds: number): string {
  const whole = formatTranscriptTime(seconds);
  const millis = Math.round((seconds % 1) * 1000);
  return `${whole}.${String(millis).padStart(3, '0')}`;
}

function timelineKey(segment: { start: number; end: number; text: string }): string {
  return `${Math.round(segment.start * 1000)}|${Math.round(segment.end * 1000)}|${segment.text}`;
}

function ChunkLine({ chunks }: { chunks: string[] }) {
  return <span className="chunk-preview-line">
    {chunks.map((chunk, index) => <span key={`${index}-${chunk}`}>
      {index > 0 && <i aria-hidden="true">/</i>}<b>{chunk}</b>
    </span>)}
  </span>;
}

function Timeline({ label, segments, other, renderText, renderDetails }: {
  label: string;
  segments: Array<{ sequence_index: number; start: number; end: number; text: string }>;
  other: Array<{ start: number; end: number; text: string }>;
  renderText?: (sequenceIndex: number, text: string) => ReactNode;
  renderDetails?: (sequenceIndex: number) => ReactNode;
}) {
  const unchanged = new Set(other.map(timelineKey));
  return <section className="srt-timeline" aria-label={label}>
    <div className="srt-timeline-heading"><h3>{label}</h3><span>{segments.length} 段</span></div>
    <ol>{segments.map(segment => <li key={segment.sequence_index}
      className={unchanged.has(timelineKey(segment)) ? '' : 'is-changed'}>
      <time>{clock(segment.start)}—{clock(segment.end)}</time>
      <p>{renderText?.(segment.sequence_index, segment.text) ?? segment.text}</p>
      {renderDetails?.(segment.sequence_index)}
    </li>)}</ol>
  </section>;
}

function PreviewProof({ preview, pending, onCancel, onConfirm, onReview, showTranslation, onTranslationChange }: {
  preview: SourceLearningPreview;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onReview: (start: number) => boolean;
  showTranslation: boolean;
  onTranslationChange: (show: boolean) => void;
}) {
  const [reviewError, setReviewError] = useState<string | null>(null);
  const review = (start: number) => setReviewError(onReview(start) ? null : '播放器尚未就绪，请检查上方播放器后再回听。');
  const sourcePreview = preview;
  const chunks = new Map(preview.segments.map(segment => [segment.sequence_index, segment.chunks]));
  return <div className="srt-proof learning-proof">
    <div className="srt-proof-heading">
      <div><p className="eyebrow">One result · one review</p><h3>同时检查原句与词块</h3></div>
      <span>{preview.summary.current_count} → {preview.summary.candidate_count} 句 · {preview.summary.chunk_count} 块</span>
    </div>
    <label className="translation-toggle"><input type="checkbox" checked={showTranslation}
      onChange={event => onTranslationChange(event.target.checked)} />显示中文</label>
    <p className="srt-proof-note">右侧已经去掉分隔符形成原句；斜杠只作为词块节奏显示。确认后两种视图会同时发布。</p>
    {preview.warnings.length > 0 && <div className="srt-warnings" role="alert">
      <strong>{preview.warnings.length} 处检查提醒 · 请回听</strong>
      <ul>{preview.warnings.map((warning, index) => <li key={`${warning.code}-${index}`}>
        <button type="button" onClick={() => review(warning.start)}>回听 {clock(warning.start)}</button> {warning.message}
      </li>)}</ul>
    </div>}
    <div className="srt-timeline-pair" aria-label="当前字幕与学习字幕对比">
      <Timeline label="当前版本" segments={preview.current_segments} other={preview.segments}
        renderDetails={sequence => showTranslation && <p className="subtitle-translation" lang="zh-Hans">{
          preview.current_segments.find(item => item.sequence_index === sequence)?.translation_zh || '此句尚无中文'}</p>} />
      <Timeline label="待发布 · 原句 / 词块" segments={preview.segments}
        other={preview.current_segments}
        renderText={sequence => <ChunkLine chunks={chunks.get(sequence) ?? []} />}
        renderDetails={sequence => {
          const item = preview.segments.find(segment => segment.sequence_index === sequence)!;
          const source = sourcePreview?.segments.find(segment => segment.sequence_index === sequence);
          return <div className="source-preview-details">
            {showTranslation && <p className="subtitle-translation" lang="zh-Hans">{item.translation_zh || '此句尚无中文'}</p>}
            {source && <><p><strong>所依据的原文</strong> {source.source_text}</p>
              <small>句首：{source.start_basis === 'inline_timestamp' ? '原字幕内部时间' : '原字幕块起点'} ·
                句尾：{source.end_basis === 'next_sentence_start' ? '下一句开始' : '原字幕块结束'}</small></>}
            <button type="button" onClick={() => review(item.start)}>回听第 {sequence + 1} 句</button>
          </div>;
        }} />
    </div>
    {reviewError && <p role="alert">{reviewError}</p>}
    <div className="srt-proof-actions">
      <button type="button" onClick={onCancel} disabled={pending}>取消预览</button>
      <button type="button" className="primary-button" onClick={onConfirm} disabled={pending}>
        {pending ? '正在发布…' : '确认发布原句与词块'}
      </button>
    </div>
  </div>;
}

export default function LearningTranscriptImportPanel({
  videoId, transcript, chunkState, chunkLoading, chunkError, onRetryChunks, onPublished, onReview,
}: Props) {
  const [showTranslation, setShowTranslation] = useState(false);
  const [srt, setSrt] = useState('');
  const [fileName, setFileName] = useState<string | null>(null);
  const [preview, setPreview] = useState<SourceLearningPreview | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRevisionId, setSelectedRevisionId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const layout = chunkState?.revision_id === transcript.revision_id ? chunkState.layout : null;
  const source = useQuery({
    queryKey: ['learning-source', videoId],
    queryFn: ({ signal }) => getLearningSource(videoId, signal),
    retry: false,
  });
  const sourceBlocked = source.isPending || source.isError;
  const revisions = useQuery({
    queryKey: ['transcript-revisions', videoId],
    queryFn: ({ signal }) => getTranscriptRevisions(videoId, signal),
  });
  const historical = useQuery({
    queryKey: ['transcript-revision', videoId, selectedRevisionId],
    queryFn: ({ signal }) => getTranscriptRevision(videoId, selectedRevisionId!, signal),
    enabled: selectedRevisionId !== null,
  });

  const updateSrt = (value: string) => {
    setSrt(value);
    setPreview(null);
    setMessage(null);
    setError(null);
  };
  const copyPrompt = async () => {
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const fresh = await source.refetch();
      if (fresh.error) throw fresh.error;
      if (!fresh.data) throw new Error('暂时无法读取原始字幕，请重试。');
      const prompt = sourceLearningPrompt(fresh.data);
      try { await navigator.clipboard.writeText(prompt); }
      catch { throw new Error('复制失败。请检查浏览器剪贴板权限后重试。'); }
      setMessage('已复制完整任务和原始字幕。交给外部 AI，再带回一份完整返回结果。');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '复制失败，请重试。');
    } finally {
      setPending(false);
    }
  };
  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    updateSrt('');
    setFileName(file.name);
    if (file.size > MAX_RESULT_BYTES) {
      updateSrt('');
      setError('文件超过 1 MiB，请缩小后再试。');
      return;
    }
    setPending(true);
    try {
      updateSrt(await file.text());
      setMessage(`已读取 ${file.name}，请预览原句与词块。`);
    } catch {
      setError('无法读取这个文件，请重新选择或粘贴返回结果。');
    } finally { setPending(false); }
  };
  const showPreview = async () => {
    if (!srt.trim()) {
      setError('请先粘贴完整返回结果，或选择结果文件。');
      return;
    }
    setPending(true);
    setPreview(null);
    setMessage(null);
    setError(null);
    try {
      setPreview(await previewSourceLearning(videoId, srt));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '预览失败，请检查完整返回结果。');
    } finally {
      setPending(false);
    }
  };
  const confirm = async () => {
    if (!preview) return;
    if (preview.base_revision_id !== transcript.revision_id) {
      setPreview(null);
      setError('当前字幕已变化，请重新复制任务并生成学习字幕。');
      return;
    }
    setPending(true);
    setError(null);
    try {
      const result = await publishSourceLearning(
        videoId, srt, preview.base_revision_id, preview.preview_digest);
      onPublished(result);
      setPreview(null);
      setSrt('');
      setFileName(null);
      if (fileInput.current) fileInput.current.value = '';
      setMessage('原句、词块与中文已同时发布。可分别开启列表和画面的中文。');
      await revisions.refetch();
    } catch (cause) {
      setPreview(null);
      setError(cause instanceof Error ? cause.message : '发布失败，当前字幕与词块均未改变。');
    } finally {
      setPending(false);
    }
  };

  const exportSrt = async (kind: 'raw' | 'learning') => {
    setPending(true); setError(null); setMessage(null);
    try {
      const content = await (kind === 'raw' ? getRawSrt : getLearningSrt)(videoId);
      const url = URL.createObjectURL(new Blob([content], { type: 'application/x-subrip;charset=utf-8' }));
      const link = document.createElement('a'); link.href = url; link.download = `${kind}-subtitles.srt`;
      link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(kind === 'raw' ? '已导出原始字幕。' : '已导出当前学习字幕，仅含英文正文。');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '导出失败，请重试。'); }
    finally { setPending(false); }
  };

  return <section className="chunk-layout-tools learning-transcript-tools" id="learning-transcript-tools"
    aria-labelledby="learning-transcript-title">
    <div className="chunk-layout-heading">
      <div><p className="eyebrow">One trip · two reading modes</p>
        <h2 id="learning-transcript-title">生成学习字幕</h2></div>
      <span>{chunkLoading ? '正在读取…' : layout
        ? `${layout.segments.reduce((sum, item) => sum + item.chunks.length, 0)} 个词块`
        : '当前版本尚无词块'}</span>
    </div>
    <p className="chunk-layout-intro">{!source.data ? '按实际字幕来源生成词块与整句中文。' : source.data.processing_mode === 'manual_cues'
      ? '人工字幕：保持原文、原条目与时间，只增加自然词块和整句中文。'
      : '自动字幕：一次完成审慎校准、自然断句、词块与整句中文，应用依据原字幕生成时间。'}</p>
    {source.isPending && <p role="status">正在检查原字幕来源…</p>}
    {source.isError && <p className="chunk-layout-error" role="alert">
      {source.error.message}
      <button type="button" onClick={() => void source.refetch()}>重新检查来源</button>
    </p>}
    <div className="subtitle-export-controls">
      <button type="button" disabled={pending} onClick={() => void exportSrt('raw')}>导出原始字幕</button>
      <button type="button" disabled={pending} onClick={() => void exportSrt('learning')}>导出当前学习字幕</button>
    </div>
    {chunkError && <p className="chunk-layout-error" role="alert">{chunkError}
      <button type="button" onClick={onRetryChunks}>重试读取</button></p>}
    <div className="chunk-layout-step">
      <span>01</span><div><h3>复制完整学习任务</h3><p>内容包含分来源处理规则、整句翻译要求与原始字幕。</p></div>
      <button type="button" onClick={() => void copyPrompt()} disabled={pending || sourceBlocked}>复制任务与原始字幕</button>
    </div>
    <div className="chunk-layout-step is-input">
      <span>02</span><div><h3>导回一份结果</h3><p>粘贴完整返回结果或选择文件，无需手填来源编号或计算时间。</p></div>
      <label htmlFor="learning-srt-content">返回结果</label>
      <textarea id="learning-srt-content" value={srt} disabled={pending} spellCheck={false}
        onChange={event => {
          setFileName(null);
          if (fileInput.current) fileInput.current.value = '';
          updateSrt(event.target.value);
        }}
        placeholder="将外部 AI 返回的完整结果粘贴到这里" />
      <div className="chunk-layout-controls">
        <label className="srt-file-label">选择返回结果文件
          <input ref={fileInput} type="file" accept=".json,.txt,application/json,text/plain"
            onChange={event => void readFile(event)} disabled={pending} />
        </label>
        {fileName && <span className="srt-file-name">{fileName}</span>}
        <button type="button" onClick={() => void showPreview()} disabled={pending || sourceBlocked}>
          {pending ? '正在检查…' : '预览原句与词块'}
        </button>
      </div>
    </div>
    {message && <p className="chunk-layout-message" role="status">{message}</p>}
    {error && <p className="chunk-layout-error" role="alert">{error}</p>}
    {preview && <PreviewProof preview={preview} pending={pending}
      onCancel={() => setPreview(null)} onConfirm={() => void confirm()} onReview={onReview}
      showTranslation={showTranslation} onTranslationChange={setShowTranslation} />}
    {revisions.data && <div className="srt-history">
      <h3>已保存版本 <span>{revisions.data.items.length}</span></h3>
      <p>确认后原句与词块属于同一版本；旧字幕仍可只读查看。</p>
      <ol>{revisions.data.items.map(revision => <li key={revision.id}>
        <span>#{revision.revision_number} · {transcriptOriginLabel(revision.origin)}</span>
        <span>{revision.segment_count} 段</span>
        {revision.is_current && <strong>当前阅读</strong>}
        {!revision.is_current && <button type="button" onClick={() =>
          setSelectedRevisionId(selectedRevisionId === revision.id ? null : revision.id)}>
          {selectedRevisionId === revision.id ? '收起旧版' : '查看旧版'}
        </button>}
      </li>)}</ol>
      {selectedRevisionId && <div className="srt-history-preview">
        <h4>旧版只读 · 不影响当前点读</h4>
        {historical.isPending && <p role="status">正在读取旧版字幕…</p>}
        {historical.isError && <p role="alert">{historical.error.message}</p>}
        {historical.data && <ol>{historical.data.segments.map(segment => <li key={segment.id}>
          <time>{clock(segment.start)}—{clock(segment.end)}</time><span>{segment.text}</span>
          {showTranslation && <p className="subtitle-translation" lang="zh-Hans">{segment.translation_zh || '此句尚无中文'}</p>}
        </li>)}</ol>}
      </div>}
    </div>}
    {revisions.isError && <p className="srt-import-error" role="alert">
      暂时无法读取历史版本。<button type="button" onClick={() => void revisions.refetch()}>重试</button>
    </p>}
  </section>;
}
