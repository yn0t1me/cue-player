import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getVideos } from '../api/videos';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { createCollection, getCollections } from '../api/collections';
import ImportPanel from '../features/collections/ImportPanel';
import CollectionFields from '../features/collections/CollectionFields';
import VideoCard from '../features/library/VideoCard';

export default function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const showCollections = params.get('view') === 'collections';
  const [creating, setCreating] = useState(false), [name, setName] = useState(''), [description, setDescription] = useState('');
  const navigate = useNavigate(), client = useQueryClient();
  const collections = useQuery({ queryKey: ['collections'], queryFn: ({ signal }) => getCollections(signal), enabled: showCollections });
  const create = useMutation({ mutationFn: () => createCollection(name.trim(), description.trim() || null),
    onSuccess: result => { void client.invalidateQueries({ queryKey: ['collections'] }); navigate(`/collections/${result.id}`); } });
  const videos = useQuery({ queryKey: ['videos'], queryFn: ({ signal }) => getVideos(signal) });
  return (
    <>
      <p className="eyebrow">从真实语境开始</p>
      <h1>读懂一句，<br />留住一种表达。</h1>
      <p className="intro">保存想读的视频，为下一次专注学习留一个入口。</p>
      <ImportPanel />
      <nav className="library-tabs" aria-label="视频库视图"><button aria-pressed={showCollections} onClick={() => setParams({ view: 'collections' })}>合集</button>
        <button aria-pressed={!showCollections} onClick={() => setParams({})}>全部视频</button></nav>
      {showCollections ? <section className="library" aria-labelledby="collections-title">
        <div className="section-heading"><h2 id="collections-title">我的合集</h2><button onClick={() => setCreating(value => !value)}>新建合集</button></div>
        {creating && <form className="collection-editor" onSubmit={event => { event.preventDefault(); if (name.trim() && !create.isPending) create.mutate(); }}>
          <CollectionFields name={name} description={description} onName={setName} onDescription={setDescription} disabled={create.isPending} />
          <button disabled={!name.trim() || create.isPending}>创建合集</button><button type="button" disabled={create.isPending} onClick={() => setCreating(false)}>取消</button>
          {create.isError && <p role="alert" className="error-message">{create.error.message}</p>}</form>}
        {collections.isPending && <p role="status">正在读取合集…</p>}
        {collections.isError && <div role="alert"><p>{collections.error.message}</p><button onClick={() => void collections.refetch()}>重新加载</button></div>}
        {collections.data?.items.length === 0 && <p className="empty-state">还没有合集。新建一个合集，按顺序组织想看的视频。</p>}
        <ul className="video-grid">{collections.data?.items.map(item => <li key={item.id}><Link className="video-card" to={`/collections/${item.id}`}>
          <div className="thumbnail">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" /> : <span>合集</span>}</div>
          <div className="card-body"><h3>{item.name}</h3><p>{item.total_count} 集 · {item.ready_count} 集字幕就绪</p></div></Link></li>)}</ul>
      </section> :
      <section className="library" aria-labelledby="library-title">
        <div className="section-heading"><h2 id="library-title">我的视频</h2><span>{videos.data ? `${videos.data.items.length} 个已保存` : '视频库'}</span></div>
        {videos.isPending && <p role="status">正在读取视频库…</p>}
        {videos.isError && <div className="error-panel" role="alert"><p>{videos.error.message}</p>
          <button disabled={videos.isFetching} onClick={() => void videos.refetch()}>重新加载</button></div>}
        {videos.data?.items.length === 0 && <div className="empty-state"><span aria-hidden="true">01 /</span><div><h3>从一个想看懂的视频开始</h3><p>粘贴上方链接，保存你的第一条学习素材。</p></div></div>}
        {videos.data && videos.data.items.length > 0 && <ul className="video-grid">{videos.data.items.map(video => <VideoCard key={video.id} video={video} />)}</ul>}
      </section>}
    </>
  );
}
