import { expect, it } from 'vitest';
import type { LearningSource } from '../../types/video';
import { sourceLearningPrompt } from './chunkPrompt';

const source: LearningSource = { format: 'learning-source-v2', source_type: 'youtube_auto',
  processing_mode: 'auto_units', source_video_id: 'abcdefghijk', source_digest: 'a'.repeat(64),
  extractor_version: 'youtube-vtt-units-v1',
  units: [{ id: 'u000001', text: 'Hello', start_ms: 1250, time_basis: 'inline_timestamp' }] };

it('keeps auto correction, complete ranges and local timing while requiring separate Chinese', () => {
  const prompt = sourceLearningPrompt(source);
  expect(prompt).toContain(JSON.stringify(source));
  expect(prompt).toContain('learning-result-v2');
  expect(prompt).toContain('恰好覆盖一次');
  expect(prompt).toContain('每一项必须是完整自然口语句子');
  expect(prompt).toContain('同步调整首末编号');
  expect(prompt).toContain('不要估算、修改或返回');
  expect(prompt).toContain('translation_zh 非空字符串');
  expect(prompt).toContain('简体中文');
  expect(prompt).toContain('中文绝不能替代或混入 text');
  expect(prompt).not.toContain('learning-result-v1');
  expect(prompt).not.toContain('SRT');
});

it('uses manual cue preservation rather than auto correction instructions', () => {
  const manual: LearningSource = { ...source, source_type: 'youtube_manual', processing_mode: 'manual_cues',
    extractor_version: 'youtube-manual-cues-v1' };
  const prompt = sourceLearningPrompt(manual);
  expect(prompt).toContain(JSON.stringify(manual));
  expect(prompt).toContain('first_unit_id 和 last_unit_id 必须相同');
  expect(prompt).toContain('不纠错、不增删、不润色、不重新断句');
  expect(prompt).toContain('不合并、不拆分、不遗漏、不去重、不重排');
  expect(prompt).toContain('包括合法重叠');
  expect(prompt).toContain('translation_zh 非空字符串');
  expect(prompt).not.toContain('修正明确的错听');
  expect(prompt).not.toContain('允许合并或拆分原字幕块');
});

it('does not copy a v2 task around a stale v1 service response', () => {
  expect(() => sourceLearningPrompt({ ...source, format: 'learning-source-v1' } as unknown as LearningSource))
    .toThrow('字幕服务尚未更新');
});
