"""Error codes and literal UI messages (spec section 14.2) and the JSON error envelope (section 6)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")

# code -> (http status, message template). Templates use str.format placeholders from the spec.
ERRORS: dict[str, tuple[int, str]] = {
    "AUTH_INVALID": (401, "Username or password is incorrect."),
    "AUTH_LOCKED": (423, "Too many attempts. Try again in 15 minutes."),
    "SESSION_EXPIRED": (401, "Your session expired. Sign in again."),
    "FORBIDDEN": (403, "You don't have permission to do that."),
    "NOT_FOUND": (404, "We couldn't find that. It may have been archived."),
    "STALE_WRITE": (409, "Someone else changed this. Reload to see the latest version."),
    "PART_NUMBER_TAKEN": (409, "A part with this number already exists."),
    "ALIAS_TAKEN": (409, "This name is already used for part {part_number}."),
    "ALIAS_IS_PART_NUMBER": (409, "This name is another part's part number."),
    "ALIAS_EMPTY": (422, "Enter a name with at least one letter or number."),
    "FIELD_REQUIRED": (422, "{Field} is required."),
    "FIELD_TOO_LONG": (422, "{Field} is longer than {max} characters."),
    "FIELD_NOT_NUMBER": (422, "{Field} must be a number."),
    "FIELD_OUT_OF_RANGE": (422, "{Field} must be between {min} and {max}."),
    "FIELD_NOT_CHOICE": (422, "{Field} must be one of: {choices}."),
    "FILE_TOO_LARGE": (413, "This file is too large. Limit: 20 MB and 50,000 rows."),
    "FILE_UNSUPPORTED": (415, "Upload a CSV, XLSX or XLS file."),
    "FILE_UNREADABLE": (422, "We couldn't read this file. Save it again as CSV or XLSX and retry."),
    "FILE_NO_HEADER": (422, "We couldn't find a header row. The first non-empty row must contain column names."),
    "MAPPING_INCOMPLETE": (422, "Map a column to Part Number and Part Name to continue."),
    "MAPPING_DUPLICATE_TARGET": (422, "Each field can be mapped from one column only."),
    "IMPORT_EXPIRED": (410, "This import expired. Upload the file again."),
    "SIZE_UNSUPPORTED": (422, "This size doesn't fit the ZQ630 Plus (media 2.0–4.4 in wide)."),
    "SIZE_IN_USE": (409, "This size is used by {n} labels, so its dimensions can't change."),
    "CONFIG_ROLE_LIMIT": (422, "A label can have 1 main line, 2 second lines and 6 detail lines."),
    "CONFIG_QR_NEEDS_SERIAL": (422, "Turn on serial numbers to use a serial QR code."),
    "TEXT_TOO_LONG": (422, "\"{Field}\" is too long for this label size. Choose a larger size or a smaller text size."),
    "CONTENT_TOO_TALL": (422, "Too much information for this label size. Remove a field or choose a larger size."),
    "QR_TOO_SMALL": (422, "The QR code would be too small to scan. Choose a larger size or move fields."),
    "QR_PAYLOAD_TOO_LONG": (422, "This part number is too long for the QR code."),
    "REQUIRED_VALUE_MISSING": (422, "Enter {Field} to print."),
    "PRINTER_OFFLINE": (409, "The printer is offline. Check the USB cable and that the printer is on."),
    "PRINTER_OUT_OF_MEDIA": (409, "The printer is out of labels."),
    "PRINTER_HEAD_OPEN": (409, "The printer cover is open."),
    "PRINTER_PAUSED": (409, "The printer is paused. Press the pause button on the printer."),
    "PRINTER_ERROR": (409, "The printer reported an error. Check it and try again."),
    "AGENT_UNREACHABLE": (409, "The print agent on the laptop isn't responding."),
    "SIZE_NOT_LOADED": (409, "Load {size} labels in the printer, then confirm."),
    "SERIAL_VOIDED": (409, "This serial was voided and can't be reprinted."),
    "SERIAL_SETTINGS_LOCKED": (409, "Locked after the first serial is issued."),
    "SERIAL_EXHAUSTED": (409, "The serial sequence is full. Increase the digit count in Settings."),
    "JOB_NOT_CANCELLABLE": (409, "This job has already been sent to the printer."),
    "LAST_ADMIN": (409, "There must be at least one active admin."),
    "INTERNAL": (500, "Something went wrong. Try again; if it keeps happening, contact your admin. (ref {request_id})"),
    # Not in 14.2; see OPEN_QUESTIONS.md for each.
    "FIELD_NOT_DATE": (422, "{Field} must be a date."),
    "FIELD_KEY_TAKEN": (409, "A field with this key already exists."),
    "FIELD_KEY_INVALID": (422, "Key can use lowercase letters, numbers and underscores, starting with a letter."),
    "IMAGE_UNSUPPORTED": (415, "Upload a PNG, JPEG or WebP image."),
    "IMAGE_TOO_LARGE": (413, "This image is too large. Limit: 10 MB."),
    "PART_NUMBER_IS_ALIAS": (409, "This part number is already used as a label name for part {part_number}."),
    "USERNAME_TAKEN": (409, "This username is already taken."),
    "USERNAME_INVALID": (422, "Username can use 3–64 letters, numbers, dots, dashes and underscores."),
    "SERIAL_PREFIX_INVALID": (422, "Serial prefix can use 1–12 capital letters and numbers."),
    "PASSWORD_TOO_SHORT": (422, "Password must be at least 12 characters."),
    "PASSWORDS_DIFFERENT": (422, "The passwords don't match."),
    "SETUP_DONE": (409, "Setup is already complete."),
    "SIZE_NAME_TAKEN": (409, "A size with this name already exists."),
    "CONFIG_INVALID": (422, "This label configuration isn't valid. Reload and try again."),
    "CONFIG_FIELD_UNKNOWN": (422, "A field on this label no longer exists. Remove it and publish again."),
    "IDEMPOTENCY_KEY_REQUIRED": (422, "Idempotency-Key is required."),
    "INVALID_STATE": (409, "Someone else changed this. Reload to see the latest version."),
    "PRINT_TOO_LARGE": (422, "{Field} must be between {min} and {max}."),
}


class _Fmt(dict):
    """Leaves unknown placeholders visible instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def message_for(code: str, **params: Any) -> str:
    return ERRORS[code][1].format_map(_Fmt(params))


