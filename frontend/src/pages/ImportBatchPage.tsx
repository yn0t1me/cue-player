import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { getBatch, retryBatch } from '../api/collections';
import type { BatchItem, BatchRetryRequest } from '../types/collections';
import { batchItemLabel, IntentKey, refreshLibrary } from '../features/collections/shared';
export default function ImportBatchPage() {
  const { batchId = '' } = useParams(), client = useQueryClient();
  const keys = useRef(new IntentKey());
  const batch = useQuery({ queryKey: ['import-batch', batchId], queryFn: ({ signal }) => getBatch(batchId, signal),
    refetchInterval: current => current.state.data && (current.state.data.counts.waiting + current.state.data.counts.running > 0) ? 2000 : false });
  const data = batch.data;
  useEffect(() => { if (data) void refreshLibrary(client); }, [data, client]);
  const retry = useMutation({ mutationFn: (payload: BatchRetryRequest) => retryBatch(batchId, payload),
    onSuccess: () => { void batch.refetch(); void refreshLibrary(client); },
    onError: () => { void batch.refetch(); } });
  const failed = data?.items.filter(item => item.job?.status === 'failed') ?? [];
  const retryItems = (items: BatchItem[]) => {
    const intent = { item_ids: items.map(item => item.id), expected_job_ids: Object.fromEntries(items.map(item => [item.id, item.job?.id ?? null])) };
    retry.mutate({ ...intent, idempotency_key: keys.current.for(intent) });
  };
  return <div><Link className="back-link" to="/">← 返回视频库</Link><p className="eyebrow">本次导入记录</p><h1 className="detail-title">导入进度</h1>
    {batch.isPending && <p role="status">正在读取进度…</p>}
    {batch.isError && <p role="alert">{batch.error.message}<button onClick={() => void batch.refetch()}>重新加载</button></p>}
    {data && <>
      {data.collection_id ? <Link className="text-link" to={`/collections/${data.collection_id}`}>打开合集：{data.collection_name_snapshot} →</Link>
        : <p className="muted">{data.collection_name_snapshot ? `原合集“${data.collection_name_snapshot}”已删除，视频仍保留。` : '视频已加入全部视频库。'}</p>}
      <p className="form-hint">关闭页面后仍继续处理。可收藏当前地址，稍后回来查看。</p>
      <dl className="batch-counts">{([['total', '总数'], ['ready', '已就绪'], ['running', '处理中'], ['waiting', '等待中'], ['failed', '失败'], ['unavailable', '不可导入']] as const).map(([key, label]) =>
        <div key={key}><dt>{label}</dt><dd>{data.counts[key]}</dd></div>)}</dl>
      <div className="collection-actions"><button disabled={retry.isPending || !failed.length} onClick={() => retryItems(failed)}>重试全部失败项（{failed.length}）</button>
        <button disabled={batch.isFetching} onClick={() => void batch.refetch()}>刷新进度</button></div>
      {retry.isError && <p role="alert" className="error-message">{retry.error.message}</p>}
      {retry.data && <div role="status" className="notice"><p>重试已接受 {retry.data.items.filter(item => item.status === 'accepted').length} 项；以下结果是请求接受记录，实际进度以目录为准。</p>
        {retry.data.items.filter(item => item.status !== 'accepted').map(item => <p key={item.item_id}>
          {data.items.find(value => value.id === item.item_id)?.video?.title ?? item.video_id ?? '不可导入项'}：{item.error?.message ?? '当前任务不需要重试，已跳过。'}</p>)}</div>}
      <ol className="episode-list">{data.items.map((item, index) => <li key={item.id}>
        <span className="episode-number">{String(index + 1).padStart(2, '0')}</span><div className="episode-content">
          {item.video ? <Link to={`/videos/${item.video.id}${data.collection_id ? `?collection=${encodeURIComponent(data.collection_id)}` : ''}`}><strong>{item.video.title ?? item.youtube_video_id}</strong></Link> : <strong>{item.youtube_video_id ?? '不可导入条目'}</strong>}
          <small>{batchItemLabel(item)} · {{ created: '本次新建', reused: '复用已有视频 · 沿用来源', already_member: '已有合集成员 · 保持原位置', unavailable: '未创建视频' }[item.disposition]}</small>
          {(item.error?.message || item.job?.error_message) && <p className="error-message">{item.error?.message ?? item.job?.error_message}</p>}
          {item.job?.status === 'failed' && item.video?.processing?.id !== item.job.id && <p className="muted">这是本批绑定的旧失败任务；视频当前{item.video?.status === 'ready' ? '已就绪' : '已有更新任务'}，重试会重新核对。</p>}
        </div>{item.job?.status === 'failed' && <button disabled={retry.isPending} onClick={() => retryItems([item])}>重试此项</button>}
      </li>)}</ol>
    </>}
  </div>;
}
