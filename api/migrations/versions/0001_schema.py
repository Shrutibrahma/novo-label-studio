"""0001: apply schema.sql verbatim (spec section 5).

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def schema_path() -> Path:
    env = os.environ.get("SCHEMA_SQL")
    if env:
        return Path(env)
    # api/migrations/versions/0001_schema.py -> repository root
    return Path(__file__).resolve().parents[3] / "schema.sql"


def upgrade() -> None:
    sql = schema_path().read_text(encoding="utf-8")
    # schema.sql carries its own BEGIN/COMMIT; executed as one parameterless script it runs exactly as
    # written (the driver connection is used so '%' in the SQL is never treated as a placeholder).
    driver_conn = op.get_bind().connection.driver_connection
    driver_conn.execute(sql)  # type: ignore[union-attr]


TABLES = [
    "audit_log", "printed_label", "print_job", "print_request", "issued_serial", "label_group", "printer",
    "print_agent", "label_config", "serial_sequence", "label_size", "part_alias", "import_row", "part",
    "import_batch", "import_mapping", "custom_field_def", "asset", "app_setting", "user_session", "app_user",
]
FUNCTIONS = [
    "search_parts(text, integer)", "like_prefix(text)", "allocate_serials(uuid, uuid, integer, uuid)",
    "printed_label_guard()", "label_config_immutable()", "part_number_alias_guard()", "part_alias_guard()",
    "normalize_alias(text)", "set_updated_at()",
]


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP VIEW IF EXISTS part_label_freshness")
    for t in TABLES:
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS {t} CASCADE")
    for f in FUNCTIONS:
        bind.exec_driver_sql(f"DROP FUNCTION IF EXISTS {f} CASCADE")
