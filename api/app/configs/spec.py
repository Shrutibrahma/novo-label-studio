"""label_config.spec (spec 7.3): shape and rules. The database stores it as jsonb; the API validates it."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.errors import ApiError

Role = Literal["primary", "secondary", "detail"]
CORE_KEYS = ("part_number", "part_name", "description", "revision")
GENERATED_KEYS = ("serial", "print_date")
ROLE_LIMITS = {"primary": 1, "secondary": 2, "detail": 6}
MANUAL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
NOUN_RE = re.compile(r"^[A-Z]{1,16}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpecField(_Strict):
    key: str = Field(min_length=1, max_length=80)
    role: Role
    uppercase: bool = False
    caption: str | None = Field(default=None, max_length=8)


class _ManualBase(_Strict):
    key: str = Field(min_length=1, max_length=63)
    label: str = Field(min_length=1, max_length=60)
    required: bool = False


class ManualText(_ManualBase):
    type: Literal["text"]
    max_length: int = Field(ge=1, le=60)


class ManualNumber(_ManualBase):
    type: Literal["number"]
    min: float | None = None
    max: float | None = None
    integer: bool = False


class ManualChoice(_ManualBase):
    type: Literal["choice"]
    choices: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(min_length=1, max_length=20)


class ManualBox(_ManualBase):
    type: Literal["box_sequence"]
    noun: str = "BOX"


ManualField = Annotated[ManualText | ManualNumber | ManualChoice | ManualBox, Field(discriminator="type")]


class Style(_Strict):
    font: Literal["inter", "roboto_condensed", "atkinson"] = "inter"
    primary_weight: Literal["regular", "bold", "extra_bold"] = "bold"
    alignment: Literal["left", "center"] = "left"
    emphasis: Literal["small", "medium", "large"] = "medium"
    spacing: Literal["compact", "standard", "spacious"] = "standard"
    qr_position: Literal["left", "right"] = "right"
    # The part's picture (dithered to 1-bit): beside the text on wide labels, above it on tall ones.
    image_position: Literal["none", "left", "right"] = "none"
    # "lines": automatic layout of spec.fields (section 7.4). "bin": the boxed bin-label grid (spec.bin).
    layout: Literal["lines", "bin"] = "lines"
    # What the QR code holds: the part number (D13: PN:…) or every value printed on the label, one per line.
    qr_content: Literal["part_number", "label_data"] = "part_number"


class BinSlot(_Strict):
    key: str | None = Field(default=None, max_length=80)
    heading: str | None = Field(default=None, max_length=24)


def _slot(key: str | None, heading: str) -> BinSlot:
    return BinSlot(key=key, heading=heading)


class BinLayout(_Strict):
    """The bin-label grid: a title bar; the main value and the name on the left with two boxes beside them;
    below, the QR code, the picture and two more boxes. Each box shows its heading and one field."""

    title: str = Field(default="BIN LABEL", max_length=40)
    main: BinSlot = Field(default_factory=lambda: _slot("part_number", "PART #"))
    name: BinSlot = Field(default_factory=lambda: _slot("part_name", "NAME"))
    info1: BinSlot = Field(default_factory=lambda: _slot(None, "BIN QTY"))
    info2: BinSlot = Field(default_factory=lambda: _slot(None, "BIN TYPE"))
    info3: BinSlot = Field(default_factory=lambda: _slot(None, "STATION #"))
    info4: BinSlot = Field(default_factory=lambda: _slot(None, "SUPERMARKET BIN"))
    qr_heading: str = Field(default="SCAN", max_length=24)
    image_heading: str = Field(default="IMAGE", max_length=24)

    def slots(self) -> list[tuple[str, BinSlot]]:
        return [("main", self.main), ("name", self.name), ("info1", self.info1), ("info2", self.info2),
                ("info3", self.info3), ("info4", self.info4)]


class LabelSpec(_Strict):
    fields: list[SpecField] = Field(default_factory=list, max_length=9)
    manual_fields: list[ManualField] = Field(default_factory=list, max_length=20)
    style: Style = Field(default_factory=Style)
    bin: BinLayout = Field(default_factory=BinLayout)

    def printed_keys(self) -> list[str]:
        """Field keys shown on the label, in order: the fields (lines layout) or the filled boxes (bin)."""
        if self.style.layout == "bin":
            keys = [s.key for _, s in self.bin.slots() if s.key]
            return list(dict.fromkeys(keys))
        return [f.key for f in self.fields]

    def manual(self, key: str) -> ManualText | ManualNumber | ManualChoice | ManualBox | None:
        return next((m for m in self.manual_fields if m.key == key), None)

    def box_field(self) -> ManualBox | None:
        return next((m for m in self.manual_fields if isinstance(m, ManualBox)), None)


def parse_spec(raw: Any) -> LabelSpec:
    try:
        return LabelSpec.model_validate(raw)
    except ValidationError as exc:
        raise ApiError("CONFIG_INVALID") from exc


def validate_spec(spec: LabelSpec, custom_keys: set[str], qr_mode: str, serial_mode: str,
                  allowed_fonts: list[str]) -> None:
    """Semantic rules on top of the shape: role limits, known field keys, manual field rules, QR/serial."""
    counts = {r: 0 for r in ROLE_LIMITS}
    seen: set[str] = set()
    manual_keys = [m.key for m in spec.manual_fields]
    for m in spec.manual_fields:
        if not MANUAL_KEY_RE.match(m.key):
            raise ApiError("CONFIG_INVALID")
        if isinstance(m, ManualBox) and not NOUN_RE.match(m.noun):
            raise ApiError("CONFIG_INVALID")
        if isinstance(m, ManualNumber) and m.min is not None and m.max is not None and m.min > m.max:
            raise ApiError("CONFIG_INVALID")
    if len(set(manual_keys)) != len(manual_keys) or sum(isinstance(m, ManualBox) for m in spec.manual_fields) > 1:
        raise ApiError("CONFIG_INVALID")
    def known(key: str) -> bool:
        return (key in CORE_KEYS or key == "label_name" or key in GENERATED_KEYS or key in custom_keys
                or (key.startswith("manual.") and key[7:] in manual_keys))

    for f in spec.fields:
        counts[f.role] += 1
        if f.key in seen:
            raise ApiError("CONFIG_INVALID")
        seen.add(f.key)
        if not known(f.key):
            raise ApiError("CONFIG_FIELD_UNKNOWN")
    if spec.style.layout == "bin" and any(s.key and not known(s.key) for _, s in spec.bin.slots()):
        raise ApiError("CONFIG_FIELD_UNKNOWN")
    if any(counts[r] > limit for r, limit in ROLE_LIMITS.items()):
        raise ApiError("CONFIG_ROLE_LIMIT")
    if qr_mode == "serial" and serial_mode != "required":
        raise ApiError("CONFIG_QR_NEEDS_SERIAL")
    if spec.style.font not in allowed_fonts:
        raise ApiError("CONFIG_INVALID")
    if (qr_mode != "none" and spec.style.layout == "lines"
            and spec.style.image_position == spec.style.qr_position):
        raise ApiError("CONFIG_IMAGE_QR_SAME_SIDE")
