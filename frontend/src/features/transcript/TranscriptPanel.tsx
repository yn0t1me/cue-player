import { transcriptOriginLabel } from '../../types/video';
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import type {
  ChunkLayout,
  Transcript,
  TranscriptMark,
  TranscriptSegment,
} from '../../types/video';
import { findActiveSegmentIndex } from './findActiveSegmentIndex';
import TranscriptViewSwitch, { hasCurrentChunkLayout, type ReadingMode } from './TranscriptViewSwitch';
import type { ReaderSelection } from './ReaderNotesControls';
import { readableTextParts, readTextSelection } from './markText';

export function formatTranscriptTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
}

interface Props {
  transcript: Transcript;
  currentTime: number;
  onPlaySegment: (segment: TranscriptSegment) => boolean;
  marks?: TranscriptMark[];
  onSelect?: (selection: ReaderSelection) => void;
  followSuspended?: boolean;
  onSelectionError?: () => void;
  initialScrollTop?: number;
  onScrollPositionChange?: (scrollTop: number) => void;
  chunkLayout?: ChunkLayout | null;
  chunkLayoutLoading?: boolean;
  onOpenChunkTools?: () => void;
  readingMode?: ReadingMode;
  onReadingModeChange?: (mode: ReadingMode) => void;
  activeSegmentIndex?: number;
  visible?: boolean;
  showTranslation?: boolean;
  onTranslationChange?: (show: boolean) => void;
}

