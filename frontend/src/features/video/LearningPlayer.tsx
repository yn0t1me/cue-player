import { useEffect, useId, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react';
import type { ChunkLayout, TranscriptSegment } from '../../types/video';
import { readableTextParts } from '../transcript/markText';
import TranscriptViewSwitch, { type ReadingMode } from '../transcript/TranscriptViewSwitch';

interface Props {
  children: ReactNode;
  segment: TranscriptSegment | undefined;
  layout: ChunkLayout | null | undefined;
  mode: ReadingMode;
  onModeChange: (mode: ReadingMode) => void;
  chunksAvailable: boolean;
  chunksLoading: boolean;
  onOpenTools: () => void;
  onFullscreenChange: (fullscreen: boolean) => void;
  translationAvailable?: boolean;
}

export default function LearningPlayer({ children, segment, layout, mode, onModeChange,
                                        chunksAvailable, chunksLoading, onOpenTools, onFullscreenChange, translationAvailable = false }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const fullscreenButton = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  const stage = useRef<HTMLDivElement>(null);
  const subtitleText = useRef<HTMLSpanElement>(null);
  const callback = useRef(onFullscreenChange);
  callback.current = onFullscreenChange;
  const helpId = useId();
  const [fullscreen, setFullscreen] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [showTranslation, setShowTranslation] = useState(false);
  const [size, setSize] = useState('medium');
  const [dockSubtitle, setDockSubtitle] = useState(false);
  const [adjusting, setAdjusting] = useState(false);
  const [position, setPosition] = useState({ x: 0.5, y: 1 });
  const [geometry, setGeometry] = useState({ width: 0, height: 0, frameWidth: 0, frameHeight: 0 });
  const drag = useRef<{ pointerId: number; x: number; y: number; position: typeof position } | null>(null);
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const moveSubtitle = (event: PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId) return;
    setPosition({
      x: clamp(start.position.x + (event.clientX - start.x) / Math.max(1, geometry.frameWidth - geometry.width)),
      y: clamp(start.position.y + (event.clientY - start.y) / Math.max(1, geometry.frameHeight - 112 - geometry.height)),
    });
  };
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  useLayoutEffect(() => {
    const frame = stage.current?.querySelector('.player-frame');
    const text = subtitleText.current;
    if (!frame || !text) { setDockSubtitle(false); return; }
    const measure = () => {
      // Reserve the title area and native controls; keep long sentences intact.
      const bounds = text.getBoundingClientRect();
      const video = frame.getBoundingClientRect();
      setDockSubtitle(bounds.height > video.height - 112);
      setGeometry({ width: bounds.width, height: bounds.height, frameWidth: video.width, frameHeight: video.height });
    };
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(frame);
    observer?.observe(text);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, [segment, mode, size, showSubtitles, showTranslation, fullscreen, chunksAvailable, layout]);

  useEffect(() => {
    const element = host.current!;
    let owned = false;
    const sync = () => {
      const next = document.fullscreenElement === element;
      if (owned && !next) restoreFocus.current = true;
      owned = next;
      setFullscreen(next);
      callback.current(next);
    };
    document.addEventListener('fullscreenchange', sync);
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      if (document.fullscreenElement === element) void document.exitFullscreen?.().catch(() => {});
    };
  }, []);

  useEffect(() => {
    if (!pending && restoreFocus.current) {
      fullscreenButton.current?.focus({ preventScroll: true });
      restoreFocus.current = false;
    }
  }, [pending, fullscreen]);

  const toggleFullscreen = async () => {
    const element = host.current;
    if (!element || pending) return;
    setMessage('');
    if (!element.requestFullscreen || !document.exitFullscreen || document.fullscreenEnabled === false) {
      setMessage('当前浏览器不支持带字幕全屏，可以继续普通观看。');
      return;
    }
    if (document.fullscreenElement && document.fullscreenElement !== element) {
      setMessage('请先退出当前全屏，再使用带字幕全屏。');
      return;
    }
    setPending(true);
    try {
      if (document.fullscreenElement === element) await document.exitFullscreen();
      else await element.requestFullscreen();
      // fullscreenElement is the source of truth, including external exits.
      const next = document.fullscreenElement === element;
      if (host.current === element) {
        setFullscreen(next);
        callback.current(next);
        restoreFocus.current = true;
      } else if (next) await document.exitFullscreen();
    } catch {
      if (host.current === element) setMessage('全屏切换失败，请重试或继续普通观看。');
    } finally {
      if (host.current === element) setPending(false);
    }
  };
  const openTools = async () => {
    if (document.fullscreenElement === host.current) {
      try { await document.exitFullscreen(); }
      catch { setMessage('请先退出全屏，再设置词块。'); return; }
    }
    if (host.current) onOpenTools();
  };
  const boundaries = chunksAvailable && mode === 'chunks'
    ? layout?.segments.find(item => item.segment_id === segment?.id)?.boundary_offsets ?? [] : [];
  return <div ref={host} className={`learning-player${fullscreen ? ' is-fullscreen' : ''}`}>
    <div ref={stage} className={`learning-video-stage${dockSubtitle ? ' has-docked-subtitle' : ''}`}>
      {children}
      {showSubtitles && segment && <div className={`player-subtitle size-${size}${adjusting && !dockSubtitle ? ' is-adjusting' : ''}`}
        style={dockSubtitle ? undefined : {
          left: `calc(${position.x * 100}% + ${(0.5 - position.x) * geometry.width}px)`,
          top: `${48 + Math.max(0, geometry.frameHeight - 112 - geometry.height) * position.y}px`,
        }}
        aria-label={adjusting && !dockSubtitle ? '当前学习字幕，拖动或使用方向键调整位置' : '当前学习字幕'}
        role={adjusting && !dockSubtitle ? 'button' : undefined} tabIndex={adjusting && !dockSubtitle ? 0 : undefined}
        onPointerDown={event => {
          if (!adjusting || dockSubtitle || event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, position };
        }} onPointerMove={moveSubtitle} onPointerUp={endDrag} onPointerCancel={endDrag}
        onKeyDown={event => {
          if (!adjusting || dockSubtitle) return;
          if (event.key === 'Home') { event.preventDefault(); setPosition({ x: 0.5, y: 1 }); }
          else if (event.key.startsWith('Arrow')) {
            event.preventDefault();
            setPosition(value => ({ x: clamp(value.x + (event.key === 'ArrowLeft' ? -0.04 : event.key === 'ArrowRight' ? 0.04 : 0)),
              y: clamp(value.y + (event.key === 'ArrowUp' ? -0.04 : event.key === 'ArrowDown' ? 0.04 : 0)) }));
          }
        }}>
        <span ref={subtitleText} className="player-subtitle-text"><span className="player-subtitle-english">{readableTextParts(segment.text, [], boundaries).map((part, index) =>
          <span key={index} className={part.chunkBoundary ? 'chunk-boundary' : undefined}>{part.text}</span>)}</span>
          {showTranslation && segment.translation_zh && <span className="player-subtitle-translation" lang="zh-Hans">{segment.translation_zh}</span>}
        </span>
      </div>}
    </div>
    <div className="learning-player-controls" aria-label="学习字幕控制">
      <button type="button" aria-pressed={showSubtitles} onClick={() => { setShowSubtitles(value => !value); setAdjusting(false); drag.current = null; }}>学习字幕</button>
      <label className="translation-toggle"><input type="checkbox" checked={showTranslation}
        onChange={event => setShowTranslation(event.target.checked)} />显示中文</label>
      <label>字号 <select aria-label="字幕字号" value={size} onChange={event => setSize(event.target.value)}>
        <option value="small">小</option><option value="medium">中</option><option value="large">大</option>
      </select></label>
      <button type="button" aria-pressed={adjusting} disabled={!showSubtitles || !segment || dockSubtitle}
        onClick={() => { drag.current = null; setAdjusting(value => !value); }}>
        {adjusting ? '完成调整' : '调整位置'}
      </button>
      {adjusting && <button type="button" onClick={() => setPosition({ x: 0.5, y: 1 })}>重置位置</button>}
      <TranscriptViewSwitch mode={mode} onChange={onModeChange} available={chunksAvailable}
        loading={chunksLoading} onOpenTools={() => void openTools()} />
      <button type="button" className="learning-fullscreen-button" ref={fullscreenButton}
        aria-describedby={helpId} disabled={pending} onClick={() => void toggleFullscreen()}>
        {fullscreen ? '退出全屏' : '带字幕全屏'} <span aria-hidden="true">{fullscreen ? '↙' : '⛶'}</span>
      </button>
    </div>
    <p className="learning-fullscreen-help" id={helpId}>{adjusting && !dockSubtitle ? '拖动字幕调整位置，也可聚焦字幕后用方向键微调，Home 重置；完成后点击“完成调整”。'
      : '使用“带字幕全屏”一起放大视频和学习字幕；YouTube 自带全屏只放大视频。'}</p>
    {showSubtitles && showTranslation && !translationAvailable && !segment?.translation_zh &&
      <p className="translation-empty" role="status">此版本尚无中文。</p>}
    {message && <p className="learning-fullscreen-message" role="status">{message}</p>}
  </div>;
}
