import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { addMembers, deleteCollection, getCollection, removeMember, reorderMembers, updateCollection } from '../api/collections';
import { getVideos } from '../api/videos';
import { ApiError } from '../api/client';
import type { CollectionDetail } from '../types/collections';
import CollectionFields from '../features/collections/CollectionFields';
import ImportPanel from '../features/collections/ImportPanel';
import { moveItem, refreshLibrary } from '../features/collections/shared';
import VideoStatus from '../components/VideoStatus';

export default function CollectionPage() {
  const { id = '' } = useParams(), navigate = useNavigate(), client = useQueryClient();
  const [editing, setEditing] = useState(false), [adding, setAdding] = useState(false);
  const [name, setName] = useState(''), [description, setDescription] = useState('');
  const [editVersion, setEditVersion] = useState(0), [selected, setSelected] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);
  const collection = useQuery({ queryKey: ['collection', id], queryFn: ({ signal }) => getCollection(id, signal),
    refetchInterval: current => current.state.data?.items.some(item => item.video.status === 'processing') ? 2000 : 10000 });
  const videos = useQuery({ queryKey: ['videos'], queryFn: ({ signal }) => getVideos(signal), enabled: adding });
  const mutation = useMutation({ mutationFn: (action: () => Promise<CollectionDetail | void>) => action(),
    onSuccess: result => {
      if (result) client.setQueryData(['collection', id], result);
      setEditing(false); setSelected([]); setAdding(false); setDeleting(false);
      void refreshLibrary(client);
    }, onError: error => {
      if (error instanceof ApiError && error.code === 'COLLECTION_VERSION_CONFLICT') void collection.refetch();
    } });
  const data = collection.data, busy = mutation.isPending;
  return <div className="collection-page"><Link className="back-link" to="/?view=collections">← 返回合集</Link>
    {collection.isPending && <p role="status">正在读取合集…</p>}
    {collection.isError && <div role="alert"><p>{collection.error.message}</p><button onClick={() => void collection.refetch()}>重新加载</button></div>}
    {data && <><p className="eyebrow">有序观看 · 共用字幕与笔记</p><h1 className="detail-title">{data.name}</h1>
      {data.description && <p className="collection-description">{data.description}</p>}
      <p className="muted">{data.total_count} 集 · {data.ready_count} 集字幕已就绪</p>
      <div className="collection-actions"><button disabled={busy} onClick={() => { setName(data.name); setDescription(data.description ?? ''); setEditVersion(data.version); setEditing(true); }}>编辑合集</button>
        <button disabled={busy} onClick={() => setAdding(value => !value)}>加入已有视频</button>
        <button disabled={busy} onClick={() => setDeleting(true)}>删除合集</button></div>
      {mutation.isError && <p className="error-message" role="alert">{mutation.error.message}{mutation.error instanceof ApiError && mutation.error.code === 'COLLECTION_VERSION_CONFLICT' && ' 已重新读取目录，请检查最新顺序后重新操作；编辑内容请重新打开核对。'}</p>}
      {editing && <form className="collection-editor" onSubmit={event => { event.preventDefault(); mutation.mutate(() => updateCollection(id, name.trim(), description.trim() || null, editVersion)); }}>
        <CollectionFields name={name} description={description} onName={setName} onDescription={setDescription} disabled={busy} />
        <button disabled={busy || !name.trim()}>保存修改</button><button type="button" disabled={busy} onClick={() => setEditing(false)}>取消编辑</button></form>}
      {deleting && <div className="notice"><p>删除“{data.name}”？仅解除合集关系，视频、字幕与笔记会保留。</p>
        <button disabled={busy} onClick={() => mutation.mutate(async () => { await deleteCollection(id, data.version); navigate('/?view=collections'); })}>确认删除合集</button>
        <button disabled={busy} onClick={() => setDeleting(false)}>取消</button></div>}
      {adding && <section className="collection-editor"><h2>从视频库加入</h2>
        {videos.isPending && <p role="status">正在读取视频…</p>}
        {videos.isError && <p role="alert">{videos.error.message}<button onClick={() => void videos.refetch()}>重新读取</button></p>}
        <ul className="existing-videos">{videos.data?.items.filter(video => !data.items.some(item => item.video.id === video.id)).map(video => <li key={video.id}>
          <label><input type="checkbox" disabled={busy} checked={selected.includes(video.id)} onChange={event => setSelected(current => event.target.checked ? [...current, video.id] : current.filter(value => value !== video.id))} />
            {video.title ?? video.youtube_video_id}</label></li>)}</ul>
        <p className="muted">按勾选顺序追加到末尾；已有成员不会重复加入。</p>
        <button disabled={busy || !selected.length || selected.length > 200} onClick={() => mutation.mutate(() => addMembers(id, selected, data.version))}>加入所选（{selected.length}）</button>
        <button disabled={busy} onClick={() => { setAdding(false); setSelected([]); }}>取消</button></section>}
      <h2 className="directory-heading">集数目录</h2>
      {!data.items.length && <p className="empty-state">这个合集还没有视频，可以加入已有视频或从下方导入。</p>}
      <ol className="episode-list">{data.items.map((item, index) => <li key={item.id}>
        <span className="episode-number">{String(index + 1).padStart(2, '0')}</span>
        <Link className="episode-content" to={`/videos/${item.video.id}?collection=${encodeURIComponent(id)}`}>
          <strong>{item.video.title ?? item.video.youtube_video_id}</strong><small><VideoStatus video={item.video} /></small></Link>
        <div className="row-actions"><button disabled={busy || index === 0} aria-label={`上移第${index + 1}集`} onClick={() => mutation.mutate(() => reorderMembers(id, moveItem(data.items.map(value => value.id), index, -1), data.version))}>↑</button>
          <button disabled={busy || index === data.items.length - 1} aria-label={`下移第${index + 1}集`} onClick={() => mutation.mutate(() => reorderMembers(id, moveItem(data.items.map(value => value.id), index, 1), data.version))}>↓</button>
          <button disabled={busy} aria-label={`移出第${index + 1}集`} onClick={() => mutation.mutate(() => removeMember(id, item.id, data.version))}>移出</button></div>
      </li>)}</ol>
      <details className="collection-import"><summary>导入视频到这个合集</summary><ImportPanel collectionId={id} /></details>
    </>}
  </div>;
}
