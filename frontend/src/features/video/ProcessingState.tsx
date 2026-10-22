import RetryVideoButton from '../collections/RetryVideoButton';
import type { Video } from '../../types/video';

const stageOrder = {
  fetching_metadata: 0,
  fetching_captions: 1,
  downloading_audio: 1,
  transcribing: 2,
  normalizing: 2,
  completed: 3,
  failed: -1,
} as const;

export function videoRefreshInterval(video?: Pick<Video, 'status'>): 2000 | false {
  return video?.status === 'processing' ? 2000 : false;
}

export default function ProcessingState({ video }: { video: Video }) {
  const job = video.processing;
  if (video.status === 'failed') {
    return <section className="processing-state failed" aria-labelledby="preparation-title">
      <h2 id="preparation-title">视频处理失败</h2>
      <p role="alert">{job?.error_message ?? '暂时无法完成处理，原记录已保留。'}</p>
      <p className="muted">保留原来源与失败记录，主动重试会创建新任务。</p>
      {job && <RetryVideoButton videoId={video.id} jobId={job.id} />}
    </section>;
  }

  const currentStep = job?.stage === 'fetching_captions' && job.progress >= 35
    ? 2 : job ? stageOrder[job.stage] : 0;
  const labels = ['视频信息', '获取字幕来源', '处理学习字幕', '可以开始阅读'];
  const acquiredSource = video.subtitle_source === 'youtube_auto'
    ? '自动英文字幕' : video.subtitle_source === 'youtube_manual'
      ? '人工英文字幕' : '英文字幕';
  const title = job?.stage === 'fetching_metadata'
    ? (job.status === 'running' ? '正在获取视频信息' : '等待获取视频信息')
    : job?.stage === 'downloading_audio'
      ? (job.status === 'running' ? '正在获取转写音频' : '等待获取转写音频')
      : job?.stage === 'transcribing'
        ? (job.status === 'running' ? '正在生成英文字幕' : '音频已获取，等待转写')
    : job?.stage === 'normalizing' && job.progress >= 80
      ? '原始字幕已保存'
      : job?.stage === 'fetching_captions' && job.progress >= 35
        ? `${acquiredSource}已获取` : '正在查找英文字幕';

  return <section className="processing-state" aria-labelledby="preparation-title">
    <div className="processing-heading">
      <div><p className="eyebrow">字幕准备进度</p><h2 id="preparation-title">{title}</h2></div>
      <strong>{job?.progress ?? 0}%</strong>
    </div>
    <progress max="100" value={job?.progress ?? 0} aria-label="字幕准备进度" />
    <ol className="processing-steps">
      {labels.map((label, index) => {
        const complete = index < currentStep || video.status === 'ready';
        const active = index === currentStep && video.status === 'processing';
        return <li key={label} className={complete ? 'complete' : active ? 'active' : ''}>
          <span aria-hidden="true">{complete ? '✓' : active ? '●' : '○'}</span>{label}
        </li>;
      })}
    </ol>
    {job?.stage === 'normalizing' && job.progress >= 80
      ? <p className="muted">Raw Transcript 已写入；正在生成可阅读的学习字幕。</p>
      : job?.stage === 'transcribing'
        ? <p className="muted">正在本机使用语音识别生成英文 Raw Transcript，较长视频需要更多时间。</p>
        : job?.stage === 'downloading_audio'
          ? <p className="muted">没有找到可用英文字幕；正在获取仅供本地转写的临时音频。</p>
      : job?.stage === 'fetching_captions' && job.progress >= 35
        ? <p className="muted">原始 VTT 已完整保存；正在转换并保存原始字幕。</p>
        : <p className="muted">页面会自动刷新处理状态，你可以继续使用上方播放器。</p>}
  </section>;
}
