import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  createTranscriptFavorite,
  deleteTranscriptMark,
  getChunkLayout,
  getTranscript,
  getTranscriptMarks,
  getVideo,
} from '../api/videos';
import VideoStatus from '../components/VideoStatus';
import ProcessingState, { videoRefreshInterval } from '../features/video/ProcessingState';
import TranscriptPanel from '../features/transcript/TranscriptPanel';
import LearningTranscriptImportPanel from '../features/transcript/LearningTranscriptImportPanel';
import YouTubePlayer, { type PlayerHandle } from '../features/video/YouTubePlayer';
import LearningPlayer from '../features/video/LearningPlayer';
import { findActiveSegmentIndex } from '../features/transcript/findActiveSegmentIndex';
import { hasCurrentChunkLayout, type ReadingMode } from '../features/transcript/TranscriptViewSwitch';
import ReadingNotesWorkspace, { type ReadingTab } from '../features/transcript/ReadingNotesWorkspace';
import { useReaderFavorites } from '../features/transcript/ReaderNotesControls';
import ReaderCollectionPanel from '../features/transcript/ReaderCollectionPanel';
import TranscriptExportPanel from '../features/transcript/TranscriptExportPanel';
import EpisodeDirectory from '../features/collections/EpisodeDirectory';
import type { TranscriptSegment } from '../types/video';

