import { useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { retryVideo } from '../../api/collections';
import { IntentKey, refreshLibrary } from './shared';
export default function RetryVideoButton({ videoId, jobId }: { videoId: string; jobId: string }) {
  const client = useQueryClient(), keys = useRef(new IntentKey());
  const mutation = useMutation({ mutationFn: () => retryVideo(videoId, jobId, keys.current.for({ videoId, jobId })),
    onSettled: () => { void refreshLibrary(client); } });
  return <><button disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? '正在请求重试…' : '重试导入'}</button>
    {mutation.isError && <p role="alert" className="error-message">{mutation.error.message}</p>}
    {mutation.isSuccess && <p role="status">重试已接受，正在更新进度。</p>}</>;
}
