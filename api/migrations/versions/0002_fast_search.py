"""0002: faster search_parts() (section 15: p95 < 150 ms at 50,000 parts) and one-word name search.

Approved change to schema.sql's search_parts(); 0001 still applies schema.sql verbatim. Same signature, same
columns, same ranking (exact 1.0 > prefix 0.9 > trigram similarity), with three differences:
  * the query text is inlined as literals (EXECUTE format), so the planner sees constants and uses indexes;
  * each branch is capped with an index-ordered top-k (btree text_pattern_ops for prefixes, GiST <-> / <<->
    nearest-neighbour for similarity) instead of scoring every row that passes the trigram filter;
  * part name + description use word similarity (a whole word inside a long name matches), capped at 0.85 so
    name matches never outrank exact / prefix matches on part numbers or label names.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NAME_EXPR = "lower(part_name || ' ' || coalesce(description, ''))"

UPGRADE = f"""
CREATE INDEX IF NOT EXISTS part_number_norm_pattern_idx ON part (part_number_norm text_pattern_ops);
CREATE INDEX IF NOT EXISTS part_alias_norm_pattern_idx ON part_alias (alias_norm text_pattern_ops);
CREATE INDEX IF NOT EXISTS part_number_trgm_gist ON part USING gist (part_number_norm gist_trgm_ops);
CREATE INDEX IF NOT EXISTS part_alias_trgm_gist ON part_alias USING gist (alias_norm gist_trgm_ops);
CREATE INDEX IF NOT EXISTS part_text_trgm_gist ON part USING gist (({NAME_EXPR}) gist_trgm_ops);

CREATE OR REPLACE FUNCTION search_parts(p_query text, p_limit integer DEFAULT 25)
RETURNS TABLE (part_id uuid, part_number text, label_name text, part_name text,
               matched_on text, score real)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
  pn  text    := upper(btrim(coalesce(p_query, '')));
  n   text    := normalize_alias(coalesce(p_query, ''));
  lim integer := greatest(1, least(coalesce(p_limit, 25), 200));
BEGIN
  IF pn = '' THEN
    RETURN;
  END IF;
  RETURN QUERY EXECUTE format($q$
    WITH hits AS (
      (SELECT p.id, 'part_number'::text AS m, 1.0::real AS s
         FROM part p WHERE p.part_number_norm = %1$L AND p.status = 'active')
      UNION ALL
      (SELECT p.id, 'part_number', 0.9::real
         FROM part p WHERE p.part_number_norm LIKE %2$L AND p.part_number_norm <> %1$L AND p.status = 'active'
        ORDER BY p.part_number_norm LIMIT %5$s)
      UNION ALL
      (SELECT p.id, 'part_number', similarity(p.part_number_norm, %1$L)::real
         FROM part p WHERE p.part_number_norm %% %1$L AND p.status = 'active'
        ORDER BY p.part_number_norm <-> %1$L LIMIT %5$s)
      UNION ALL
      (SELECT a.part_id, 'label_name', 1.0::real
         FROM part_alias a JOIN part p ON p.id = a.part_id AND p.status = 'active'
        WHERE %3$L <> '' AND a.alias_norm = %3$L)
      UNION ALL
      (SELECT a.part_id, 'label_name', 0.9::real
         FROM part_alias a JOIN part p ON p.id = a.part_id AND p.status = 'active'
        WHERE %3$L <> '' AND a.alias_norm LIKE %4$L AND a.alias_norm <> %3$L
        ORDER BY a.alias_norm LIMIT %5$s)
      UNION ALL
      (SELECT a.part_id, 'label_name', similarity(a.alias_norm, %3$L)::real
         FROM part_alias a JOIN part p ON p.id = a.part_id AND p.status = 'active'
        WHERE %3$L <> '' AND a.alias_norm %% %3$L
        ORDER BY a.alias_norm <-> %3$L LIMIT %5$s)
      UNION ALL
      (SELECT p.id, 'name', least(word_similarity(%3$L, {NAME_EXPR}), 0.85)::real
         FROM part p WHERE %3$L <> '' AND %3$L <%% {NAME_EXPR} AND p.status = 'active'
        ORDER BY %3$L <<-> {NAME_EXPR} LIMIT %5$s)
    ),
    best AS (
      SELECT DISTINCT ON (h.id) h.id, h.m, h.s FROM hits h ORDER BY h.id, h.s DESC
    )
    SELECT p.id, p.part_number, ln.alias, p.part_name, b.m, b.s
      FROM best b
      JOIN part p ON p.id = b.id
      LEFT JOIN part_alias ln ON ln.part_id = p.id AND ln.is_label_name
     WHERE p.status = 'active'
     ORDER BY b.s DESC, p.part_number
     LIMIT %6$s
  $q$, pn, like_prefix(pn), n, like_prefix(n), lim * 4, lim);
