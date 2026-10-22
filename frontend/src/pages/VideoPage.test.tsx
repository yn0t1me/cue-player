// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  createTranscriptFavorite,

  deleteTranscriptMark,

  getChunkLayout,
  getRawSrt, getLearningSource, getLearningSrt, previewSourceLearning, publishSourceLearning,
  getTranscript,
  getTranscriptMarks,

  getTranscriptRevisions,
  getTranscriptRevision,
  getVideo,

} from '../api/videos';
import type { LearningSource, TranscriptMark, Video } from '../types/video';
import VideoPage from './VideoPage';
import { getCollection } from '../api/collections';
import { ApiError } from '../api/client';
vi.mock('../api/collections', () => ({ getCollection: vi.fn() }));

vi.mock('../api/videos', () => ({
  getVideo: vi.fn(), getTranscript: vi.fn(), getRawSrt: vi.fn(),
  getLearningSource: vi.fn(), getLearningSrt: vi.fn(), previewSourceLearning: vi.fn(), publishSourceLearning: vi.fn(),
  getTranscriptRevisions: vi.fn(),
  getTranscriptRevision: vi.fn(), getTranscriptMarks: vi.fn(), createTranscriptFavorite: vi.fn(),
  deleteTranscriptMark: vi.fn(), getChunkLayout: vi.fn(),
}));
const playerHandle = vi.hoisted(() => ({ seekTo: vi.fn(() => true), play: vi.fn(() => true),
  mounted: vi.fn(), destroyed: vi.fn(), time: 10.5 }));
vi.mock('../features/video/YouTubePlayer', async () => {
  const React = await import('react');
  return {
    default: React.forwardRef(function Player(
      { onTimeChange, initialTime, onReadyChange }: { onTimeChange?: (seconds: number) => void;
        initialTime?: number; onReadyChange?: (ready: boolean) => void },
      ref,
    ) {
      React.useImperativeHandle(ref, () => playerHandle);
      React.useEffect(() => {
        playerHandle.mounted(); onReadyChange?.(true);
        return () => { playerHandle.destroyed(); };
      }, []);
      return <><button className="report-time" data-initial-time={initialTime}
        onClick={() => onTimeChange?.(playerHandle.time)}>Report player time</button>
        <button className="report-error" onClick={() => onReadyChange?.(false)}>Report error</button>
        <button className="report-ready" onClick={() => onReadyChange?.(true)}>Report ready</button></>;
    }),
  };
});

let root: Root;
let container: HTMLDivElement;
const readyVideo: Video = {
  id: 'video-id', youtube_video_id: 'M7lc1UVf-VE', youtube_url: 'https://www.youtube.com/watch?v=M7lc1UVf-VE',
  title: 'Video', channel_title: 'Channel', duration_seconds: 20, thumbnail_url: null,
  status: 'ready', subtitle_preference: 'manual_first', subtitle_source: 'youtube_manual', subtitle_language: 'en', created_at: '2026-09-07T00:00:00Z',
  processing: { id: 'job-id', stage: 'completed', status: 'completed', progress: 100, error_code: null, error_message: null },
};

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  playerHandle.time = 10.5;
  playerHandle.seekTo.mockReturnValue(true);
  playerHandle.play.mockReturnValue(true);
  vi.mocked(getVideo).mockResolvedValue(readyVideo);
  vi.mocked(getTranscript).mockResolvedValue({
    video_id: 'video-id', revision_id: 'revision-id', origin: 'generated', normalization_version: 1,
    segments: [
      { id: 'one', sequence_index: 0, start: 2, end: 4, text: 'Earlier sentence.' },
      { id: 'two', sequence_index: 1, start: 10, end: 12, text: 'Current sentence.' },
    ],
  });
  vi.mocked(getLearningSource).mockResolvedValue({ format: 'learning-source-v2', source_type: 'youtube_auto', processing_mode: 'auto_units', source_video_id: 'M7lc1UVf-VE', source_digest: 'a'.repeat(64), extractor_version: 'youtube-vtt-units-v1', units: [{ id: 'u000001', text: 'Raw source', start_ms: 6500, time_basis: 'inline_timestamp' }] });
  vi.mocked(getRawSrt).mockResolvedValue('1\n00:00:02,000 --> 00:00:04,000\nRaw text\n');
  vi.mocked(getTranscriptMarks).mockResolvedValue({ items: [] });
  vi.mocked(getChunkLayout).mockResolvedValue({
    video_id: 'video-id', revision_id: 'revision-id', layout: null,
  });
  vi.mocked(getTranscriptRevisions).mockResolvedValue({ items: [{
    id: 'revision-id', origin: 'generated', revision_number: 1,
    created_at: '2026-10-05T00:00:00Z', normalization_version: 1,
    segment_count: 2, is_current: true,
  }] });
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

