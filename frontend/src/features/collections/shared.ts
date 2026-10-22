import type { QueryClient } from '@tanstack/react-query';
import type { BatchItem } from '../../types/collections';
export function refreshLibrary(client: QueryClient) {
  return Promise.all(['videos', 'video', 'collections', 'collection'].map(key =>
    client.invalidateQueries({ queryKey: [key] })));
}
export function moveItem<T>(items: T[], index: number, delta: number): T[] {
  const next = [...items], target = index + delta;
  if (index < 0 || target < 0 || target >= items.length) return next;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
export function batchItemLabel(item: BatchItem): string {
  if (item.disposition === 'unavailable') return '不可导入';
  if (item.job?.status === 'failed') return '本次处理失败';
  if (item.job?.status === 'pending') return '等待中';
  if (item.job?.status === 'running') return '处理中';
  if (item.job?.status === 'completed') return '已就绪';
  return item.video?.status === 'ready' ? '已就绪' : item.video?.status === 'failed' ? '处理失败' : '等待中';
}
// Retain a key across a lost response; a changed intent must get a new key.
export class IntentKey {
  private keys = new Map<string, string>();
  for(payload: unknown) {
    const intent = JSON.stringify(payload);
    let key = this.keys.get(intent);
    if (!key) { key = crypto.randomUUID(); this.keys.set(intent, key); }
    return key;
  }
}
export function hasVideoAndPlaylist(value: string) {
  try {
    const url = new URL(value);
    return Boolean(url.searchParams.get('list')) && (Boolean(url.searchParams.get('v'))
      || url.hostname === 'youtu.be' || /^\/(shorts|embed)\//.test(url.pathname));
  } catch { return false; }
}