class ApiError(Exception):
    def __init__(self, code: str, fields: dict[str, str] | None = None, **params: Any) -> None:
        if code not in ERRORS:
            raise KeyError(code)
        self.code = code
        self.status = ERRORS[code][0]
        self.message = message_for(code, **params)
        self.fields = fields
        self.params = params
        super().__init__(f"{code}: {self.message}")


def field_error(code: str, field_key: str, field_label: str, **params: Any) -> ApiError:
    msg = message_for(code, Field=field_label, **params)
    return ApiError(code, fields={field_key: msg}, Field=field_label, **params)


def _envelope(status: int, code: str, message: str, fields: dict[str, str] | None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return JSONResponse(status_code=status, content=body)


def humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize() or "Value"


def _validation_to_error(exc: RequestValidationError) -> JSONResponse:
    fields: dict[str, str] = {}
    first: tuple[str, str] | None = None
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header")]
        key = ".".join(loc) or "body"
        label = humanize(loc[-1]) if loc else "Value"
        etype = err.get("type", "")
        ctx = err.get("ctx") or {}
        if etype == "missing":
            code, msg = "FIELD_REQUIRED", message_for("FIELD_REQUIRED", Field=label)
        elif etype in ("string_too_long", "too_long"):
            code = "FIELD_TOO_LONG"
            msg = message_for(code, Field=label, max=ctx.get("max_length", ""))
        elif etype in ("string_too_short", "too_short"):
            code, msg = "FIELD_REQUIRED", message_for("FIELD_REQUIRED", Field=label)
        elif etype in ("int_parsing", "float_parsing", "decimal_parsing", "int_type", "float_type",
                       "decimal_type", "int_from_float"):
            code, msg = "FIELD_NOT_NUMBER", message_for("FIELD_NOT_NUMBER", Field=label)
        elif etype in ("greater_than", "greater_than_equal", "less_than", "less_than_equal"):
            lo = ctx.get("ge", ctx.get("gt", ""))
            hi = ctx.get("le", ctx.get("lt", ""))
            code, msg = "FIELD_OUT_OF_RANGE", message_for("FIELD_OUT_OF_RANGE", Field=label, min=lo, max=hi)
        elif etype in ("literal_error", "enum"):
            expected = str(ctx.get("expected", "")).replace("'", "")
            code, msg = "FIELD_NOT_CHOICE", message_for("FIELD_NOT_CHOICE", Field=label, choices=expected)
        else:
            code, msg = "FIELD_REQUIRED", message_for("FIELD_REQUIRED", Field=label)
        fields[key] = msg
        if first is None:
            first = (code, msg)
    code, msg = first or ("FIELD_REQUIRED", message_for("FIELD_REQUIRED", Field="Value"))
    return _envelope(ERRORS[code][0], code, msg, fields)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.status, exc.code, exc.message, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _validation_to_error(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _envelope(404, "NOT_FOUND", message_for("NOT_FOUND"), None)
        if exc.status_code == 405:
            return _envelope(405, "NOT_FOUND", message_for("NOT_FOUND"), None)
        if exc.status_code == 403:
            return _envelope(403, "FORBIDDEN", message_for("FORBIDDEN"), None)
        return _envelope(exc.status_code, "INTERNAL", str(exc.detail), None)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        log.exception("unhandled error", extra={"request_id": rid})
        return _envelope(500, "INTERNAL", message_for("INTERNAL", request_id=rid), None)