it('saves a whole-sentence mark and shows it in the same-place favorites tab', async () => {
  let items: TranscriptMark[] = [];
  vi.mocked(getTranscriptMarks).mockImplementation(async () => ({ items }));
  vi.mocked(createTranscriptFavorite).mockImplementation(async (_videoId, payload) => {
    items = [{ id: 'mark-1', video_id: 'video-id', revision_id: payload.revision_id,
      revision_number: 1, revision_origin: 'generated', is_current: true,
      segment_id: payload.segment_id, segment_sequence_index: 0, segment_start: 2,
      segment_end: 4, segment_text: 'Earlier sentence.',
      start_offset: payload.start_offset, end_offset: payload.end_offset,
      selected_text: payload.selected_text,
      created_at: '', updated_at: '' }];
    return { item: items[0], created: true };
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/videos/video-id']}>
        <Routes><Route path="/videos/:id" element={<VideoPage />} />
          <Route path="/videos/:id/marks" element={<VideoPage initialTab="favorites" />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  ));
  await vi.waitFor(() => expect(container.querySelector('.segment-mark-whole')).not.toBeNull());
  await act(async () => (container.querySelector('.segment-mark-whole') as HTMLButtonElement).click());
  await act(async () => (container.querySelector('.reader-selection-menu button') as HTMLButtonElement).click());
  expect(createTranscriptFavorite).toHaveBeenCalledWith('video-id', {
    revision_id: 'revision-id', segment_id: 'one', start_offset: 0, end_offset: 17,
    selected_text: 'Earlier sentence.',
  });
  expect(playerHandle.seekTo).not.toHaveBeenCalled();
  await vi.waitFor(() => expect(container.querySelector('.favorites-panel .collection-heading')?.textContent).toContain('1'));
  expect(container.querySelector('.segment-readable mark')?.textContent).toBe('Earlier sentence.');
  await act(async () => (container.querySelector('#reading-tab-favorites') as HTMLButtonElement).click());
  await vi.waitFor(() => expect(container.querySelector('.favorites-panel .collection-card')?.textContent).toContain('Earlier sentence.'));
  expect(vi.mocked(getTranscriptMarks).mock.calls.length).toBeGreaterThanOrEqual(2);
  queryClient.clear();
});

it('preserves all tab scroll positions and playback when switching in place', async () => {
  const queryClient = await renderReadingPage();
  const list = container.querySelector('.transcript-list') as HTMLOListElement;
  const favorites = container.querySelector('#reading-panel-favorites .reading-collection-scroll') as HTMLElement;
  const player = container.querySelector('.report-time');
  await clickControl('.report-time');
  await act(async () => { list.scrollTop = 55; list.dispatchEvent(new Event('scroll', { bubbles: true })); });
  await clickControl('#reading-tab-favorites');
  favorites.scrollTop = 88;
  playerHandle.time = 2.5;
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Earlier sentence.');
  await clickControl('#reading-tab-transcript');
  expect(container.querySelector('.transcript-list')).toBe(list);
  expect(list.scrollTop).toBe(55);
  expect(container.querySelector('.transcript-follow-control')).not.toBeNull();
  await clickControl('#reading-tab-favorites');
  expect(favorites.scrollTop).toBe(88);
  expect(container.querySelector('.report-time')).toBe(player);
  expect(playerHandle.mounted).toHaveBeenCalledOnce();
  expect(playerHandle.destroyed).not.toHaveBeenCalled();
  expect(playerHandle.seekTo).not.toHaveBeenCalled();
  expect(playerHandle.play).not.toHaveBeenCalled();
  queryClient.clear();
});

it('opens the legacy marks URL as the unified favorites tab', async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(<QueryClientProvider client={queryClient}>
    <MemoryRouter initialEntries={['/videos/video-id/marks']}>
      <Routes><Route path="/videos/:id/marks" element={<VideoPage initialTab="favorites" />} /></Routes>
    </MemoryRouter>
  </QueryClientProvider>));
  await vi.waitFor(() => expect(container.querySelector('.transcript-list')).not.toBeNull());
  expect(container.querySelector('#reading-tab-favorites')?.getAttribute('aria-selected')).toBe('true');
  expect(container.querySelector('.learning-player')).not.toBeNull();
  expect(container.querySelector('.video-marks-page')).toBeNull();
  await clickControl('#reading-tab-transcript');
  expect(playerHandle.mounted).toHaveBeenCalledOnce();
  expect(playerHandle.seekTo).not.toHaveBeenCalled();
  expect(playerHandle.play).not.toHaveBeenCalled();
  queryClient.clear();
});

it('passes player time through the page to transcript highlighting', async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/videos/video-id']}>
        <Routes><Route path="/videos/:id" element={<VideoPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  ));
  await vi.waitFor(() => expect(container.querySelector('.report-time')).not.toBeNull());
  expect(container.textContent).toContain('人工英文字幕 · en');
  expect(container.querySelector('[aria-current="true"]')).toBeNull();

  await act(async () => (container.querySelector('.report-time') as HTMLButtonElement).click());

  expect(container.querySelector('[aria-current="true"] .segment-readable')?.textContent).toBe('Current sentence.');
  queryClient.clear();
});

it('shows the automatic caption source on a ready video', async () => {
  vi.mocked(getVideo).mockResolvedValue({
    ...readyVideo,
    subtitle_source: 'youtube_auto',
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/videos/video-id']}>
        <Routes><Route path="/videos/:id" element={<VideoPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  ));
  await vi.waitFor(() => expect(container.textContent).toContain('自动英文字幕 · en'));
  queryClient.clear();
});

it('seeks to the selected start and then requests playback', async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/videos/video-id']}>
        <Routes><Route path="/videos/:id" element={<VideoPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  ));
  await vi.waitFor(() => expect(container.querySelector('.transcript-segment button')).not.toBeNull());

  await act(async () => (container.querySelectorAll('.segment-play')[1] as HTMLButtonElement).click());
  expect(playerHandle.seekTo).toHaveBeenCalledWith(10);
  expect(playerHandle.play).toHaveBeenCalledOnce();

  playerHandle.seekTo.mockReturnValue(false);
  await act(async () => (container.querySelectorAll('.segment-play')[0] as HTMLButtonElement).click());
  expect(playerHandle.seekTo).toHaveBeenLastCalledWith(2);
  expect(playerHandle.play).toHaveBeenCalledOnce();
  expect(container.textContent).toContain('播放器尚未就绪');
  queryClient.clear();
});

