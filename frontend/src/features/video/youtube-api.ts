export interface YouTubeInstance {
  cueVideoById(options: { videoId: string; startSeconds: number }): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  pauseVideo(): void;
  getCurrentTime(): number;
  destroy(): void;
}

export interface PlayerOptions {
  videoId: string;
  width: string;
  height: string;
  playerVars: { autoplay: number; playsinline: number; origin: string };
  events: {
    onReady(event: { target: YouTubeInstance }): void;
    onError(event: { data: number }): void;
    onStateChange(event: { target: YouTubeInstance; data: number }): void;
  };
}

export interface YouTubeApi {
  Player: new (element: HTMLElement, options: PlayerOptions) => YouTubeInstance;
}

declare global {
  interface Window {
    YT?: YouTubeApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let pending: Promise<YouTubeApi> | undefined;

export function loadYouTubeApi(): Promise<YouTubeApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (pending) return pending;
  pending = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    const previous = window.onYouTubeIframeAPIReady;
    const cleanup = () => {
      window.clearTimeout(timeout);
      script.onerror = null;
      if (window.onYouTubeIframeAPIReady === ready) window.onYouTubeIframeAPIReady = previous;
    };
    const fail = (message: string) => {
      cleanup();
      script.remove();
      pending = undefined;
      reject(new Error(message));
    };
    const ready = () => {
      if (!window.YT?.Player) { fail('YouTube 播放器初始化失败。'); return; }
      cleanup();
      resolve(window.YT);
      previous?.();
    };
    const timeout = window.setTimeout(() => fail('加载 YouTube 超时，请检查网络后重试。'), 15000);
    script.onerror = () => fail('无法加载 YouTube，请检查网络后重试。');
    window.onYouTubeIframeAPIReady = ready;
    document.head.append(script);
  });
  return pending;
}
