"""0003: saved label types (D11 changed at the owner's request, 2026-10-19).

A label type is a named design (Label, Bin, Rack, Workstation, Kanban, ...). Every label config version belongs
to one type: each type has one current default and at most one current per-part override, versioned exactly as
before. Existing configs are moved into a first type named "Label", so nothing an installation already uses
changes. Printing picks a type (the first one when none is given).

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE label_type (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 40),
  sort_order integer NOT NULL DEFAULT 0,
  archived   boolean NOT NULL DEFAULT false,
  created_by uuid NOT NULL REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX label_type_name_uq ON label_type (lower(btrim(name))) WHERE NOT archived;

ALTER TABLE label_config ADD COLUMN label_type_id uuid REFERENCES label_type(id);

-- Existing installations: everything so far is the type "Label".
INSERT INTO label_type (name, sort_order, created_by)
SELECT 'Label', 0, created_by FROM label_config ORDER BY created_at LIMIT 1;
-- Config versions are immutable (trigger label_config_immutable); this one-time backfill is the only exception.
ALTER TABLE label_config DISABLE TRIGGER USER;
UPDATE label_config SET label_type_id = (SELECT id FROM label_type ORDER BY created_at LIMIT 1)
 WHERE label_type_id IS NULL;
ALTER TABLE label_config ENABLE TRIGGER USER;
ALTER TABLE label_config ALTER COLUMN label_type_id SET NOT NULL;

-- One current default per type, one current override per part per type.
DROP INDEX label_config_current_default_uq;
DROP INDEX label_config_current_part_uq;
CREATE UNIQUE INDEX label_config_current_default_uq ON label_config (label_type_id)
  WHERE scope = 'default' AND is_current;
CREATE UNIQUE INDEX label_config_current_part_uq ON label_config (label_type_id, part_id)
  WHERE scope = 'part' AND is_current;
CREATE INDEX label_config_type_idx ON label_config (label_type_id, scope) WHERE is_current;
"""

DOWNGRADE = """
DROP INDEX label_config_type_idx;
DROP INDEX label_config_current_part_uq;
DROP INDEX label_config_current_default_uq;
-- Only the first type survives a downgrade; configs of other types are removed with their types (this fails,
-- keeping everything, if labels were already printed with another type: print history references its config).
DELETE FROM label_config WHERE label_type_id <> (SELECT id FROM label_type ORDER BY sort_order, created_at LIMIT 1);
ALTER TABLE label_config DROP COLUMN label_type_id;
DROP TABLE label_type;
CREATE UNIQUE INDEX label_config_current_default_uq ON label_config ((true)) WHERE scope = 'default' AND is_current;
CREATE UNIQUE INDEX label_config_current_part_uq ON label_config (part_id) WHERE scope = 'part' AND is_current;
"""


def _run(sql: str) -> None:
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