it('shows a saved old version read-only without changing the playback transcript', async () => {
  vi.mocked(getTranscriptRevisions).mockResolvedValue({ items: [
    { id: 'revision-new', origin: 'source_aligned', revision_number: 2,
      created_at: '2026-10-05T01:00:00Z', normalization_version: null,
      segment_count: 1, is_current: true },
    { id: 'revision-id', origin: 'generated', revision_number: 1,
      created_at: '2026-10-05T00:00:00Z', normalization_version: 1,
      segment_count: 2, is_current: false },
  ] });
  vi.mocked(getTranscriptRevision).mockResolvedValue({
    video_id: 'video-id', revision_id: 'revision-id', origin: 'generated',
    normalization_version: 1,
    segments: [{ id: 'old', sequence_index: 0, start: 1, end: 2, text: 'Old saved line.' }],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/videos/video-id']}>
        <Routes><Route path="/videos/:id" element={<VideoPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  ));
  await vi.waitFor(() => expect(container.textContent).toContain('#2 · 原字幕时间重建'));
  const viewOld = Array.from(container.querySelectorAll('button'))
    .find(button => button.textContent === '查看旧版');
  await act(async () => viewOld?.click());
  await vi.waitFor(() => expect(container.textContent).toContain('Old saved line.'));
  expect(container.querySelector('.transcript-list')?.textContent).toContain('Earlier sentence.');
  expect(getTranscriptRevision).toHaveBeenCalledWith('video-id', 'revision-id', expect.anything());
  queryClient.clear();
});

async function renderReadingPage(entry = '/videos/video-id') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => root.render(<QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[entry]}>
      <Routes><Route path="/videos/:id" element={<VideoPage />} /></Routes>
    </MemoryRouter>
  </QueryClientProvider>));
  await vi.waitFor(() => expect(container.querySelector('.transcript-list')).not.toBeNull());
  return client;
}
const clickControl = async (selector: string) => {
  await act(async () => (container.querySelector(selector) as HTMLButtonElement).click());
};

it('keeps overlay, list and real time in sync across gaps, player errors and reloads', async () => {
  const client = await renderReadingPage();
  expect(container.querySelector('.player-subtitle')).toBeNull();
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Current sentence.');
  expect(container.querySelector('[aria-current="true"] .segment-readable')?.textContent).toBe('Current sentence.');
  await clickControl('.learning-player-controls > button');
  expect(container.querySelector('.player-subtitle')).toBeNull();
  expect(container.querySelector('[aria-current="true"]')).not.toBeNull();
  await clickControl('.learning-player-controls > button');
  playerHandle.time = 12;
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')).toBeNull();
  expect(container.querySelector('[aria-current="true"]')).toBeNull();
  playerHandle.time = 2;
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Earlier sentence.');
  await clickControl('.report-error');
  expect(container.querySelector('.player-subtitle')).toBeNull();
  await clickControl('.report-ready');
  expect(container.querySelector('.player-subtitle')).toBeNull();
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Earlier sentence.');
  client.clear();
});

it('preserves manual reading state and player instance when collapsing and expanding the list', async () => {
  const client = await renderReadingPage();
  const list = container.querySelector('.transcript-list') as HTMLOListElement;
  const player = container.querySelector('.report-time');
  await act(async () => { list.scrollTop = 55; list.dispatchEvent(new Event('scroll', { bubbles: true })); });
  await clickControl('.transcript-list-toggle');
  expect((container.querySelector('.reading-transcript-column') as HTMLElement).hidden).toBe(true);
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Current sentence.');
  await clickControl('.transcript-list-toggle');
  expect(container.querySelector('.transcript-list')).toBe(list);
  expect(list.scrollTop).toBe(55);
  expect(container.querySelector('.transcript-follow-control')).not.toBeNull();
  expect(container.querySelector('.report-time')).toBe(player);
  expect(playerHandle.mounted).toHaveBeenCalledOnce();
  expect(playerHandle.destroyed).not.toHaveBeenCalled();
  expect(playerHandle.seekTo).not.toHaveBeenCalled();
  expect(playerHandle.play).not.toHaveBeenCalled();
  client.clear();
});

it('shares chunk mode between the overlay and list and ignores stale layouts after a revision changes', async () => {
  const client = await renderReadingPage();
  await act(async () => client.setQueryData(['chunk-layout', 'video-id', 'revision-id'], {
    layout: { id: 'layout', revision_id: 'revision-id', segments: [
      { segment_id: 'one', boundary_offsets: [] }, { segment_id: 'two', boundary_offsets: [7] },
    ] },
  }));
  await clickControl('.report-time');
  const chunkButton = [...container.querySelectorAll('.learning-player-controls button')]
    .find(button => button.textContent === '词块') as HTMLButtonElement;
  await act(async () => chunkButton.click());
  expect(container.querySelectorAll('.player-subtitle .chunk-boundary')).toHaveLength(1);
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Current sentence.');
  expect(container.querySelectorAll('.transcript-list .chunk-boundary')).toHaveLength(1);
  const sentenceButton = [...container.querySelectorAll('.transcript-panel button')]
    .find(button => button.textContent === '原句') as HTMLButtonElement;
  await act(async () => sentenceButton.click());
  expect(container.querySelector('.player-subtitle .chunk-boundary')).toBeNull();
  await act(async () => chunkButton.click());
  await act(async () => client.setQueryData(['transcript', 'video-id'], {
    video_id: 'video-id', revision_id: 'new-revision', origin: 'source_aligned', normalization_version: null,
    segments: [{ id: 'new', sequence_index: 0, start: 10, end: 12, text: 'New published sentence.' }],
  }));
  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 20)); });
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('New published sentence.');
  expect(container.querySelector('.player-subtitle .chunk-boundary')).toBeNull();
  expect(container.querySelector('[aria-current="true"] .segment-readable')?.textContent).toBe('New published sentence.');
  client.clear();
});

