import { afterEach, expect, it } from 'vitest';
import { AxiosError } from 'axios';
import { api, ApiError } from './client';
import {
  createTranscriptFavorite, createTranscriptQuestion, updateTranscriptQuestion,
  deleteTranscriptMark, deleteTranscriptQuestion,
  getRawSrt, getLearningSource, getLearningSrt, previewSourceLearning, publishSourceLearning,
  getTranscriptRevisions,
  getTranscriptRevision,
  getTranscript,
  getTranscriptMarks,
  getVideos,
  importVideo,
  updateTranscriptMarkNote,
} from './videos';

const originalAdapter = api.defaults.adapter;
afterEach(() => { api.defaults.adapter = originalAdapter; });

it('unwraps the library response', async () => {
  api.defaults.adapter = async config => ({ data: { items: [] }, status: 200, statusText: 'OK', headers: {}, config });
  await expect(getVideos()).resolves.toEqual({ items: [] });
});

it('unwraps the learning transcript without changing its segment order', async () => {
  const data = { video_id: 'video-id', revision_id: 'revision-id', origin: 'generated', normalization_version: 1, segments: [
    { id: 'one', sequence_index: 0, start: 1.25, end: 2.5, text: 'Hello.' },
  ] };
  api.defaults.adapter = async config => ({ data, status: 200, statusText: 'OK', headers: {}, config });
  await expect(getTranscript('video/id')).resolves.toEqual(data);
});

it('gets the Raw-derived SRT as text', async () => {
  const requests: Array<{ url?: string; responseType?: string }> = [];
  api.defaults.adapter = async config => {
    requests.push({ url: config.url, responseType: config.responseType });
    return { data: '1\n00:00:00,000 --> 00:00:01,000\nHello\n', status: 200,
      statusText: 'OK', headers: {}, config };
  };
  await expect(getRawSrt('video/id')).resolves.toContain('Hello');
  expect(requests).toEqual([{ url: '/videos/video%2Fid/transcript/export.srt', responseType: 'text' }]);
});

it('retains read-only historical versions', async () => {
  const requests: Array<{ method?: string; url?: string; data?: unknown }> = [];
  api.defaults.adapter = async config => {
    requests.push({ method: config.method, url: config.url, data: JSON.parse(config.data ?? '{}') });
    return { data: { items: [] }, status: 200, statusText: 'OK', headers: {}, config };
  };
  await getTranscriptRevisions('video/id');
  await getTranscriptRevision('video/id', 'old/id');
  expect(requests).toEqual([
    { method: 'get', url: '/videos/video%2Fid/transcript/revisions', data: {} },
    { method: 'get', url: '/videos/video%2Fid/transcript/revisions/old%2Fid', data: {} },
  ]);
});

it('uses video-scoped mark endpoints and only sends a note when editing', async () => {
  const requests: Array<{ method?: string; url?: string; data?: unknown }> = [];
  api.defaults.adapter = async config => {
    requests.push({ method: config.method, url: config.url,
      data: config.data ? JSON.parse(config.data) : undefined });
    return { data: { items: [] }, status: 200, statusText: 'OK', headers: {}, config };
  };
  await getTranscriptMarks('video/id');
  await createTranscriptFavorite('video/id', { revision_id: 'r', segment_id: 's',
    start_offset: 0, end_offset: 5, selected_text: 'Hello', note: null });
  await updateTranscriptMarkNote('video/id', 'mark/id', 'Personal note');
  await deleteTranscriptMark('video/id', 'mark/id');
  expect(requests).toEqual([
    { method: 'get', url: '/videos/video%2Fid/marks', data: undefined },
    { method: 'post', url: '/videos/video%2Fid/marks', data: {
      revision_id: 'r', segment_id: 's', start_offset: 0, end_offset: 5,
      selected_text: 'Hello', note: null,
    } },
    { method: 'patch', url: '/videos/video%2Fid/marks/mark%2Fid',
      data: { note: 'Personal note' } },
    { method: 'delete', url: '/videos/video%2Fid/marks/mark%2Fid', data: undefined },
  ]);
});

it.each([200, 202])('unwraps import HTTP %s without losing duplicate identity', async status => {
  const data = { already_exists: status === 200, video: { id: 'saved-id' }, job: null };
  api.defaults.adapter = async config => ({ data, status, statusText: 'OK', headers: {}, config });
  await expect(importVideo('https://youtu.be/aB3_dE-fGhI')).resolves.toEqual(data);
});

