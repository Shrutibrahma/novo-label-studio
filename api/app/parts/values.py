"""Part field rules shared by manual entry (12.8/12.9) and imports (10.3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

CORE_FIELDS: dict[str, tuple[str, int]] = {
    # key -> (label, max length)
    "part_number": ("Part number", 64),
    "part_name": ("Part name", 200),
    "description": ("Description", 1000),
    "revision": ("Revision", 16),
}
CUSTOM_TEXT_MAX = 1000
RESERVED_KEYS = frozenset({"part_number", "part_name", "description", "revision", "label_name", "serial",
                           "print_date", "status", "id", "custom_data", "manual"})

_EXCEL_EPOCH = date(1899, 12, 30)
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


class ValueError_(Exception):
    """A field value that breaks a rule. `code` is a 14.2 code; `message` is the literal UI string."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    data_type: str  # text | number | date | choice
    choices: tuple[str, ...] = ()
    required: bool = False


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def clean_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError_("FIELD_NOT_NUMBER", f"{label} must be a number.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    text = str(value).strip().replace(",", "")
    try:
        num = float(text)
    except ValueError as exc:
        raise ValueError_("FIELD_NOT_NUMBER", f"{label} must be a number.") from exc
    if num != num or num in (float("inf"), float("-inf")):
        raise ValueError_("FIELD_NOT_NUMBER", f"{label} must be a number.")
    return int(num) if num.is_integer() else num


def parse_date(value: Any, label: str) -> str:
    """ISO, M/D/YYYY, or an Excel serial -> ISO YYYY-MM-DD (10.3)."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float) and not isinstance(value, bool):
        serial = float(value)
    else:
        text = str(value).strip()
        try:
            if re.match(r"^\d{4}-\d{2}-\d{2}", text):
                return date.fromisoformat(text[:10]).isoformat()
            if _MDY.match(text):
                return _mdy(text)
        except ValueError as exc:
            raise ValueError_("FIELD_NOT_DATE", f"{label} must be a date.") from exc
        try:
            serial = float(text)
        except ValueError as exc:
            raise ValueError_("FIELD_NOT_DATE", f"{label} must be a date.") from exc
    if not 1 <= serial < 2958466:
        raise ValueError_("FIELD_NOT_DATE", f"{label} must be a date.")
    return (_EXCEL_EPOCH + timedelta(days=int(serial))).isoformat()


def _mdy(text: str) -> str:
    m = _MDY.match(text)
    if not m:
        raise ValueError("not M/D/YYYY")
    return date(int(m[3]), int(m[1]), int(m[2])).isoformat()


def parse_choice(value: Any, label: str, choices: tuple[str, ...]) -> str:
    text = clean_text(value)
    for c in choices:
        if c.lower() == text.lower():
            return c
    raise ValueError_("FIELD_NOT_CHOICE", f"{label} must be one of: {', '.join(choices)}.")


def parse_custom(field: FieldDef, value: Any) -> Any:
    """Returns the canonical stored JSON value (number stays a number, date an ISO string)."""
    if field.data_type == "number":
        return parse_number(value, field.label)
    if field.data_type == "date":
        return parse_date(value, field.label)
    if field.data_type == "choice":
        return parse_choice(value, field.label, field.choices)
    text = clean_text(value)
    if len(text) > CUSTOM_TEXT_MAX:
        raise ValueError_("FIELD_TOO_LONG", f"{field.label} is longer than {CUSTOM_TEXT_MAX} characters.")
    return text


def check_core(key: str, value: Any, required: bool) -> str | None:
    """Trims and validates a core text field. Returns None for an empty optional value."""
    label, max_len = CORE_FIELDS[key]
    if is_blank(value):
        if required:
            raise ValueError_("FIELD_REQUIRED", f"{label} is missing." if key in ("part_number", "part_name")
                              else f"{label} is required.")
        return None
    text = clean_text(value)
    if len(text) > max_len:
        raise ValueError_("FIELD_TOO_LONG", f"{label} is longer than {max_len} characters.")
    return text


def normalize_part_number(value: str) -> str:
    """Matches part.part_number_norm = upper(btrim(part_number)) (D8)."""
    return value.strip().upper()


_ALIAS_SEP = re.compile(r"[^a-z0-9/.]+")


def normalize_alias(text: str) -> str:
    """Python twin of the SQL normalize_alias()."""
    return _ALIAS_SEP.sub(" ", text.lower()).strip()


def key_from_label(label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    key = re.sub(r"_+", "_", key)
    if not key or not key[0].isalpha():
        key = f"f_{key}" if key else "field"
    return key[:63]
