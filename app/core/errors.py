from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """API 명세의 실패 응답 { code, message }.

    예: raise AppError(409, "ID_DUPLICATED", "이미 사용 중인 아이디입니다.")
    """

    def __init__(self, status_code: int, code: str, message: str | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


# FastAPI 기본 HTTP 에러를 명세의 code로 바꾼다
_HTTP_CODES = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "FILE_TOO_LARGE",
    429: "TOO_MANY_REQUESTS",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 요청 형식이 틀리면 공통 400 INVALID_INPUT (명세 기준. FastAPI 기본은 422)
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return _error(400, "INVALID_INPUT", f"{field}: {first.get('msg', '잘못된 입력')}")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "INTERNAL_ERROR")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, __: Exception) -> JSONResponse:
        return _error(500, "INTERNAL_ERROR", "서버 오류가 발생했습니다.")
