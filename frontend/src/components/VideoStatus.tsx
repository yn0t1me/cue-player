import type { Video } from '../types/video';

export default function VideoStatus({ video }: { video: Video }) {
  const label = video.status === 'failed' ? '处理失败' : video.status === 'ready' ? '已就绪'
    : video.processing?.status === 'pending' ? '已保存 · 待处理' : '处理中';
  return <span className={`video-status ${video.status}`}>{label}</span>;
}