function formatDuration(seconds: number | null): string | null {
  if (seconds === null) return null;
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function subtitleSourceLabel(source: 'youtube_manual' | 'youtube_auto' | 'stt'): string {
  if (source === 'youtube_manual') return '人工英文字幕';
  if (source === 'youtube_auto') return '自动英文字幕';
  return '语音转写';
}

export default function VideoPage({ initialTab = 'transcript' }: { initialTab?: ReadingTab }) {
  const { id = '' } = useParams();
  return <VideoPageContent key={id} id={id} initialTab={initialTab} />;
}

function VideoPageContent({ id, initialTab }: { id: string; initialTab: ReadingTab }) {
  useLayoutEffect(() => { if (window.scrollY > 0) window.scrollTo(0, 0); }, []);
  const location = useLocation();
  const navigate = useNavigate();
  const collectionId = new URLSearchParams(location.search).get('collection');
  const [activeTab, setActiveTab] = useState<ReadingTab>(initialTab);
  useEffect(() => setActiveTab(initialTab), [initialTab]);
  const [currentTime, setCurrentTime] = useState(0);
  const [playerReady, setPlayerReady] = useState(false);
  const [hasPlayerTime, setHasPlayerTime] = useState(false);
  const [readingMode, setReadingMode] = useState<ReadingMode>('sentence');
  const [listVisible, setListVisible] = useState(true);
  const [showTranslation, setShowTranslation] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const playerRef = useRef<PlayerHandle>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const playAt = (start: number): boolean => {
    if (!playerRef.current?.seekTo(start)) return false;
    return playerRef.current.play();
  };
  const playSegment = (segment: TranscriptSegment) => playAt(segment.start);
  const query = useQuery({
    queryKey: ['video', id],
    queryFn: ({ signal }) => getVideo(id, signal),
    refetchInterval: current => videoRefreshInterval(current.state.data),
  });
  const video = query.data;
  const transcript = useQuery({
    queryKey: ['transcript', id],
    queryFn: ({ signal }) => getTranscript(id, signal),
    enabled: video?.status === 'ready',
  });
  const marks = useQuery({
    queryKey: ['transcript-marks', id],
    queryFn: ({ signal }) => getTranscriptMarks(id, signal),
    enabled: video?.status === 'ready',
  });
  const chunkLayout = useQuery({
    queryKey: ['chunk-layout', id, transcript.data?.revision_id],
    queryFn: ({ signal }) => getChunkLayout(id, signal),
    enabled: transcript.data !== undefined,
  });
  useLayoutEffect(() => {
    const element = workspace.current;
    const player = element?.querySelector('.learning-player');
    if (!element || !player || fullscreen) return;
    const measure = () => element.style.setProperty('--reading-player-height', `${player.getBoundingClientRect().height}px`);
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(player);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, [video?.status, fullscreen]);
  const activeIndex = transcript.data && hasPlayerTime
    ? findActiveSegmentIndex(transcript.data.segments, currentTime) : -1;
  const chunksAvailable = hasCurrentChunkLayout(transcript.data, chunkLayout.data?.layout);
  const effectiveMode = chunksAvailable ? readingMode : 'sentence';
  const openChunkTools = () => {
    const details = document.getElementById('subtitle-tools');
    if (details instanceof HTMLDetailsElement) details.open = true;
    window.requestAnimationFrame(() => document.getElementById(
      'learning-transcript-tools')?.scrollIntoView({ block: 'start' }));
  };
  const reportTime = (seconds: number) => { setCurrentTime(seconds); setHasPlayerTime(true); };
  const reportReady = (ready: boolean) => { setPlayerReady(ready); setHasPlayerTime(false); };
  const refreshMarks = () => queryClient.invalidateQueries({ queryKey: ['transcript-marks', id] });
  const favorites = useReaderFavorites({
    createFavorite: async anchor => { const result = await createTranscriptFavorite(id, anchor); await refreshMarks(); return result; },
    deleteFavorite: async markId => { await deleteTranscriptMark(id, markId); await refreshMarks(); },
    onConflict: () => { void queryClient.invalidateQueries({ queryKey: ['transcript', id] }); void refreshMarks(); },
  });
  return (
    <div className={video?.status === 'ready' ? 'video-reading-page' : 'video-detail-page'}>
      <div className="video-page-topline"><Link className="back-link" to="/" onClick={event => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); favorites.guard(() => navigate('/'));
      }}>← 返回视频库</Link>
        {video?.status === 'ready' && <a href="#subtitle-tools" onClick={() => {
          const tools = document.getElementById('subtitle-tools');
          if (tools instanceof HTMLDetailsElement) tools.open = true;
        }}>字幕管理 ↓</a>}</div>
      {query.isPending && <p role="status">正在读取视频…</p>}
      {query.isError && <div className="error-panel" role="alert"><h1 className="detail-title">暂时无法打开视频</h1><p>{query.error.message}</p>
        <button disabled={query.isFetching} onClick={() => void query.refetch()}>重新加载</button></div>}
      {video && <>
        {collectionId && <EpisodeDirectory collectionId={collectionId} videoId={id} guard={favorites.guard} navigate={navigate} />}
        {location.state?.alreadyExists && <p className="notice" role="status">这个视频已在视频库中，已打开原记录；沿用已保存来源，本次选择不会更换字幕。</p>}
        <div className={`detail-summary${video.status === 'ready' ? ' is-reading' : ''}`}>
          {video.status !== 'ready' && video.thumbnail_url && <img className="detail-thumbnail" src={video.thumbnail_url} alt="" />}
          <div><p className="eyebrow">已保存的学习素材</p>
            <h1 className="detail-title">{video.title ?? `YouTube · ${video.youtube_video_id}`}</h1>
            <div className="video-meta"><VideoStatus video={video} />
              <span>{video.channel_title ?? '视频信息尚未获取'}</span>
              {formatDuration(video.duration_seconds) && <span>{formatDuration(video.duration_seconds)}</span>}
              <span>导入偏好：{video.subtitle_preference === 'auto_only' ? '自动字幕' : '人工字幕优先'}</span>
              {video.subtitle_source && <span>{subtitleSourceLabel(video.subtitle_source)}
                {video.subtitle_language && ` · ${video.subtitle_language}`}</span>}
            </div>
          </div>
        </div>
        {video.status !== 'ready' && <><YouTubePlayer key={video.youtube_video_id}
          videoId={video.youtube_video_id} onTimeChange={setCurrentTime} ref={playerRef} />
          <ProcessingState video={video} /></>}
        {video.status === 'ready' && <div ref={workspace} className={`reading-workspace${listVisible ? '' : ' is-list-hidden'}`}>
          <div className="reading-media-column">
            <LearningPlayer segment={playerReady && !transcript.isError ? transcript.data?.segments[activeIndex] : undefined}
              layout={chunkLayout.data?.layout} mode={effectiveMode} onModeChange={setReadingMode}
              chunksAvailable={chunksAvailable} chunksLoading={chunkLayout.isPending}
              onOpenTools={openChunkTools} onFullscreenChange={setFullscreen}
              translationAvailable={transcript.data?.segments.some(item => Boolean(item.translation_zh)) ?? false}>
              <YouTubePlayer key={video.youtube_video_id} videoId={video.youtube_video_id}
                onTimeChange={reportTime}
                onReadyChange={reportReady} ref={playerRef} />
            </LearningPlayer>
            <button type="button" className="transcript-list-toggle" aria-expanded={listVisible}
              aria-controls="reading-transcript-column" onClick={() => favorites.guard(() => setListVisible(value => !value))}>
              {listVisible ? '收起字幕面板' : '展开字幕面板'} <span aria-hidden="true">{listVisible ? '→' : '←'}</span>
            </button>
          </div>
          <div id="reading-transcript-column" className="reading-transcript-column" hidden={!listVisible}>
            <ReadingNotesWorkspace activeTab={activeTab} onTabChange={tab => tab === activeTab || favorites.guard(() => {
              setActiveTab(tab);
              window.requestAnimationFrame(() => document.getElementById(`reading-tab-${tab}`)?.focus({ preventScroll: true }));
            })}
              transcript={<>
                {transcript.isPending && <p className="transcript-loading" role="status">正在读取学习字幕…</p>}
                {transcript.isError && <div className="error-panel transcript-error" role="alert">
                  <p>{transcript.error.message}</p>
                  <button disabled={transcript.isFetching} onClick={() => void transcript.refetch()}>重新加载字幕</button>
                </div>}
                {transcript.data && <TranscriptExportPanel key={`export-${transcript.data.revision_id}`}
                  transcript={transcript.data} videoTitle={video.title ?? `YouTube · ${video.youtube_video_id}`}
                  layout={chunkLayout.data?.layout} loading={transcript.isFetching || chunkLayout.isFetching}
                  error={chunkLayout.isError ? chunkLayout.error.message : transcript.isError ? transcript.error.message : null}
                  onRetry={() => { void transcript.refetch(); void chunkLayout.refetch(); }} />}
                {transcript.data && <TranscriptPanel key={transcript.data.revision_id}
                  transcript={transcript.data} currentTime={currentTime}
                  showTranslation={showTranslation} onTranslationChange={setShowTranslation}
                  activeSegmentIndex={activeIndex} visible={listVisible && !fullscreen && activeTab === 'transcript'}
                  readingMode={effectiveMode} onReadingModeChange={setReadingMode}
                  onPlaySegment={playSegment} marks={marks.data?.items ?? []}
                  chunkLayout={chunkLayout.data?.layout}
                  chunkLayoutLoading={chunkLayout.isPending}
                  onOpenChunkTools={openChunkTools}
                  onSelect={favorites.openSelection} onSelectionError={favorites.invalidSelection} followSuspended={favorites.suspended} />}
              </>}
              favorites={<div className="reading-collection-scroll">
                <ReaderCollectionPanel items={marks.data?.items ?? []}
                  videoTitle={video.title ?? `YouTube · ${video.youtube_video_id}`}
                  loading={marks.isPending} loadError={marks.isError ? marks.error.message : null}
                  onRetry={() => { void marks.refetch(); }} onReplay={playAt}
                  editingDisabled={favorites.suspended}
                  onDelete={async markId => { await deleteTranscriptMark(id, markId); await refreshMarks(); }} />
              </div>} />
            {favorites.controls}
          </div>
        </div>}
        {video.status === 'ready' && <details className="subtitle-tools" id="subtitle-tools">
          <summary><span>字幕管理</span><small>一次生成 · 原句 / 词块 / 中文 · 历史版本</small></summary>
          {transcript.data && <LearningTranscriptImportPanel key={id}
            videoId={id} transcript={transcript.data}
            chunkState={chunkLayout.data} chunkLoading={chunkLayout.isPending}
            chunkError={chunkLayout.isError ? chunkLayout.error.message : null}
            onRetryChunks={() => { void chunkLayout.refetch(); }}
            onReview={playAt}
            onPublished={result => {
              queryClient.setQueryData(['transcript', id], result.transcript);
              queryClient.setQueryData(
                ['chunk-layout', id, result.transcript.revision_id], result.chunk_layout);
              void queryClient.invalidateQueries({ queryKey: ['transcript-revisions', id] });
              void refreshMarks();
            }} />}
        </details>}
        <a className="text-link" href={video.youtube_url} target="_blank" rel="noreferrer">在 YouTube 打开原视频 ↗</a>
      </>}
    </div>
  );
}