const sourcePreview = {
  video_id: 'video-id', base_revision_id: 'revision-id', preview_digest: 'source-preview',
  source_digest: 'a'.repeat(64), extractor_version: 'youtube-vtt-units-v1', current_segments: [],
  segments: [{ sequence_index: 0, start: 6.5, end: 8, text: 'Keep me in the loop.', translation_zh: '让我知道最新情况。',
    chunks: ['Keep me', 'in the loop.'], boundary_offsets: [7],
    first_unit_id: 'u000001', last_unit_id: 'u000001', source_text: 'keep me in the lup',
    start_basis: 'inline_timestamp' as const, end_basis: 'source_cue_end' as const }],
  summary: { current_count: 2, candidate_count: 1, text_changed: true, timing_changed: true,
    split_segment_count: 1, chunk_count: 2 },
  warnings: [{ code: 'TEXT_CHANGED', start: 6.5, end: 8, message: '文字已调整，请回听检查。' }],
};
const byLabel = (label: string) => [...container.querySelectorAll('button')].find(b => b.textContent === label)!;
async function enterResult(value: string) {
  await act(async () => {
    const textarea = container.querySelector('#learning-srt-content')!;
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, value);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

it('copies numbered source once, reviews provenance, seeks and publishes both reading views', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  vi.mocked(previewSourceLearning).mockResolvedValue(sourcePreview);
  const transcript = { video_id: 'video-id', revision_id: 'source-revision',
    origin: 'source_aligned' as const, normalization_version: null,
    segments: [{ id: 'source-segment', sequence_index: 0, start: 6.5, end: 8, text: 'Keep me in the loop.', translation_zh: '让我知道最新情况。' }] };
  const chunk_layout = { video_id: 'video-id', revision_id: 'source-revision', layout: {
    id: 'source-layout', revision_id: 'source-revision', content_sha256: 'layout', created_at: '', updated_at: '',
    segments: [{ segment_id: 'source-segment', ...sourcePreview.segments[0] }] } };
  vi.mocked(publishSourceLearning).mockResolvedValue({ transcript, chunk_layout });
  const client = await renderReadingPage();
  await vi.waitFor(() => expect(byLabel('复制任务与原始字幕').disabled).toBe(false));
  await act(async () => byLabel('复制任务与原始字幕').click());
  expect(writeText.mock.calls[0][0]).toContain('learning-source-v2');
  expect(writeText.mock.calls[0][0]).toContain('不要估算、修改或返回');
  expect(getRawSrt).not.toHaveBeenCalled();
  await enterResult('complete returned JSON');
  await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(container.textContent).toContain('keep me in the lup'));
  expect(container.textContent).toContain('原字幕内部时间');
  expect(container.querySelector('.transcript-list')!.textContent).toContain('Earlier sentence.');
  await act(async () => byLabel('回听第 1 句').click());
  expect(playerHandle.seekTo).toHaveBeenCalledWith(6.5);
  expect(publishSourceLearning).not.toHaveBeenCalled();
  vi.mocked(getChunkLayout).mockResolvedValue(chunk_layout);
  await act(async () => byLabel('确认发布原句与词块').click());
  await vi.waitFor(() => expect(container.querySelector('.transcript-list')!.textContent).toContain('Keep me in the loop.'));
  expect(publishSourceLearning).toHaveBeenCalledWith('video-id', 'complete returned JSON', 'revision-id', 'source-preview');

  expect(container.textContent).toContain('原字幕时间重建');
  expect(container.textContent).not.toContain('vnull');
  await act(async () => byLabel('词块').click());
  expect(container.querySelectorAll('.transcript-list .chunk-boundary')).toHaveLength(1);
  expect(container.querySelector('.transcript-list')!.textContent).not.toContain('u000001');
  client.clear();
});

it('keeps unsupported sources blocked without offering SRT compatibility', async () => {
  const { ApiError } = await import('../api/client');
  vi.mocked(getLearningSource).mockRejectedValue(new ApiError('此字幕暂不支持按原始细粒度时间重建。', 409, 'SOURCE_TIMING_UNAVAILABLE'));
  const client = await renderReadingPage();
  await vi.waitFor(() => expect(container.textContent).toContain('此字幕暂不支持'));
  expect(byLabel('复制任务与原始字幕').disabled).toBe(true);
  expect(byLabel('预览原句与词块').disabled).toBe(true);
  expect(getRawSrt).not.toHaveBeenCalled();
  expect(container.textContent).not.toContain('SRT 兼容处理');
  expect(container.querySelectorAll('textarea')).toHaveLength(1);
  client.clear();
});

