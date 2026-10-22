import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getCollection } from '../../api/collections';
import { ApiError } from '../../api/client';
import VideoStatus from '../../components/VideoStatus';
export default function EpisodeDirectory({ collectionId, videoId, guard, navigate }: {
  collectionId: string; videoId: string; guard: (action: () => void) => boolean; navigate: (url: string) => void;
}) {
  const query = useQuery({ queryKey: ['collection', collectionId], queryFn: ({ signal }) => getCollection(collectionId, signal),
    refetchInterval: 10000 });
  const data = query.data, index = data?.items.findIndex(item => item.video.id === videoId) ?? -1;
  const path = (id: string) => `/videos/${id}?collection=${encodeURIComponent(collectionId)}`;
  if (query.isPending) return <p role="status">正在读取集数目录…</p>;
  if (query.isError) return <p className="notice" role="status">{query.error instanceof ApiError && query.error.code === 'COLLECTION_NOT_FOUND'
    ? '合集已不存在，当前视频仍可独立阅读。' : '暂时无法读取合集，当前视频仍可独立阅读。'}
    <button onClick={() => void query.refetch()}>重新读取目录</button></p>;
  if (!data || index < 0) return <p className="notice">当前视频已不在这个合集中，仍可独立阅读。</p>;
  return <section className="episode-directory" aria-label="合集观看目录"><div className="episode-navigation">
    <Link to={`/collections/${collectionId}`} onClick={event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); guard(() => navigate(`/collections/${collectionId}`)); }}>{data.name}</Link>
    <span>第 {index + 1} / {data.items.length} 集</span><div className="row-actions">
      <button disabled={index === 0} onClick={() => guard(() => navigate(path(data.items[index - 1].video.id)))}>← 上一集</button>
      <button disabled={index === data.items.length - 1} onClick={() => guard(() => navigate(path(data.items[index + 1].video.id)))}>下一集 →</button></div></div>
    <details><summary>展开 / 收起集数目录</summary><ol className="episode-list">{data.items.map((item, position) => <li key={item.id} aria-current={position === index ? 'true' : undefined}>
      <span className="episode-number">{position + 1}</span><Link className="episode-content" to={path(item.video.id)}
        onClick={event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); if (position !== index) guard(() => navigate(path(item.video.id))); }}>
        <strong>{item.video.title ?? item.video.youtube_video_id}{position === index ? ' · 当前集' : ''}</strong><small><VideoStatus video={item.video} /></small></Link>
    </li>)}</ol></details></section>;
}
