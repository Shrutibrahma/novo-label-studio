"""0007: quick labels (v1.1 U4, D24).

A label type of kind `quick` prints without a part ("QC HOLD", workstation signs): its printed labels have no
part_id. Quick labels never allocate serials or box groups, so issued_serial.part_id and label_group.part_id stay
NOT NULL. The reprint guard compares parts with IS DISTINCT FROM (a NULL part equals a NULL part), and the
freshness view ignores quick labels.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

GUARD = """
CREATE OR REPLACE FUNCTION printed_label_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  o       printed_label%ROWTYPE;
  v_total smallint;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'printed_label rows are immutable';
  END IF;

  IF NEW.group_id IS NOT NULL THEN
    SELECT total INTO v_total FROM label_group WHERE id = NEW.group_id;
    IF NEW.group_index > v_total THEN
      RAISE EXCEPTION 'group_index % exceeds group total %', NEW.group_index, v_total;
    END IF;
  END IF;

  -- A reprint must reproduce the original: same part, serial, and printed data.
  IF NEW.reprint_of IS NOT NULL THEN
    SELECT * INTO o FROM printed_label WHERE id = NEW.reprint_of;
    IF NEW.part_id {cmp} o.part_id
       OR NEW.serial_value IS DISTINCT FROM o.serial_value
       OR NEW.snapshot IS DISTINCT FROM o.snapshot THEN
      RAISE EXCEPTION 'reprint must match original label %', o.id;
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""

VIEW = """
CREATE OR REPLACE VIEW part_label_freshness AS
WITH last_print AS (
  SELECT DISTINCT ON (pl.part_id)
         pl.part_id, pl.created_at AS last_printed_at, pl.snapshot -> 'part' AS printed_fields
    FROM printed_label pl
   WHERE pl.reprint_of IS NULL{quick}
   ORDER BY pl.part_id, pl.created_at DESC
)
SELECT p.id AS part_id,
       lp.last_printed_at,
       CASE
         WHEN lp.part_id IS NULL THEN 'never_printed'
         WHEN EXISTS (
           SELECT 1
             FROM jsonb_each(lp.printed_fields) AS f
            WHERE f.value IS DISTINCT FROM
                  ((to_jsonb(p) - 'custom_data') || p.custom_data
                   || jsonb_build_object('label_name', ln.alias)) -> f.key
         ) THEN 'out_of_date'
         ELSE 'current'
       END AS label_state
  FROM part p
  LEFT JOIN part_alias ln ON ln.part_id = p.id AND ln.is_label_name
  LEFT JOIN last_print lp ON lp.part_id = p.id;
"""

UPGRADE = f"""
ALTER TABLE label_type ADD COLUMN kind text NOT NULL DEFAULT 'part' CHECK (kind IN ('part', 'quick'));
ALTER TABLE printed_label ALTER COLUMN part_id DROP NOT NULL;
{GUARD.replace("{cmp}", "IS DISTINCT FROM")}
{VIEW.replace("{quick}", " AND pl.part_id IS NOT NULL")}
"""

# Down: only possible while no quick label has been printed (part_id must be set again).
DOWNGRADE = f"""
{VIEW.replace("{quick}", "")}
{GUARD.replace("{cmp}", "<>")}
ALTER TABLE printed_label ALTER COLUMN part_id SET NOT NULL;
ALTER TABLE label_type DROP COLUMN kind;
"""


def _run(sql: str) -> None:
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
