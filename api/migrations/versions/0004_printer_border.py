"""0004: center smaller labels on a bigger roll, with a border (owner's request, 2026-10-27).

When the roll loaded in the printer is bigger than the label being printed, the label is placed in the middle of
the roll instead of its top-left corner. `label_border` says when a border (cut line) is drawn around it:
'smaller' = only when the label is centered on a bigger roll (default), 'always', or 'never'.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE printer ADD COLUMN label_border text NOT NULL DEFAULT 'smaller'
  CHECK (label_border IN ('never', 'smaller', 'always'));
"""

DOWNGRADE = """
ALTER TABLE printer DROP COLUMN label_border;
"""


def _run(sql: str) -> None:
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
