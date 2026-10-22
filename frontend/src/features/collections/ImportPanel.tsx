import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getCollections, previewImport, submitBatch } from '../../api/collections';
import type { BatchRequest, ImportTarget, InputKind, Preview } from '../../types/collections';
import type { SubtitlePreference } from '../../types/video';
import ImportVideoForm from '../library/ImportVideoForm';
import CollectionFields from './CollectionFields';
import { hasVideoAndPlaylist, IntentKey, moveItem, refreshLibrary } from './shared';

export default function ImportPanel({ collectionId }: { collectionId?: string }) {
  const [mode, setMode] = useState<InputKind>('single');
  const [text, setText] = useState('');
  const [scope, setScope] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [order, setOrder] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [preference, setPreference] = useState<SubtitlePreference>('manual_first');
  const [target, setTarget] = useState(collectionId ?? 'none');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const keys = useRef(new IntentKey());
  const navigate = useNavigate(), client = useQueryClient();
  const collections = useQuery({ queryKey: ['collections'], queryFn: ({ signal }) => getCollections(signal), enabled: !!preview });
  const parsing = useMutation({ mutationFn: (input: { kind: InputKind; urls: string[] }) => previewImport(input.kind, input.urls),
    onSuccess: result => {
      setPreview(result); setOrder(result.items.map(item => item.id));
      setSelected(result.items.filter(item => item.selectable).map(item => item.id));
    } });
  const submission = useMutation({ mutationFn: (payload: BatchRequest) => submitBatch(payload),
    onSuccess: result => { void refreshLibrary(client); navigate(`/imports/${result.id}`); } });
  const busy = parsing.isPending || submission.isPending;
  const mixed = mode !== 'multiple' && hasVideoAndPlaylist(text);
  const mixedMultiple = mode === 'multiple' && text.split(/\r?\n/).some(hasVideoAndPlaylist);
  const reset = () => { setPreview(null); parsing.reset(); submission.reset(); };
  const chooseMode = (value: InputKind) => { setMode(value); setScope(''); reset(); };
  const ordered = order.flatMap(id => { const item = preview?.items.find(value => value.id === id); return item ? [item] : []; });
  return <section className="import-panel" aria-label="导入素材">
    <div className="mode-tabs" role="group" aria-label="导入方式">
      {([['single', '单个视频'], ['multiple', '多个链接'], ['playlist', '播放列表']] as const).map(([value, label]) =>
        <button key={value} aria-pressed={mode === value} disabled={busy} onClick={() => chooseMode(value)}>{label}</button>)}
    </div>
    {mode === 'single' && !collectionId ? <ImportVideoForm onPlaylist={url => { setText(url); chooseMode('playlist'); setScope('playlist'); }} /> : <>
      {!preview && <form className="import-form" onSubmit={event => {
        event.preventDefault();
        const urls = mode === 'multiple' ? text.split(/\r?\n/).map(line => line.trim()).filter(Boolean) : [text.trim()];
        if (urls.length && (!(mixed || mixedMultiple) || scope) && !busy) parsing.mutate({ kind: mixed ? scope as InputKind : mode, urls });
      }}>
        <label htmlFor="batch-links">{mode === 'multiple' ? '每行一个 YouTube 视频链接' : mode === 'playlist' ? 'YouTube 播放列表链接' : 'YouTube 视频链接'}</label>
        <textarea id="batch-links" rows={mode === 'multiple' ? 5 : 2} required value={text} disabled={busy}
          onChange={event => { setText(event.target.value); setScope(''); parsing.reset(); }} />
        {mixed && <fieldset><legend>链接同时包含视频与播放列表，请选择范围</legend>
          <label><input type="radio" name="batch-scope" checked={scope === 'single'} onChange={() => setScope('single')} />仅此视频</label>
          <label><input type="radio" name="batch-scope" checked={scope === 'playlist'} onChange={() => setScope('playlist')} />整个播放列表</label>
        </fieldset>}
        {mixedMultiple && <fieldset><legend>部分链接同时包含视频与播放列表</legend>
          <label><input type="radio" name="multiple-scope" checked={scope === 'single'} onChange={() => setScope('single')} />仅导入各视频，不展开播放列表</label>
          <p className="form-hint">如需整个播放列表，请切换到“播放列表”入口并粘贴一条列表链接。</p>
        </fieldset>}
        <p className="form-hint">最多200条。多链接入口不展开播放列表；请使用播放列表入口。预览不会创建视频或任务。</p>
        <button className="primary-button" disabled={!text.trim() || busy || ((mixed || mixedMultiple) && !scope)}>{parsing.isPending ? '正在读取列表…' : '解析预览'}</button>
        {parsing.isError && <p role="alert" className="error-message">{parsing.error.message}</p>}
      </form>}
      {preview && <div className="import-preview">
        <h2>{preview.source.title ?? '确认导入内容'}</h2>
        <p className="muted">已选 {selected.length} 条 · 重复 {preview.duplicate_count} 条已合并 · 预览有效至 {new Date(preview.expires_at).toLocaleTimeString()}</p>
        <div className="collection-actions"><button disabled={busy} onClick={() => setSelected(preview.items.filter(item => item.selectable).map(item => item.id))}>全选可导入项</button>
          <button disabled={busy} onClick={() => setSelected([])}>取消全选</button></div>
        {ordered.length === 0 && <p>列表为空，请返回修改链接。</p>}
        <ol className="episode-list preview-list">{ordered.map((item, index) => <li key={item.id}>
          <label className="episode-content"><input type="checkbox" checked={selected.includes(item.id)} disabled={!item.selectable || busy}
            onChange={event => setSelected(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} />
            <span><strong>{item.title ?? item.youtube_video_id ?? `源条目 ${item.source_position + 1}`}</strong>
              <small>{item.error?.message ?? (item.existing_video_id ? '已有视频 · 沿用已保存字幕来源，不自动重试' : '新视频 · 可访问性待实际导入确认')}</small></span></label>
          <div className="row-actions"><button aria-label={`上移第${index + 1}项`} disabled={busy || index === 0} onClick={() => setOrder(moveItem(order, index, -1))}>↑</button>
            <button aria-label={`下移第${index + 1}项`} disabled={busy || index === ordered.length - 1} onClick={() => setOrder(moveItem(order, index, 1))}>↓</button></div>
        </li>)}</ol>
        <div className="import-settings">
          <label htmlFor="batch-subtitle-preference">字幕来源</label><select id="batch-subtitle-preference" value={preference} disabled={busy} onChange={event => setPreference(event.target.value as SubtitlePreference)}>
            <option value="manual_first">人工字幕优先（没有时自动）</option><option value="auto_only">自动字幕</option></select>
          <p className="form-hint">仅影响新视频；没有合格英文字幕时在本机转写。已有视频不换源、不自动重试。</p>
          <label htmlFor="batch-target">导入归属</label><select id="batch-target" value={target} disabled={busy} onChange={event => setTarget(event.target.value)}>
            <option value="none">仅加入视频库</option><option value="new">新建合集</option>
            {collectionId && !collections.data?.items.some(item => item.id === collectionId) && <option value={collectionId}>当前合集（读取中）</option>}
            {collections.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          {collections.isPending && <p role="status">正在读取合集…</p>}
          {collections.isError && <p role="alert">{collections.error.message}<button onClick={() => void collections.refetch()}>重新读取合集</button></p>}
          {target === 'new' && <CollectionFields name={name} description={description} onName={setName} onDescription={setDescription} disabled={busy} />}
        </div>
        {submission.isError && <p role="alert" className="error-message">{submission.error.message} 可保留当前选择重试；预览过期时请重新解析。</p>}
        <div className="collection-actions"><button className="primary-button" disabled={busy || !selected.length || (target === 'new' && !name.trim()) || (target !== 'new' && target !== 'none' && !collections.data?.items.some(item => item.id === target))}
          onClick={() => {
            const importTarget: ImportTarget = target === 'none' ? { kind: 'none' } : target === 'new' ? { kind: 'new', name: name.trim(), description: description.trim() || null } : { kind: 'existing', collection_id: target };
            const intent = { preview_id: preview.id, selected_item_ids: order.filter(id => selected.includes(id)), subtitle_preference: preference, target: importTarget };
            submission.mutate({ ...intent, idempotency_key: keys.current.for(intent) });
          }}>{submission.isPending ? '正在提交…' : '确认导入'}</button>
          <button disabled={busy} onClick={reset}>取消预览 / 修改输入</button></div>
      </div>}
    </>}
  </section>;
}
