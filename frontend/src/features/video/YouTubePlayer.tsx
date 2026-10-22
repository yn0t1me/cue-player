import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { loadYouTubeApi, type YouTubeInstance } from './youtube-api';

export interface PlayerHandle {
  seekTo(seconds: number): boolean;
  play(): boolean;
}

interface Props {
  videoId: string;
  onTimeChange?: (seconds: number) => void;
  initialTime?: number;
  onReadyChange?: (ready: boolean) => void;
}

function errorMessage(code: number): string {
  if (code === 100) return '这个视频不存在、已删除或为私密视频。';
  if (code === 101 || code === 150) return '这个视频不允许嵌入播放，请在 YouTube 打开。';
  if (code === 153) return 'YouTube 无法验证当前页面，请尝试使用普通浏览器打开。';
  if (code === 2) return '视频标识无效，无法播放。';
  return 'YouTube 暂时无法播放这个视频，请重试或打开原视频。';
}

const YouTubePlayer = forwardRef<PlayerHandle, Props>(function YouTubePlayer({ videoId, onTimeChange, initialTime, onReadyChange }, ref) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<YouTubeInstance | null>(null);
  const ready = useRef(false);
  const callback = useRef(onTimeChange);
  const readyCallback = useRef(onReadyChange);
  readyCallback.current = onReadyChange;
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { callback.current = onTimeChange; }, [onTimeChange]);
  useImperativeHandle(ref, () => ({
    seekTo(seconds) {
      if (!ready.current || !instance.current || !Number.isFinite(seconds) || seconds < 0) return false;
      instance.current.seekTo(seconds, true);
      return true;
    },
    play() {
      if (!ready.current || !instance.current) return false;
      instance.current.playVideo();
      return true;
    },
  }), []);

  useEffect(() => {
    const host = container.current!;
    let active = true;
    let failed = false;
    let timer: number | undefined;
    let timeout: number | undefined;
    let player: YouTubeInstance | undefined;
    let awaitingRestoredPlayback = false;
    ready.current = false;
    readyCallback.current?.(false);
    setLoading(true);
    setError(null);
    const fail = (message: string) => {
      if (!active) return;
      failed = true;
      readyCallback.current?.(false);
      ready.current = false;
      window.clearInterval(timer);
      window.clearTimeout(timeout);
      setError(message);
      setLoading(false);
    };
    loadYouTubeApi().then(api => {
      if (!active) return;
      const mount = document.createElement('div');
      host.replaceChildren(mount);
      timeout = window.setTimeout(() => fail('播放器就绪超时，请检查网络后重试。'), 15000);
      player = new api.Player(mount, {
        videoId, width: '100%', height: '100%',
        playerVars: { autoplay: 0, playsinline: 1, origin: window.location.origin },
        events: {
          onReady(event) {
            if (!active || failed) return;
            window.clearTimeout(timeout);
            ready.current = true;
            instance.current = event.target;
            if (initialTime !== undefined && Number.isFinite(initialTime) && initialTime >= 0) {
              // Cue preserves the next playback position without seeking an unstarted
              // player and immediately pausing it before a playable frame is loaded.
              awaitingRestoredPlayback = true;
              event.target.cueVideoById({ videoId, startSeconds: initialTime });
            }
            readyCallback.current?.(true);
            setLoading(false);
            setError(null);
            window.clearInterval(timer);
            timer = window.setInterval(() => {
              if (!active || !ready.current || awaitingRestoredPlayback) return;
              const seconds = event.target.getCurrentTime();
              if (Number.isFinite(seconds) && seconds >= 0) callback.current?.(seconds);
            }, 200);
          },
          onError(event) { fail(errorMessage(event.data)); },
          onStateChange(event) {
            if (!active || !ready.current || failed) return;
            if (awaitingRestoredPlayback) {
              if (event.data !== 1 && event.data !== 2 && event.data !== 0) return;
              awaitingRestoredPlayback = false;
            }
            const seconds = event.target.getCurrentTime();
            if (Number.isFinite(seconds) && seconds >= 0) callback.current?.(seconds);
          },
        },
      });
      instance.current = player;
    }).catch(error => fail(error instanceof Error ? error.message : '播放器加载失败。'));
    return () => {
      active = false;
      ready.current = false;
      instance.current = null;
      window.clearTimeout(timeout);
      window.clearInterval(timer);
      player?.destroy();
      host.replaceChildren();
    };
  }, [videoId, attempt]);

  return (
    <section className="youtube-player" aria-label="YouTube 播放器">
      <div className="player-frame" ref={container} />
      {loading && <p role="status" className="player-message">正在加载 YouTube 播放器…</p>}
      {error && <div className="player-message error-panel" role="alert"><p>{error}</p>
        <button onClick={() => setAttempt(value => value + 1)}>重新加载播放器</button></div>}
    </section>
  );
});

export default YouTubePlayer;
