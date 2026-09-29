"""ORM mapping of schema.sql. The database owns defaults, generated columns and triggers; the
mapping only mirrors it (FetchedValue / Computed), so schema.sql stays the single source of truth."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DB_DEFAULT = FetchedValue()


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=DB_DEFAULT)


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=DB_DEFAULT)


def _ts_updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=DB_DEFAULT, server_onupdate=DB_DEFAULT)


class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = _pk()
    username: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, server_default=DB_DEFAULT)
    first_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()


class UserSession(Base):
    __tablename__ = "user_session"
    token_sha256: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()
    last_seen_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)


class AppSetting(Base):
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id"))
    updated_at: Mapped[datetime] = _ts_updated()


class Asset(Base):
    __tablename__ = "asset"
    id: Mapped[uuid.UUID] = _pk()
    sha256: Mapped[bytes] = mapped_column(LargeBinary)
    mime_type: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()


class CustomFieldDef(Base):
    __tablename__ = "custom_field_def"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    required: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    searchable: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    printable: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    created_at: Mapped[datetime] = _ts()


class ImportMapping(Base):
    __tablename__ = "import_mapping"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    header_signature: Mapped[str] = mapped_column(Text)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()


class ImportBatch(Base):
    __tablename__ = "import_batch"
    id: Mapped[uuid.UUID] = _pk()
    file_name: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary)
    mapping_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("import_mapping.id"))
    sheet_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    progress_done: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    progress_total: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    error: Mapped[str | None] = mapped_column(Text)
    total_rows: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    new_count: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    updated_count: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    unchanged_count: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    invalid_count: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    missing_count: Mapped[int] = mapped_column(Integer, server_default=DB_DEFAULT)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Part(Base):
    __tablename__ = "part"
    id: Mapped[uuid.UUID] = _pk()
    part_number: Mapped[str] = mapped_column(Text)
    part_number_norm: Mapped[str] = mapped_column(Text, Computed("upper(btrim(part_number))", persisted=True))
    part_name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[str | None] = mapped_column(Text)
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("asset.id"))
    custom_data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=DB_DEFAULT)
    status: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    source: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    last_import_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("import_batch.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()


class ImportRow(Base):
    __tablename__ = "import_row"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, server_default=DB_DEFAULT)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("import_batch.id"))
    source_row: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)
    part_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("part.id"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    errors: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB(none_as_null=True))
    accepted: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)


class PartAlias(Base):
    __tablename__ = "part_alias"
    id: Mapped[uuid.UUID] = _pk()
    part_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("part.id"))
    alias: Mapped[str] = mapped_column(Text)
    alias_norm: Mapped[str] = mapped_column(Text, Computed("normalize_alias(alias)", persisted=True))
    is_label_name: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()


class LabelSize(Base):
    __tablename__ = "label_size"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    width_in: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    height_in: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    active: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    created_at: Mapped[datetime] = _ts()


class SerialSequence(Base):
    __tablename__ = "serial_sequence"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    prefix: Mapped[str] = mapped_column(Text)
    separator: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    digits: Mapped[int] = mapped_column(SmallInteger, server_default=DB_DEFAULT)
    next_value: Mapped[int] = mapped_column(BigInteger, server_default=DB_DEFAULT)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()


class LabelConfig(Base):
    __tablename__ = "label_config"
    id: Mapped[uuid.UUID] = _pk()
    config_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(Text)
    part_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("part.id"))
    label_size_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("label_size.id"))
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    qr_mode: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    serial_mode: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    serial_sequence_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("serial_sequence.id"))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()


class PrintAgent(Base):
    __tablename__ = "print_agent"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text)
    host_info: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=DB_DEFAULT)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    created_at: Mapped[datetime] = _ts()


class Printer(Base):
    __tablename__ = "printer"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    command_language: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    print_method: Mapped[str] = mapped_column(Text)
    dpi: Mapped[int] = mapped_column(SmallInteger)
    print_width_in: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    media_min_width_in: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    media_max_width_in: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("print_agent.id"))
    connection: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=DB_DEFAULT)
    loaded_label_size_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("label_size.id"))
    offset_x_dots: Mapped[int] = mapped_column(SmallInteger, server_default=DB_DEFAULT)
    offset_y_dots: Mapped[int] = mapped_column(SmallInteger, server_default=DB_DEFAULT)
    darkness: Mapped[int | None] = mapped_column(SmallInteger)
    speed_ips: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=DB_DEFAULT)
    last_status: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    last_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()


class LabelGroup(Base):
    __tablename__ = "label_group"
    id: Mapped[uuid.UUID] = _pk()
    part_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("part.id"))
    noun: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    total: Mapped[int] = mapped_column(SmallInteger)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()


class IssuedSerial(Base):
    __tablename__ = "issued_serial"
    value: Mapped[str] = mapped_column(Text, primary_key=True)
    sequence_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("serial_sequence.id"))
    seq_value: Mapped[int] = mapped_column(BigInteger)
    part_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("part.id"))
    status: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    void_reason: Mapped[str | None] = mapped_column(Text)
    allocated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    allocated_at: Mapped[datetime] = _ts()
    status_changed_at: Mapped[datetime] = _ts()


class PrintRequest(Base):
    __tablename__ = "print_request"
    id: Mapped[uuid.UUID] = _pk()
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(Text)
    request_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()


class PrintJob(Base):
    __tablename__ = "print_job"
    id: Mapped[uuid.UUID] = _pk()
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("print_request.id"))
    seq_in_request: Mapped[int | None] = mapped_column(SmallInteger)
    printer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("printer.id"))
    kind: Mapped[str] = mapped_column(Text)
    payload_zpl: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(Text, server_default=DB_DEFAULT)
    reprint_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _ts()
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrintedLabel(Base):
    __tablename__ = "printed_label"
    id: Mapped[uuid.UUID] = _pk()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("print_job.id"))
    seq_in_job: Mapped[int] = mapped_column(Integer)
    part_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("part.id"))
    label_config_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("label_config.id"))
    serial_value: Mapped[str | None] = mapped_column(Text, ForeignKey("issued_serial.value"))
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("label_group.id"))
    group_index: Mapped[int | None] = mapped_column(SmallInteger)
    copies: Mapped[int] = mapped_column(SmallInteger, server_default=DB_DEFAULT)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    qr_payload: Mapped[str | None] = mapped_column(Text)
    dpi: Mapped[int] = mapped_column(SmallInteger)
    bitmap_png: Mapped[bytes] = mapped_column(LargeBinary)
    bitmap_sha256: Mapped[bytes] = mapped_column(LargeBinary)
    reprint_of: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("printed_label.id"))
    created_at: Mapped[datetime] = _ts()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, server_default=DB_DEFAULT)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id"))
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    before: Mapped[Any] = mapped_column(JSONB(none_as_null=True))
    after: Mapped[Any] = mapped_column(JSONB(none_as_null=True))
    at: Mapped[datetime] = _ts()