it('cancels or edits a source preview without publishing and shows range errors', async () => {
  vi.mocked(previewSourceLearning).mockResolvedValue(sourcePreview);
  const client = await renderReadingPage();
  await vi.waitFor(() => expect(byLabel('预览原句与词块').disabled).toBe(false));
  await enterResult('complete JSON');
  await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(container.querySelector('.learning-proof')).not.toBeNull());
  await act(async () => byLabel('取消预览').click());
  expect(container.querySelector('.learning-proof')).toBeNull();
  await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(container.querySelector('.learning-proof')).not.toBeNull());
  await enterResult('changed JSON');
  expect(container.querySelector('.learning-proof')).toBeNull();
  vi.mocked(previewSourceLearning).mockRejectedValue(new Error('第 2 句：来源范围不连续。'));
  await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(container.textContent).toContain('第 2 句：来源范围不连续。'));
  expect(publishSourceLearning).not.toHaveBeenCalled();
  client.clear();
});

it('reads a result file and clears a previous preview on read failure', async () => {
  vi.mocked(previewSourceLearning).mockResolvedValue(sourcePreview);
  const client = await renderReadingPage();
  await vi.waitFor(() => expect(byLabel('预览原句与词块').disabled).toBe(false));
  const input = container.querySelector('input[type=file]')!;
  await act(async () => {
    Object.defineProperty(input, 'files', { configurable: true, value: [{ name: 'result.json', size: 10, text: async () => 'file JSON' }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(previewSourceLearning).toHaveBeenCalledWith('video-id', 'file JSON'));
  await act(async () => {
    Object.defineProperty(input, 'files', { configurable: true, value: [{ name: 'broken.json', size: 10, text: async () => { throw new Error('read failed'); } }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  expect(container.querySelector('.learning-proof')).toBeNull();
  expect(container.textContent).toContain('无法读取这个文件');
  expect(publishSourceLearning).not.toHaveBeenCalled();
  client.clear();
});

it('keeps the current reading revision when source confirmation conflicts', async () => {
  vi.mocked(previewSourceLearning).mockResolvedValue(sourcePreview);
  vi.mocked(publishSourceLearning).mockRejectedValue(new Error('当前字幕已变化，请重新预览。'));
  const client = await renderReadingPage();
  await vi.waitFor(() => expect(byLabel('预览原句与词块').disabled).toBe(false));
  await enterResult('complete returned result');
  await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(container.querySelector('.learning-proof')).not.toBeNull());
  await act(async () => byLabel('确认发布原句与词块').click());
  await vi.waitFor(() => expect(container.textContent).toContain('当前字幕已变化，请重新预览。'));
  expect(container.querySelector('.learning-proof')).toBeNull();
  expect(container.querySelector('.transcript-list')!.textContent).toContain('Earlier sentence.');
  expect(client.getQueryData<{revision_id: string}>(['transcript', 'video-id'])!.revision_id).toBe('revision-id');
  client.clear();
});

it('reports clipboard denial and rejects oversized files without publishing', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: vi.fn().mockRejectedValue(new Error('permission denied')) } });
  const client = await renderReadingPage();
  await vi.waitFor(() => expect(byLabel('复制任务与原始字幕').disabled).toBe(false));
  await act(async () => byLabel('复制任务与原始字幕').click());
  await vi.waitFor(() => expect(container.textContent).toContain('请检查浏览器剪贴板权限'));
  const input = container.querySelector('input[type=file]')!;
  const read = vi.fn();
  await act(async () => {
    Object.defineProperty(input, 'files', { configurable: true, value: [{ name: 'huge.json', size: 1_048_577, text: read }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  expect(container.textContent).toContain('文件超过 1 MiB');
  expect(read).not.toHaveBeenCalled();
  expect(publishSourceLearning).not.toHaveBeenCalled();
  client.clear();
});


it('supports roving keyboard focus and hides inactive panels from assistive technology', async () => {
  const client = await renderReadingPage();
  const first = container.querySelector('#reading-tab-transcript') as HTMLButtonElement;
  first.focus();
  await act(async () => first.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })));
  expect(document.activeElement?.id).toBe('reading-tab-favorites');
  expect(first.tabIndex).toBe(-1);
  expect(container.querySelector('#reading-panel-transcript')?.getAttribute('aria-hidden')).toBe('true');
  expect(container.querySelector('#reading-panel-transcript')?.hasAttribute('inert')).toBe(true);
  expect(container.querySelector('#reading-panel-favorites')?.hasAttribute('inert')).toBe(false);
  await act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true })));
  expect(document.activeElement?.id).toBe('reading-tab-favorites');
  await act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })));
  expect(document.activeElement?.id).toBe('reading-tab-transcript');
  await act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true })));
  expect(document.activeElement?.id).toBe('reading-tab-favorites');
  await act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true })));
  expect(document.activeElement?.id).toBe('reading-tab-transcript');
  expect(playerHandle.seekTo).not.toHaveBeenCalled();
  expect(playerHandle.play).not.toHaveBeenCalled();
  client.clear();
});

it('does not follow hidden subtitles and resumes following the current sentence on return', async () => {
  const originalScroll = HTMLElement.prototype.scrollTo;
  const scroll = vi.fn(function (this: HTMLElement) {
    this.dispatchEvent(new Event('scroll'));
  });
  HTMLElement.prototype.scrollTo = scroll;
  try {
    const client = await renderReadingPage();
    await clickControl('.report-time');
    const before = scroll.mock.calls.length;
    expect(before).toBeGreaterThan(0);
    await clickControl('#reading-tab-favorites');
    playerHandle.time = 2.5;
    await clickControl('.report-time');
    expect(scroll).toHaveBeenCalledTimes(before);
    await clickControl('#reading-tab-transcript');
    expect(scroll).toHaveBeenCalledTimes(before + 1);
    expect(container.querySelector('.transcript-follow-control')).toBeNull();
    expect(playerHandle.play).not.toHaveBeenCalled();
    client.clear();
  } finally {
    if (originalScroll) HTMLElement.prototype.scrollTo = originalScroll;
    else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo');
  }
});


