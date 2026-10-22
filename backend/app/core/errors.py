from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError):
        return JSONResponse(status_code=error.status_code,
                            content={'error': {'code': error.code, 'message': error.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError):
        message = ('请检查导入重试请求字段。' if request.url.path.endswith('/retry')
                   else '请检查合集或批量导入请求字段。' if any(
            part in request.url.path for part in ('/collections', '/video-import-'))
                   else '请检查学习字幕请求字段。' if '/source-learning' in request.url.path
                   else '请检查字幕标记字段。' if '/marks' in request.url.path
                   else '请提交有效的 YouTube 链接。')
        return JSONResponse(status_code=422, content={
            'error': {'code': 'VALIDATION_ERROR', 'message': message}})