export default function TranscriptPanel({ transcript, currentTime, onPlaySegment,
                                         marks = [], onSelect, followSuspended = false, onSelectionError,
                                         initialScrollTop, onScrollPositionChange,
                                         chunkLayout, chunkLayoutLoading = false,
                                         onOpenChunkTools, readingMode: controlledMode,
                                         onReadingModeChange, activeSegmentIndex, visible = true, showTranslation = false, onTranslationChange }: Props) {
  const activeIndex = activeSegmentIndex ?? findActiveSegmentIndex(transcript.segments, currentTime);
  const [playbackMessage, setPlaybackMessage] = useState<string | null>(null);
  const [autoFollow, setAutoFollow] = useState(initialScrollTop === undefined);
  const [localMode, setLocalMode] = useState<ReadingMode>('sentence');
  const readingMode = controlledMode ?? localMode;
  const setReadingMode = onReadingModeChange ?? setLocalMode;
  const segmentElements = useRef<Array<HTMLLIElement | null>>([]);
  const listElement = useRef<HTMLOListElement>(null);
  const programmaticScroll = useRef(false);
  const selectedByGesture = useRef(false);
  const resetFrame = useRef<number | undefined>(undefined);
  const marksBySegment = useMemo(() => {
    const grouped = new Map<string, TranscriptMark[]>();
    for (const mark of marks) {
      if (mark.revision_id !== transcript.revision_id) continue;
      const group = grouped.get(mark.segment_id) ?? [];
      group.push(mark);
      grouped.set(mark.segment_id, group);
    }
    return grouped;
  }, [marks, transcript.revision_id]);
  const boundariesBySegment = useMemo(() => new Map(
    chunkLayout?.revision_id === transcript.revision_id
      ? chunkLayout.segments.map(item => [item.segment_id, item.boundary_offsets] as const)
      : [],
  ), [chunkLayout, transcript.revision_id]);
  const hasChunkLayout = hasCurrentChunkLayout(transcript, chunkLayout);

  useEffect(() => setAutoFollow(initialScrollTop === undefined), [transcript.revision_id, initialScrollTop]);
  useLayoutEffect(() => {
    if (initialScrollTop === undefined || !listElement.current) return;
    listElement.current.scrollTop = initialScrollTop;
    onScrollPositionChange?.(listElement.current.scrollTop);
  }, [transcript.revision_id, initialScrollTop]);
  useEffect(() => {
    if (!visible || followSuspended || !autoFollow || activeIndex < 0) return;
    const element = segmentElements.current[activeIndex];
    const list = listElement.current;
    if (!element || !list || typeof list.scrollTo !== 'function') return;
    const center = () => {
      const itemBounds = element.getBoundingClientRect();
      const listBounds = list.getBoundingClientRect();
      programmaticScroll.current = true;
      list.scrollTo({ top: Math.max(0, list.scrollTop + itemBounds.top - listBounds.top - list.clientTop
        + itemBounds.height / 2 - list.clientHeight / 2), behavior: 'auto' });
      window.cancelAnimationFrame(resetFrame.current ?? 0);
      resetFrame.current = window.requestAnimationFrame(() => { programmaticScroll.current = false; });
    };
    center();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(center);
    observer?.observe(list);
    observer?.observe(element);
    return () => { observer?.disconnect(); window.cancelAnimationFrame(resetFrame.current ?? 0); };
  }, [activeIndex, autoFollow, visible, readingMode, followSuspended, showTranslation]);

  const pauseAutoFollow = () => {
    if (!followSuspended && !programmaticScroll.current) setAutoFollow(false);
  };
  const pauseAutoFollowForKey = (event: KeyboardEvent) => {
    if (!followSuspended && ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'].includes(event.key)) {
      setAutoFollow(false);
    }
  };
  const playSegment = (segment: TranscriptSegment) => {
    setPlaybackMessage(onPlaySegment(segment)
      ? null
      : '播放器尚未就绪，请等待播放器加载完成或先处理上方的播放错误。');
  };
  const captureSelection = (segment: TranscriptSegment, element: HTMLElement, keyboard = false) => {
    if (!onSelect) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    // The consumer may clear the DOM selection before the following click.
    selectedByGesture.current = true;
    const range = readTextSelection(element, segment.text, selection);
    if (!range) { onSelectionError?.(); return; }
    const domRange = selection.getRangeAt(0);
    onSelect({ anchor: { revision_id: transcript.revision_id, segment_id: segment.id,
      start_offset: range.startOffset, end_offset: range.endOffset, selected_text: range.selectedText },
      trigger: element, rect: typeof domRange.getBoundingClientRect === 'function'
        ? domRange.getBoundingClientRect() : element.getBoundingClientRect(), keyboard });
  };
  const selectWhole = (segment: TranscriptSegment, element: HTMLElement, keyboard: boolean) => onSelect?.({
    anchor: { revision_id: transcript.revision_id, segment_id: segment.id, start_offset: 0,
      end_offset: Array.from(segment.text).length, selected_text: segment.text },
    trigger: element, rect: element.getBoundingClientRect(), keyboard,
  });
  return <section className="transcript-panel" aria-labelledby="transcript-title">
    <div className="transcript-heading">
      <div><h2 id="transcript-title">逐句阅读</h2></div>
      <div className="transcript-heading-tools">
        <span>{transcript.segments.length} 段 · {transcript.origin === 'generated' ? `v${transcript.normalization_version}` : transcriptOriginLabel(transcript.origin)}</span>
        <label className="translation-toggle"><input type="checkbox" checked={showTranslation}
          onChange={event => onTranslationChange?.(event.target.checked)} />显示中文</label>
        <TranscriptViewSwitch mode={readingMode} onChange={setReadingMode}
          available={hasChunkLayout} loading={chunkLayoutLoading} onOpenTools={onOpenChunkTools} />
      </div>
    </div>
    <p className="transcript-note">时间来自原始字幕。{readingMode === 'chunks' && hasChunkLayout
        ? '细刻线表示自然词块，仍可跨词块选择文字。'
        : '点击时间或正文可回听；选中同一句内的文字可收藏、做笔记或提问。'}</p>
    {showTranslation && !transcript.segments.some(item => item.translation_zh) &&
      <p className="translation-empty" role="status">此版本尚无中文，可在字幕管理中生成含翻译的学习字幕。</p>}
    {playbackMessage && <p className="transcript-playback-message" role="status">{playbackMessage}</p>}
    {!autoFollow && <div className="transcript-follow-control">
      <button type="button" disabled={followSuspended} onClick={() => setAutoFollow(true)}>返回当前字幕</button>
    </div>}
    <ol
      aria-label="学习字幕"
      className="transcript-list"
      ref={listElement}
      onKeyDown={pauseAutoFollowForKey}
      onScroll={event => { onScrollPositionChange?.(event.currentTarget.scrollTop); pauseAutoFollow(); }}
      onTouchMove={pauseAutoFollow}
      onWheel={pauseAutoFollow}
      tabIndex={0}
    >
      {transcript.segments.map((segment, index) => <li
        aria-current={index === activeIndex ? 'true' : undefined}
        className={`transcript-segment${index === activeIndex ? ' is-active' : ''}`}
        key={segment.id}
        ref={element => { segmentElements.current[index] = element; }}
      >
        <div className="transcript-segment-row">
          <button className="segment-play" type="button"
            aria-label={`从 ${formatTranscriptTime(segment.start)} 回听这句字幕`}
            onClick={() => playSegment(segment)}>
            <time dateTime={`PT${segment.start}S`}>{formatTranscriptTime(segment.start)}</time>
            <span aria-hidden="true">↗</span>
          </button>
          <div className="segment-readable" role="button" tabIndex={0}
            aria-label={`字幕：${segment.text}。按回车回听，或选中文字标记`}
            onMouseDown={() => { selectedByGesture.current = false; }}
            onTouchStart={() => { selectedByGesture.current = false; }}
            onMouseUp={event => captureSelection(segment, event.currentTarget)}
            onTouchEnd={event => captureSelection(segment, event.currentTarget)}
            onKeyUp={event => { if (event.shiftKey || event.key === 'F10') captureSelection(segment, event.currentTarget, event.key === 'F10'); }}
            onClick={() => {
              if (!selectedByGesture.current && window.getSelection()?.isCollapsed !== false) playSegment(segment);
              selectedByGesture.current = false;
            }}
            onKeyDown={event => {
              if (event.key === 'F10' && event.shiftKey) {
                event.preventDefault();
                if (window.getSelection()?.isCollapsed === false) captureSelection(segment, event.currentTarget, true);
                else selectWhole(segment, event.currentTarget, true);
              } else if ((event.key === 'Enter' || event.key === ' ') && window.getSelection()?.isCollapsed !== false) {
                event.preventDefault();
                playSegment(segment);
              }
            }}>
            {readableTextParts(
              segment.text,
              marksBySegment.get(segment.id) ?? [],
              readingMode === 'chunks' ? boundariesBySegment.get(segment.id) ?? [] : [],
            ).map((part, partIndex) => {
              const className = part.chunkBoundary ? 'chunk-boundary' : undefined;
              return part.marked
                ? <mark key={partIndex}
                  className={`transcript-marked-text${className ? ` ${className}` : ''}`}>
                  {part.text}</mark>
                : <span key={partIndex} className={className}>{part.text}</span>;
            })}
          </div>
          {onSelect && <button type="button" className="segment-mark-whole"
            aria-label={`整句操作：${segment.text}`} aria-haspopup="dialog"
            onClick={event => selectWhole(segment, event.currentTarget, event.detail === 0)}>整句</button>}
          {showTranslation && segment.translation_zh && <p className="segment-translation subtitle-translation" lang="zh-Hans">
            {segment.translation_zh}</p>}
        </div>
      </li>)}
    </ol>
  </section>;
}