async function menuAction(label: string) {
  await clickControl('.segment-mark-whole');
  await act(async () => [...container.querySelectorAll<HTMLButtonElement>('.reader-selection-menu button')]
    .find(button => button.textContent === label)!.click());
}
const existingFavorite: TranscriptMark = {
  id: 'existing', video_id: 'video-id', revision_id: 'revision-id', revision_number: 1,
  revision_origin: 'generated', is_current: true, segment_id: 'one', segment_sequence_index: 0,
  segment_start: 2, segment_end: 4, segment_text: 'Earlier sentence.', start_offset: 0, end_offset: 17,
  selected_text: 'Earlier sentence.', created_at: '', updated_at: '',
};

it.each([true, false])('offers undo only for a newly created favorite (%s)', async created => {
  vi.mocked(createTranscriptFavorite).mockResolvedValue({ item: existingFavorite, created });
  const client = await renderReadingPage();
  await menuAction('收藏');
  expect(container.querySelector('.reader-selection-menu')).toBeNull();
  const undo = [...container.querySelectorAll<HTMLButtonElement>('.reader-notice button')].find(button => button.textContent === '撤销');
  expect(!!undo).toBe(created);
  if (undo) { await act(async () => undo.click()); expect(deleteTranscriptMark).toHaveBeenCalledWith('video-id', 'existing'); }
  else expect(deleteTranscriptMark).not.toHaveBeenCalled();
  expect(playerHandle.play).not.toHaveBeenCalled(); expect(playerHandle.seekTo).not.toHaveBeenCalled();
  client.clear();
});

it('keeps the selection and allows retry when quick favorite fails', async () => {
  vi.mocked(createTranscriptFavorite).mockRejectedValueOnce(new Error('network failed'))
    .mockResolvedValueOnce({ item: existingFavorite, created: true });
  const client = await renderReadingPage();
  await menuAction('收藏');
  expect(container.querySelector('.reader-selection-menu')?.textContent).toContain('network failed');
  expect(container.querySelector('.reader-selection-menu')?.textContent).toContain('Earlier sentence.');
  await clickControl('.reader-selection-menu button');
  expect(container.querySelector('.reader-selection-menu')).toBeNull();
  expect(createTranscriptFavorite).toHaveBeenCalledTimes(2);
  client.clear();
});


it('replays old collection context at its saved time while keeping the current revision and player', async () => {
  vi.mocked(getTranscriptMarks).mockResolvedValue({ items: [{ ...existingFavorite, is_current: false,
    revision_id: 'old', revision_number: 1, segment_id: 'old-segment', segment_start: 7.75,
    segment_text: 'Old expression in an older sentence.' }] });
  const client = await renderReadingPage(); await clickControl('#reading-tab-favorites');
  await act(async () => [...container.querySelectorAll<HTMLButtonElement>('.favorites-panel button')].find(b => b.textContent === '回听旧版')!.click());
  expect(playerHandle.seekTo).toHaveBeenCalledWith(7.75); expect(playerHandle.play).toHaveBeenCalledOnce();
  expect(container.querySelector('.transcript-list')?.textContent).toContain('Earlier sentence.');
  expect(container.querySelector('.transcript-list')?.textContent).not.toContain('Old expression');
  expect(client.getQueryData<{revision_id: string}>(['transcript', 'video-id'])?.revision_id).toBe('revision-id');
   expect(publishSourceLearning).not.toHaveBeenCalled();
  expect(playerHandle.mounted).toHaveBeenCalledOnce(); client.clear();
});


it('keeps translated English anchors exact when saving a favorite and showing chunks', async () => {
  vi.mocked(getTranscript).mockResolvedValue({ video_id: 'video-id', revision_id: 'revision-id', origin: 'source_aligned',
    normalization_version: null, segments: [{ id: 'two', sequence_index: 0, start: 10, end: 12,
      text: 'Current sentence.', translation_zh: '当前这句话。' }] });
  vi.mocked(createTranscriptFavorite).mockResolvedValue({ item: existingFavorite, created: true });
  const client = await renderReadingPage();
  await act(async () => (container.querySelector('.transcript-heading-tools input') as HTMLInputElement).click());
  await act(async () => client.setQueryData(['chunk-layout', 'video-id', 'revision-id'], {
    video_id: 'video-id', revision_id: 'revision-id', layout: { id: 'layout', revision_id: 'revision-id', segments: [
      { segment_id: 'two', text: 'Current sentence.', boundary_offsets: [7], chunks: ['Current', 'sentence.'] }] } }));
  await vi.waitFor(() => expect([...container.querySelectorAll('.transcript-panel button')].some(b => b.textContent === '词块')).toBe(true));
  await act(async () => [...container.querySelectorAll<HTMLButtonElement>('.transcript-panel button')].find(b => b.textContent === '词块')!.click());
  expect(container.querySelector('.segment-translation')?.textContent).toBe('当前这句话。');
  expect(container.querySelector('.segment-readable')?.textContent).toBe('Current sentence.');
  await menuAction('收藏');
  await vi.waitFor(() => expect(createTranscriptFavorite).toHaveBeenCalled());
  expect(vi.mocked(createTranscriptFavorite).mock.lastCall?.[1]).toEqual({ revision_id: 'revision-id', segment_id: 'two',
    start_offset: 0, end_offset: 17, selected_text: 'Current sentence.' });
  expect(playerHandle.seekTo).not.toHaveBeenCalled(); client.clear();
});