END $fn$;
"""

# The 0001 version, restored on downgrade (copied from schema.sql).
DOWNGRADE = """
DROP INDEX IF EXISTS part_text_trgm_gist;
DROP INDEX IF EXISTS part_alias_trgm_gist;
DROP INDEX IF EXISTS part_number_trgm_gist;
DROP INDEX IF EXISTS part_alias_norm_pattern_idx;
DROP INDEX IF EXISTS part_number_norm_pattern_idx;
DROP FUNCTION IF EXISTS search_parts(text, integer);
CREATE FUNCTION search_parts(p_query text, p_limit integer DEFAULT 25)
RETURNS TABLE (part_id uuid, part_number text, label_name text, part_name text,
               matched_on text, score real)
LANGUAGE sql STABLE AS $$
  WITH q AS (
    SELECT normalize_alias(p_query) AS n, upper(btrim(p_query)) AS pn,
           like_prefix(normalize_alias(p_query)) AS n_like,
           like_prefix(upper(btrim(p_query))) AS pn_like
  ),
  hits AS (
    SELECT p.id, 'part_number'::text AS m,
           CASE WHEN p.part_number_norm = q.pn THEN 1.0
                WHEN p.part_number_norm LIKE q.pn_like THEN 0.9
                ELSE similarity(p.part_number_norm, q.pn) END::real AS s
      FROM part p, q
     WHERE p.part_number_norm % q.pn OR p.part_number_norm LIKE q.pn_like
    UNION ALL
    SELECT a.part_id, 'label_name',
           CASE WHEN a.alias_norm = q.n THEN 1.0
                WHEN a.alias_norm LIKE q.n_like THEN 0.9
                ELSE similarity(a.alias_norm, q.n) END::real
      FROM part_alias a, q
     WHERE a.alias_norm % q.n OR a.alias_norm LIKE q.n_like
    UNION ALL
    SELECT p.id, 'name',
           similarity(lower(p.part_name || ' ' || coalesce(p.description, '')), q.n)::real
      FROM part p, q
     WHERE lower(p.part_name || ' ' || coalesce(p.description, '')) % q.n
  ),
  best AS (
    SELECT DISTINCT ON (h.id) h.id, h.m, h.s
      FROM hits h
     ORDER BY h.id, h.s DESC
  )
  SELECT p.id, p.part_number, ln.alias, p.part_name, b.m, b.s
    FROM best b
    JOIN part p ON p.id = b.id
    LEFT JOIN part_alias ln ON ln.part_id = p.id AND ln.is_label_name
   WHERE p.status = 'active'
     AND btrim(p_query) <> ''
   ORDER BY b.s DESC, p.part_number
   LIMIT greatest(1, least(p_limit, 200));
$$;
"""


def _run(sql: str) -> None:
    # Parameterless script on the driver connection, so '%' is never treated as a placeholder.
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    _run(UPGRADE)


def downgrade() -> None:
    _run(DOWNGRADE)
