import axios from 'axios';

export class ApiError extends Error {
  constructor(message: string, public status?: number, public code?: string) {
    super(message);
    this.name = 'ApiError';
  }
}

export const api = axios.create({ baseURL: 'http://localhost:8000/api', timeout: 10000 });
api.interceptors.response.use(response => response, (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.error;
    const message = typeof detail?.message === 'string' ? detail.message
      : error.response ? '服务暂时不可用，请稍后重试。' : '无法连接服务，请确认后端已启动。';
    return Promise.reject(new ApiError(message, error.response?.status,
      typeof detail?.code === 'string' ? detail.code : undefined));
  }
  return Promise.reject(new ApiError('请求失败，请稍后重试。'));
});
