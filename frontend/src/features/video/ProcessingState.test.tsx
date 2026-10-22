// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it } from 'vitest';
import type { Video } from '../../types/video';
import ProcessingState, { videoRefreshInterval } from './ProcessingState';

let root: Root;
let container: HTMLDivElement;

const video: Video = {
  id: 'video-id', youtube_video_id: 'aB3_dE-fGhI', youtube_url: 'https://youtube.test/watch',
  title: 'Lesson', channel_title: 'Teacher', duration_seconds: 90, thumbnail_url: null,
  status: 'processing', subtitle_preference: 'manual_first', subtitle_source: null, subtitle_language: null,
  created_at: '2026-09-06T00:00:00Z',
  processing: { id: 'job-id', stage: 'fetching_captions', status: 'pending', progress: 10,
    error_code: null, error_message: null },
};

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

it('shows the metadata handoff without claiming captions are running', async () => {
  await act(async () => root.render(<ProcessingState video={video} />));
  expect(container.textContent).toContain('正在查找英文字幕');
  expect(container.querySelector('progress')?.value).toBe(10);
});

it('shows the downloaded VTT handoff without claiming Raw cues exist', async () => {
  const acquired = { ...video, subtitle_source: 'youtube_manual' as const,
    processing: { ...video.processing!, progress: 35 } };
  await act(async () => root.render(<ProcessingState video={acquired} />));
  expect(container.textContent).toContain('人工英文字幕已获取');
  expect(container.textContent).toContain('正在转换并保存原始字幕');
  expect(container.querySelector('progress')?.value).toBe(35);
});

it('shows when the downloaded source is automatic English captions', async () => {
  const acquired = { ...video, subtitle_source: 'youtube_auto' as const,
    processing: { ...video.processing!, progress: 35 } };
  await act(async () => root.render(<ProcessingState video={acquired} />));
  expect(container.textContent).toContain('自动英文字幕已获取');
});

it('shows persisted Raw cues without claiming learning subtitles exist', async () => {
  const raw = { ...video, processing: { ...video.processing!, stage: 'normalizing' as const,
    progress: 80 } };
  await act(async () => root.render(<ProcessingState video={raw} />));
  expect(container.textContent).toContain('原始字幕已保存');
  expect(container.textContent).toContain('正在生成可阅读的学习字幕');
  expect(container.querySelector('progress')?.value).toBe(80);
});

it('explains local audio download and transcription stages', async () => {
  const downloading = { ...video, processing: {
    ...video.processing!, stage: 'downloading_audio' as const, status: 'running' as const,
    progress: 20 } };
  await act(async () => root.render(<ProcessingState video={downloading} />));
  expect(container.textContent).toContain('正在获取转写音频');
  expect(container.textContent).toContain('临时音频');
  expect(container.querySelector('progress')?.value).toBe(20);

  const transcribing = { ...video, processing: {
    ...video.processing!, stage: 'transcribing' as const, status: 'running' as const,
    progress: 40 } };
  await act(async () => root.render(<ProcessingState video={transcribing} />));
  expect(container.textContent).toContain('正在生成英文字幕');
  expect(container.textContent).toContain('较长视频需要更多时间');
  expect(container.querySelector('progress')?.value).toBe(40);
});

it('shows a persisted failure reason', async () => {
  const failed = { ...video, status: 'failed' as const, processing: {
    ...video.processing!, stage: 'failed' as const, status: 'failed' as const,
    error_code: 'METADATA_FETCH_FAILED', error_message: '无法获取视频信息。',
  } };
  const client = new QueryClient();
  await act(async () => root.render(<QueryClientProvider client={client}><ProcessingState video={failed} /></QueryClientProvider>));
  expect(container.textContent).toContain('重试导入');
  client.clear();
  expect(container.querySelector('[role="alert"]')?.textContent).toBe('无法获取视频信息。');
});

it('polls only while the video is processing', () => {
  expect(videoRefreshInterval(video)).toBe(2000);
  expect(videoRefreshInterval({ status: 'ready' })).toBe(false);
  expect(videoRefreshInterval({ status: 'failed' })).toBe(false);
});