it('preserves the user-facing API error', async () => {
  api.defaults.adapter = async config => {
    throw new AxiosError('Bad request', 'ERR_BAD_REQUEST', config, undefined, {
      data: { error: { code: 'INVALID_YOUTUBE_URL', message: '链接无效' } },
      status: 422, statusText: 'Unprocessable Entity', headers: {}, config,
    });
  };
  await expect(importVideo('bad')).rejects.toMatchObject({ status: 422, code: 'INVALID_YOUTUBE_URL', message: '链接无效' });
});

it('turns a network failure into a readable error', async () => {
  api.defaults.adapter = async config => { throw new AxiosError('Network Error', 'ERR_NETWORK', config); };
  await expect(getVideos()).rejects.toBeInstanceOf(ApiError);
  await expect(getVideos()).rejects.toThrow('无法连接服务');
});

it('keeps source result requests separate from legacy SRT and exports published text', async () => {
  const requests: Array<{ url?: string; data?: unknown; responseType?: string }> = [];
  api.defaults.adapter = async config => {
    requests.push({ url: config.url, data: config.data ? JSON.parse(config.data) : undefined,
      responseType: config.responseType });
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
  };
  await getLearningSource('video/id');
  await previewSourceLearning('video/id', 'returned-json');
  await publishSourceLearning('video/id', 'returned-json', 'base-revision', 'digest');
  await getLearningSrt('video/id');
  expect(requests.map(r => r.url)).toEqual([
    '/videos/video%2Fid/transcript/learning-source',
    '/videos/video%2Fid/transcript/source-learning/preview',
    '/videos/video%2Fid/transcript/source-learning',
    '/videos/video%2Fid/transcript/learning-export.srt',
  ]);
  expect(requests[1].data).toEqual({ result: 'returned-json' });
  expect(requests[2].data).toEqual({ result: 'returned-json', expected_revision_id: 'base-revision', preview_digest: 'digest' });
  expect(requests[3].responseType).toBe('text');
});

it.each([200, 201])('distinguishes duplicate and created favorites by HTTP status %s', async status => {
  const item = { id: 'canonical' };
  api.defaults.adapter = async config => ({ data: item, status, statusText: 'OK', headers: {}, config });
  await expect(createTranscriptFavorite('video/id', { revision_id: 'r', segment_id: 's',
    start_offset: 0, end_offset: 1, selected_text: 'A' })).resolves.toEqual({ item, created: status === 201 });
});

it('sends manual question anchors and answer-only patches without changing the question', async () => {
  const requests: Array<{ url?: string; method?: string; data: unknown }> = [];
  api.defaults.adapter = async config => {
    requests.push({ url: config.url, method: config.method, data: JSON.parse(config.data) });
    return { data: { id: 'q' }, status: 201, statusText: 'OK', headers: {}, config };
  };
  await createTranscriptQuestion('video/id', { revision_id: 'r', segment_id: 's',
    start_offset: 1, end_offset: 2, selected_text: '😀' }, 'Why?', 'Manual');
  await updateTranscriptQuestion('video/id', 'q/id', { answer: null });
  expect(requests).toEqual([
    { url: '/videos/video%2Fid/questions', method: 'post', data: { revision_id: 'r', segment_id: 's',
      start_offset: 1, end_offset: 2, selected_text: '😀', question: 'Why?', answer: 'Manual' } },
    { url: '/videos/video%2Fid/questions/q%2Fid', method: 'patch', data: { answer: null } },
  ]);
});


it('deletes only the selected question using encoded video and record identifiers', async () => {
  let request: { url?: string; method?: string } | undefined;
  api.defaults.adapter = async config => {
    request = { url: config.url, method: config.method };
    return { data: null, status: 204, statusText: 'No Content', headers: {}, config };
  };
  await deleteTranscriptQuestion('video/id', 'question/id');
  expect(request).toEqual({ url: '/videos/video%2Fid/questions/question%2Fid', method: 'delete' });
});


it.each(['manual_first', 'auto_only'] as const)('persists the selected import preference %s', async preference => {
  let data: unknown;
  api.defaults.adapter = async config => {
    data = JSON.parse(config.data);
    return { data: {}, status: 202, statusText: 'OK', headers: {}, config };
  };
  await importVideo('https://youtu.be/abcdefghijk', preference);
  expect(data).toEqual({ url: 'https://youtu.be/abcdefghijk', subtitle_preference: preference });
});
