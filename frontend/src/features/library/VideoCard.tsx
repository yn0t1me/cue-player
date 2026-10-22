import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Video } from '../../types/video';
import VideoStatus from '../../components/VideoStatus';

export default function VideoCard({ video }: { video: Video }) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <li>
      <Link className="video-card" to={`/videos/${video.id}`}>
        <div className="thumbnail">
          {video.thumbnail_url && !imageFailed
            ? <img src={video.thumbnail_url} alt="" onError={() => setImageFailed(true)} />
            : <span aria-hidden="true">CC<span className="thumbnail-caption">等待视频信息</span></span>}
        </div>
        <div className="card-body">
          <VideoStatus video={video} />
          <h3>{video.title ?? `YouTube · ${video.youtube_video_id}`}</h3>
          <p>{video.channel_title ?? '标题与频道信息尚未获取'}</p>
          <div className="card-foot"><time dateTime={video.created_at}>{new Date(video.created_at).toLocaleDateString('zh-CN')}</time><span>打开记录 ↗</span></div>
        </div>
      </Link>
    </li>
  );
}
