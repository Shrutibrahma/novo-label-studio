"""Label snapshots (section 5 invariant 2; section 9) and print-time value rules (7.3)."""

from __future__ import annotations

from typing import Any

from app.configs.spec import CORE_KEYS, LabelSpec, ManualBox, ManualChoice, ManualNumber, ManualText
from app.errors import ApiError
from app.render.engine import display_value
from app.render.fonts import renderer_version

CORE_LABELS = {"part_number": "Part number", "part_name": "Part name", "description": "Description",
               "revision": "Revision", "label_name": "Label name", "serial": "Serial number",
               "print_date": "Print date"}


def field_labels(spec: LabelSpec, custom_labels: dict[str, str]) -> dict[str, str]:
    labels = dict(CORE_LABELS) | custom_labels
    for m in spec.manual_fields:
        labels[f"manual.{m.key}"] = m.label
    return labels


def part_field_values(part_number: str, part_name: str, description: str | None, revision: str | None,
                      custom_data: dict[str, Any], label_name: str | None) -> dict[str, Any]:
    values: dict[str, Any] = dict(custom_data)
    values.update({"part_number": part_number, "part_name": part_name})
    if description is not None:
        values["description"] = description
    if revision is not None:
        values["revision"] = revision
    if label_name is not None:
        values["label_name"] = label_name
    return values


def qr_payload(qr_mode: str, part_number: str, serial: str | None) -> str | None:
    """9.4: plain text; always the part number, never the label name."""
    if qr_mode == "part":
        return f"PN:{part_number}"
    if qr_mode == "serial":
        return f"SN:{serial or ''}|PN:{part_number}"
    return None


def clean_manual(spec: LabelSpec, values: dict[str, Any] | None, labels: dict[str, str]) -> dict[str, Any]:
    """Validates print-time values against their field definitions. Missing required values are not an error
    here: the renderer reports REQUIRED_VALUE_MISSING, and printing refuses labels that don't fit."""
    out: dict[str, Any] = {}
    values = values or {}
    for m in spec.manual_fields:
        raw = values.get(m.key)
        label = labels.get(f"manual.{m.key}", m.label)
        fkey = f"manual_values.{m.key}"
        if isinstance(m, ManualBox):
            if isinstance(raw, dict) and "index" in raw and "total" in raw:
                try:
                    index, total = int(raw["index"]), int(raw["total"])
                except (TypeError, ValueError) as exc:
                    raise ApiError("FIELD_NOT_NUMBER", fields={fkey: f"{label} must be a number."}, Field=label) from exc
                if not (1 <= total <= 999 and 1 <= index <= total):
                    raise ApiError("FIELD_OUT_OF_RANGE", fields={fkey: f"{label} must be between 1 and {total}."},
                                   Field=label, min=1, max=total)
                out[m.key] = {"index": index, "total": total}
            continue
        if raw is None or display_value(raw) == "":
            continue
        if isinstance(m, ManualText):
            text = display_value(raw)
            if len(text) > m.max_length:
                raise ApiError("FIELD_TOO_LONG", fields={fkey: f"{label} is longer than {m.max_length} characters."},
                               Field=label, max=m.max_length)
            out[m.key] = text
        elif isinstance(m, ManualNumber):
            try:
                num = float(str(raw).replace(",", "").strip())
            except ValueError as exc:
                raise ApiError("FIELD_NOT_NUMBER", fields={fkey: f"{label} must be a number."}, Field=label) from exc
            if m.integer and not num.is_integer():
                raise ApiError("FIELD_NOT_NUMBER", fields={fkey: f"{label} must be a number."}, Field=label)
            lo = m.min if m.min is not None else float("-inf")
            hi = m.max if m.max is not None else float("inf")
            if not lo <= num <= hi:
                msg_lo = display_value(m.min) if m.min is not None else "−∞"
                msg_hi = display_value(m.max) if m.max is not None else "∞"
                raise ApiError("FIELD_OUT_OF_RANGE", fields={fkey: f"{label} must be between {msg_lo} and {msg_hi}."},
                               Field=label, min=msg_lo, max=msg_hi)
            out[m.key] = int(num) if num.is_integer() else num
        elif isinstance(m, ManualChoice):
            text = display_value(raw)
            match = next((c for c in m.choices if c.lower() == text.lower()), None)
            if match is None:
                raise ApiError("FIELD_NOT_CHOICE", fields={fkey: f"{label} must be one of: {', '.join(m.choices)}."},
                               Field=label, choices=", ".join(m.choices))
            out[m.key] = match
    return out


def build_snapshot(spec: LabelSpec, qr_mode: str, part_values: dict[str, Any], custom_keys: set[str],
                   manual: dict[str, Any], serial: str | None, print_date: str) -> dict[str, Any]:
    """snapshot.part keys are exactly the part fields printed on the label (core, custom, label_name) with the
    source JSON types; empty fields aren't printed, so they aren't in the snapshot."""
    printed = [f.key for f in spec.fields if f.key in CORE_KEYS or f.key == "label_name" or f.key in custom_keys]
    part = {k: part_values[k] for k in printed if k in part_values and display_value(part_values[k]) != ""}
    generated: dict[str, Any] = {"print_date": print_date, "renderer_version": renderer_version()}
    if serial is not None:
        generated["serial"] = serial
    payload = qr_payload(qr_mode, str(part_values["part_number"]), serial)
    if payload is not None:
        generated["qr_payload"] = payload
    return {"part": part, "manual": manual, "generated": generated}
