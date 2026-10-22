import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import type { SubtitlePreference } from '../../types/video';
import { importVideo } from '../../api/videos';
import { hasVideoAndPlaylist } from '../collections/shared';

export default function ImportVideoForm({ onPlaylist }: { onPlaylist?: (url: string) => void }) {
  const [url, setUrl] = useState('');
  const [scope, setScope] = useState('');
  const mixed = hasVideoAndPlaylist(url);
  const [preference, setPreference] = useState<SubtitlePreference>('manual_first');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (input: { url: string; preference: SubtitlePreference }) => importVideo(input.url, input.preference),
    onSuccess: result => {
      queryClient.setQueryData(['video', result.video.id], result.video);
      void queryClient.invalidateQueries({ queryKey: ['videos'] });
      navigate(`/videos/${result.video.id}`, { state: { alreadyExists: result.already_exists } });
    },
  });

  return (
    <form className="import-form" onSubmit={event => {
      event.preventDefault();
      if (mutation.isPending || !url.trim() || (mixed && !scope)) return;
      if (mixed && scope === 'playlist') { onPlaylist?.(url.trim()); return; }
      mutation.mutate({ url: url.trim(), preference });
    }}>
      <label htmlFor="video-url">粘贴 YouTube 视频链接</label>
      <div className="import-controls">
        <input id="video-url" type="url" inputMode="url" required maxLength={2048}
          placeholder="https://www.youtube.com/watch?v=…" value={url}
          disabled={mutation.isPending} aria-describedby={mutation.isError ? 'import-error' : 'import-hint'}
          aria-invalid={mutation.isError || undefined}
          onChange={event => { setUrl(event.target.value); setScope(''); mutation.reset(); }} />
        <button className="primary-button" type="submit" disabled={!url.trim() || mutation.isPending || (mixed && !scope)}>
          {mutation.isPending ? '正在保存…' : '导入视频'}<span aria-hidden="true"> ↗</span>
        </button>
      </div>
      {mixed && <fieldset disabled={mutation.isPending}><legend>链接同时包含视频与播放列表，请选择范围</legend>
        <label><input type="radio" name="single-scope" checked={scope === 'single'} onChange={() => setScope('single')} />仅此视频</label>
        {onPlaylist && <label><input type="radio" name="single-scope" checked={scope === 'playlist'} onChange={() => setScope('playlist')} />整个播放列表</label>}
      </fieldset>}
      <div className="import-preference">
        <label htmlFor="subtitle-preference">字幕来源</label>
        <select id="subtitle-preference" value={preference} disabled={mutation.isPending}
          aria-describedby="import-hint" onChange={event => { setPreference(event.target.value as SubtitlePreference); mutation.reset(); }}>
          <option value="manual_first">人工字幕优先（没有时自动）</option>
          <option value="auto_only">自动字幕</option>
        </select>
      </div>
      {mutation.isError && <p className="error-message" id="import-error" role="alert">{mutation.error.message}</p>}
      <p id="import-hint" className="form-hint">支持 watch、短链、Shorts 与 embed。人工优先会先找人工、再找自动英文字幕，都没有时在本机进行语音转写；自动模式只找自动英文字幕，没有时使用本机转写。重复导入沿用已保存来源。</p>
    </form>
  );
}