it('copies the manual preservation task based on actual source even after an auto preference', async () => {
  vi.mocked(getVideo).mockResolvedValue({ ...readyVideo, subtitle_preference: 'auto_only' });
  const manualSource: LearningSource = { format: 'learning-source-v2', source_type: 'youtube_manual',
    processing_mode: 'manual_cues', source_video_id: 'M7lc1UVf-VE', source_digest: 'b'.repeat(64),
    extractor_version: 'youtube-manual-cues-v1', units: [{ id: 'u000001', text: 'Raw manual.', start_ms: 1000, time_basis: 'cue_start' }] };
  let resolveInitial!: (source: LearningSource) => void;
  let resolveRefresh!: (source: LearningSource) => void;
  vi.mocked(getLearningSource)
    .mockImplementationOnce(() => new Promise(resolve => { resolveInitial = resolve; }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveRefresh = resolve; }));
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  const client = await renderReadingPage();
  expect(byLabel('复制任务与原始字幕').disabled).toBe(true);
  await act(async () => resolveInitial(manualSource));
  await vi.waitFor(() => expect(byLabel('复制任务与原始字幕').disabled).toBe(false));
  await act(async () => byLabel('复制任务与原始字幕').click());
  expect(getLearningSource).toHaveBeenCalledTimes(2);
  expect(writeText).not.toHaveBeenCalled();
  await act(async () => resolveRefresh(manualSource));
  await vi.waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  expect(writeText.mock.lastCall?.[0]).toContain('不纠错、不增删、不润色、不重新断句');
  expect(writeText.mock.lastCall?.[0]).not.toContain('修正明确的错听');
  expect(container.textContent).toContain('导入偏好：自动字幕');
  expect(container.textContent).toContain('人工英文字幕'); client.clear();
});

it('explains old revisions without Chinese and leaves all three switches off on a fresh page', async () => {
  let client = await renderReadingPage();
  await act(async () => (container.querySelector('.transcript-heading-tools input') as HTMLInputElement).click());
  expect(container.querySelector('.transcript-panel')?.textContent).toContain('此版本尚无中文');
  expect(container.querySelectorAll('.segment-translation')).toHaveLength(0);
  await act(async () => root.render(null)); client.clear(); client = await renderReadingPage();
  expect((container.querySelector('.transcript-heading-tools input') as HTMLInputElement).checked).toBe(false);
  expect((container.querySelector('.learning-player-controls input') as HTMLInputElement).checked).toBe(false);
  client.clear();
});

const episodeFixture = {
  id: 'course', name: 'Course', description: null, version: 1, source_playlist_id: null,
  source_playlist_url: null, created_at: '', updated_at: '', thumbnail_url: null, total_count: 2, ready_count: 2,
  items: [{ id: 'member1', position: 0, video: readyVideo },
    { id: 'member2', position: 1, video: { ...readyVideo, id: 'next', youtube_video_id: 'abcdefghijk', title: 'Next episode' } }],
};
it.each(['removed', 'deleted'])('keeps independent reading for %s collection context', async context => {
  if (context === 'removed') vi.mocked(getCollection).mockResolvedValue({ ...episodeFixture, items: [] });
  else vi.mocked(getCollection).mockRejectedValue(new ApiError('missing', 404, 'COLLECTION_NOT_FOUND'));
  const client = await renderReadingPage('/videos/video-id?collection=course');
  await vi.waitFor(() => expect(container.textContent).toContain('仍可独立阅读'));
  expect(container.querySelector('.episode-navigation')).toBeNull();
  expect(container.querySelector('.transcript-list')).not.toBeNull();
  expect(playerHandle.mounted).toHaveBeenCalledOnce(); client.clear();
});
it('does not choose a collection when opened outside its context', async () => {
  const client = await renderReadingPage();
  expect(getCollection).not.toHaveBeenCalled(); expect(container.querySelector('.episode-directory')).toBeNull(); client.clear();
});

it('keeps complete transcript and favorite exports independent in their own tabs', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  vi.mocked(getTranscriptMarks).mockResolvedValue({ items: [existingFavorite] });
  const client = await renderReadingPage();
  expect([...container.querySelectorAll('[role="tab"]')].map(tab => tab.textContent)).toEqual(['字幕', '收藏']);
  await act(async () => [...container.querySelectorAll<HTMLButtonElement>('#reading-panel-transcript button')]
    .find(button => button.textContent === '复制完整字幕')!.click());
  expect(writeText).toHaveBeenLastCalledWith('Video\n\nEarlier sentence.\n\nCurrent sentence.');
  await clickControl('#reading-tab-favorites');
  await act(async () => [...container.querySelectorAll<HTMLButtonElement>('#reading-panel-favorites button')]
    .find(button => button.textContent === '复制全部收藏')!.click());
  expect(writeText).toHaveBeenLastCalledWith('Video\n\n1.\n表达：Earlier sentence.\n原句：Earlier sentence.');
  expect(writeText.mock.lastCall?.[0]).not.toContain('Current sentence.');
  expect(container.querySelector('#reading-tab-questions')).toBeNull();
  expect(playerHandle.mounted).toHaveBeenCalledOnce();
  client.clear();
});


