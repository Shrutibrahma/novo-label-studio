"""0005: house label style (v1.1 U1, D21).

One company-wide style (font, frame, title band, footer) applied by the renderer to every label type, stored in
app_setting `label.house_style`. Its font starts as the font of the first label type's current default design, so
existing labels keep their font. `label_type.title` is the text printed in the title band (NULL = the type's
name).

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE label_type ADD COLUMN title text
  CHECK (title IS NULL OR (btrim(title) <> '' AND length(title) <= 24));

INSERT INTO app_setting (key, value)
SELECT 'label.house_style',
       jsonb_build_object(
         'font', CASE WHEN c.spec -> 'style' ->> 'font' IN ('inter', 'roboto_condensed', 'atkinson')
                      THEN c.spec -> 'style' ->> 'font' ELSE 'inter' END,
         'frame', true, 'title_band', true, 'company_in_band', true, 'footer', true)
  FROM label_type t
  JOIN label_config c ON c.label_type_id = t.id AND c.scope = 'default' AND c.is_current
 WHERE NOT t.archived
 ORDER BY t.sort_order, t.created_at
 LIMIT 1
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = """
DELETE FROM app_setting WHERE key = 'label.house_style';
ALTER TABLE label_type DROP COLUMN title;
"""


def _run(sql: str) -> None:
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
