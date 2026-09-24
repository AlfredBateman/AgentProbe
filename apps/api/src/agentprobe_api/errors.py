"""One error shape for every non-2xx response:

{"error": {"code": "not_found", "message": "...", "request_id": "...", "details": [...]}}
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from agentprobe_api.logs import request_id_var

_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        *,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.code = code or _CODES.get(status, "error")
        self.message = message
        self.headers = headers


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    details: list[Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id_var.get()}
    if details is not None:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status, headers=headers)


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    err = cast(ApiError, exc)
    return error_response(err.status, err.code, err.message, headers=err.headers)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    http = cast(StarletteHTTPException, exc)
    message = http.detail if isinstance(http.detail, str) else HTTPStatus(http.status_code).phrase
    code = _CODES.get(http.status_code, "error")
    return error_response(http.status_code, code, message, headers=http.headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    # Only loc/msg/type: FastAPI's `input` and `ctx` would echo submitted values (passwords).
    details = [
        {"loc": e["loc"], "msg": e["msg"], "type": e["type"]}
        for e in cast(RequestValidationError, exc).errors()
    ]
    return error_response(422, "validation_error", "Request validation failed", details=details)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    # Unhandled exceptions become 500s in RequestContextMiddleware (main.py), inside the
    # request-ID context; Starlette's Exception handler would run outside it.