it('keeps preview, list and overlay Chinese independent without moving playback', async () => {
  vi.mocked(getTranscript).mockResolvedValue({ video_id: 'video-id', revision_id: 'revision-id', origin: 'source_aligned',
    normalization_version: null, segments: [{ id: 'two', sequence_index: 0, start: 10, end: 12,
      text: 'Current sentence.', translation_zh: '当前这句话。' }] });
  vi.mocked(previewSourceLearning).mockResolvedValue(sourcePreview);
  const client = await renderReadingPage(); await clickControl('.report-time');
  const listToggle = container.querySelector('.transcript-heading-tools input') as HTMLInputElement;
  const overlayToggle = container.querySelector('.learning-player-controls input') as HTMLInputElement;
  expect(listToggle.checked).toBe(false); expect(overlayToggle.checked).toBe(false);
  await act(async () => listToggle.click());
  expect(container.querySelector('.segment-translation')?.textContent).toBe('当前这句话。');
  expect(container.querySelector('.player-subtitle-translation')).toBeNull();
  await act(async () => overlayToggle.click());
  expect(container.querySelector('.player-subtitle-translation')?.textContent).toBe('当前这句话。');
  await enterResult('bilingual result'); await act(async () => byLabel('预览原句与词块').click());
  await vi.waitFor(() => expect(container.querySelector('.learning-proof')).not.toBeNull());
  const previewToggle = container.querySelector('.learning-proof input') as HTMLInputElement;
  expect(previewToggle.checked).toBe(false);
  await act(async () => previewToggle.click());
  expect(container.querySelector('.learning-proof')?.textContent).toContain('让我知道最新情况。');
  await act(async () => previewToggle.click());
  expect(container.querySelector('.segment-translation')).not.toBeNull();
  expect(playerHandle.mounted).toHaveBeenCalledOnce(); expect(playerHandle.destroyed).not.toHaveBeenCalled();
  expect(playerHandle.seekTo).not.toHaveBeenCalled(); expect(playerHandle.play).not.toHaveBeenCalled();
  expect(publishSourceLearning).not.toHaveBeenCalled(); client.clear();
});

it('keeps the player while collapsing the directory and clears old reading state on episode switch', async () => {
  vi.mocked(getCollection).mockResolvedValue(episodeFixture);
  vi.mocked(getVideo).mockImplementation(async id => id === 'next' ? episodeFixture.items[1].video : readyVideo);
  vi.mocked(getTranscript).mockImplementation(async id => ({ video_id: id, revision_id: id + '-revision', origin: 'generated', normalization_version: 2,
    segments: id === 'next' ? [{ id: 'next-line', sequence_index: 0, start: 10, end: 12, text: 'New episode only.' }] : [
      { id: 'one', sequence_index: 0, start: 2, end: 4, text: 'Earlier sentence.' },
      { id: 'two', sequence_index: 1, start: 10, end: 12, text: 'Current sentence.' }] }));
  const client = await renderReadingPage('/videos/video-id?collection=course');
  await vi.waitFor(() => expect(container.querySelector('.episode-directory')).not.toBeNull());
  const buttons = () => container.querySelectorAll<HTMLButtonElement>('.episode-navigation button');
  expect(buttons()[0].disabled).toBe(true); expect(buttons()[1].disabled).toBe(false);
  await clickControl('.report-time');
  expect(container.querySelector('.player-subtitle')?.textContent).toBe('Current sentence.');
  await act(async () => { const details = container.querySelector('.episode-directory details') as HTMLDetailsElement; details.open = true; details.open = false; });
  expect(playerHandle.mounted).toHaveBeenCalledOnce(); expect(playerHandle.destroyed).not.toHaveBeenCalled();
  await act(async () => buttons()[1].click());
  await vi.waitFor(() => expect(container.querySelector('.transcript-list')?.textContent).toContain('New episode only.'));
  expect(container.querySelector('.transcript-list')?.textContent).not.toContain('Earlier sentence.');
  expect(container.querySelector('.player-subtitle')).toBeNull();
  expect(buttons()[1].disabled).toBe(true); expect(buttons()[0].disabled).toBe(false);
  expect(playerHandle.destroyed).toHaveBeenCalledOnce(); expect(playerHandle.mounted).toHaveBeenCalledTimes(2);
  expect(playerHandle.play).not.toHaveBeenCalled(); expect(playerHandle.seekTo).not.toHaveBeenCalled();
  client.clear();
});

it('suspends following during selection and restores previous automatic mode', async () => {
  const original = HTMLElement.prototype.scrollTo;
  const scroll = vi.fn(); HTMLElement.prototype.scrollTo = scroll;
  try {
    const client = await renderReadingPage(); await clickControl('.report-time');
    const before = scroll.mock.calls.length;
    await clickControl('.segment-mark-whole'); playerHandle.time = 2.5; await clickControl('.report-time');
    expect(scroll).toHaveBeenCalledTimes(before);
    await clickControl('.reader-selection-menu [aria-label="关闭选字菜单"]');
    expect(scroll).toHaveBeenCalledTimes(before + 1);
    expect(playerHandle.mounted).toHaveBeenCalledOnce(); expect(playerHandle.play).not.toHaveBeenCalled();
    client.clear();
  } finally { if (original) HTMLElement.prototype.scrollTo = original; else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo'); }
});
