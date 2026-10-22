import type { ChunkLayout, Transcript } from '../../types/video';

export type ReadingMode = 'sentence' | 'chunks';

export function hasCurrentChunkLayout(transcript: Transcript | undefined, layout: ChunkLayout | null | undefined): boolean {
  if (!transcript || layout?.revision_id !== transcript.revision_id || !transcript.segments.length) return false;
  const ids = new Set(layout.segments.map(segment => segment.segment_id));
  return ids.size === transcript.segments.length && transcript.segments.every(segment => ids.has(segment.id));
}

interface Props {
  mode: ReadingMode;
  onChange: (mode: ReadingMode) => void;
  available: boolean;
  loading?: boolean;
  onOpenTools?: () => void;
}

export default function TranscriptViewSwitch({ mode, onChange, available, loading = false, onOpenTools }: Props) {
  return <div className="transcript-view-switch" role="group" aria-label="字幕阅读方式">
    <button type="button" aria-pressed={mode === 'sentence' || !available}
      onClick={() => onChange('sentence')}>原句</button>
    {available
      ? <button type="button" aria-pressed={mode === 'chunks'} onClick={() => onChange('chunks')}>词块</button>
      : <button type="button" aria-pressed={false} disabled={loading}
        onClick={onOpenTools}>{loading ? '读取词块…' : '设置词块'}</button>}
  </div>;
}
