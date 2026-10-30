"""0006: each part remembers its label type (v1.1 U2, D11 amended).

`part.preferred_label_type_id` is the type a part always prints as, when set. Archiving a type doesn't clear it;
type resolution skips archived types.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE part ADD COLUMN preferred_label_type_id uuid REFERENCES label_type(id);
"""

DOWNGRADE = """
ALTER TABLE part DROP COLUMN preferred_label_type_id;
"""


def _run(sql: str) -> None:
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
