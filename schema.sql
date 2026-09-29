-- Labeling system — PostgreSQL 16 schema
-- Conventions:
--   * text + CHECK instead of ENUM types (easier to migrate).
--   * Label configs and printed labels are immutable; history never mutates.
--   * Serial allocation is a single locked UPDATE; concurrent prints cannot collide.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------- users
CREATE TABLE app_user (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username      text NOT NULL CHECK (username ~ '^[A-Za-z0-9._-]{3,64}$'),
  display_name  text NOT NULL,
  role          text NOT NULL CHECK (role IN ('admin', 'operator')),
  password_hash text NOT NULL,              -- argon2id, hashed in the API
  active        boolean NOT NULL DEFAULT true,
  failed_login_count smallint NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
  first_failed_at    timestamptz,           -- start of the current 15-minute failure window
  locked_until       timestamptz,
  last_login_at      timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX app_user_username_uq ON app_user (lower(username));
CREATE TRIGGER app_user_updated BEFORE UPDATE ON app_user
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Server-side sessions: cookie holds a random 32-byte token; only its sha256 is stored.
CREATE TABLE user_session (
  token_sha256 bytea PRIMARY KEY CHECK (length(token_sha256) = 32),
  user_id      uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  user_agent   text,
  CHECK (expires_at > created_at)
);
CREATE INDEX user_session_user_idx ON user_session (user_id);
CREATE INDEX user_session_expiry_idx ON user_session (expires_at);

-- Application settings (company name, QR/serial defaults, allowed fonts). Keys are fixed by the API.
CREATE TABLE app_setting (
  key        text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_.]{0,63}$'),
  value      jsonb NOT NULL,
  updated_by uuid REFERENCES app_user(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER app_setting_updated BEFORE UPDATE ON app_setting
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------- assets (part images; bytes live in object storage / disk)
CREATE TABLE asset (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sha256      bytea NOT NULL UNIQUE,
  mime_type   text NOT NULL CHECK (mime_type IN ('image/png', 'image/jpeg', 'image/webp')),
  byte_size   integer NOT NULL CHECK (byte_size BETWEEN 1 AND 10485760),
  storage_key text NOT NULL,
  created_by  uuid NOT NULL REFERENCES app_user(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- custom field definitions
CREATE TABLE custom_field_def (
  key        text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{0,62}$'),
  label      text NOT NULL,
  data_type  text NOT NULL CHECK (data_type IN ('text', 'number', 'date', 'choice')),
  choices    jsonb CHECK (choices IS NULL OR jsonb_typeof(choices) = 'array'),
  required   boolean NOT NULL DEFAULT false,
  searchable boolean NOT NULL DEFAULT false,
  printable  boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((data_type = 'choice') = (choices IS NOT NULL))
);

-- ---------------------------------------------------------------- imports
CREATE TABLE import_mapping (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text NOT NULL,
  header_signature text NOT NULL UNIQUE,   -- sha256 of normalized, sorted headers
  mapping          jsonb NOT NULL CHECK (jsonb_typeof(mapping) = 'object'),  -- {"PART_NO": "part_number", ...}
  created_by       uuid NOT NULL REFERENCES app_user(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER import_mapping_updated BEFORE UPDATE ON import_mapping
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE import_batch (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_name       text NOT NULL,
  file_sha256     bytea NOT NULL,
  mapping_id      uuid REFERENCES import_mapping(id),
  sheet_name      text,                    -- chosen sheet for multi-sheet workbooks; NULL for CSV
  status          text NOT NULL DEFAULT 'parsing'
                  CHECK (status IN ('parsing', 'needs_sheet', 'mapping', 'validating',
                                    'staged', 'committed', 'discarded', 'failed')),
  progress_done   integer NOT NULL DEFAULT 0 CHECK (progress_done >= 0),
  progress_total  integer NOT NULL DEFAULT 0 CHECK (progress_total >= 0),
  error           text,
  total_rows      integer NOT NULL DEFAULT 0,
  new_count       integer NOT NULL DEFAULT 0,
  updated_count   integer NOT NULL DEFAULT 0,
  unchanged_count integer NOT NULL DEFAULT 0,
  invalid_count   integer NOT NULL DEFAULT 0,
  missing_count   integer NOT NULL DEFAULT 0,
  created_by      uuid NOT NULL REFERENCES app_user(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  committed_at    timestamptz,
  CHECK ((status = 'committed') = (committed_at IS NOT NULL)),
  CHECK (progress_done <= progress_total OR progress_total = 0),
  CHECK (status <> 'failed' OR error IS NOT NULL)
);

-- ---------------------------------------------------------------- parts
CREATE TABLE part (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  part_number          text NOT NULL CHECK (btrim(part_number) <> ''),
  -- Leading-zero rules are customer-specific; apply them in the API before insert.
  part_number_norm     text GENERATED ALWAYS AS (upper(btrim(part_number))) STORED,
  part_name            text NOT NULL CHECK (btrim(part_name) <> ''),
  description          text,
  revision             text,
  image_asset_id       uuid REFERENCES asset(id) ON DELETE SET NULL,
  custom_data          jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(custom_data) = 'object'),
  status               text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
  source               text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'import')),
  last_import_batch_id uuid REFERENCES import_batch(id),
  created_by           uuid NOT NULL REFERENCES app_user(id),
  updated_by           uuid NOT NULL REFERENCES app_user(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX part_number_norm_uq ON part (part_number_norm);
CREATE INDEX part_number_trgm ON part USING gin (part_number_norm gin_trgm_ops);
CREATE INDEX part_text_trgm ON part
  USING gin ((lower(part_name || ' ' || coalesce(description, ''))) gin_trgm_ops);
CREATE INDEX part_status_idx ON part (status);
CREATE TRIGGER part_updated BEFORE UPDATE ON part
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE import_row (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  batch_id   uuid NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
  source_row integer,                       -- NULL for 'missing' (part absent from the new file)
  action     text NOT NULL CHECK (action IN ('new', 'update', 'unchanged', 'invalid', 'missing')),
  part_id    uuid REFERENCES part(id),
  data       jsonb NOT NULL,
  diff       jsonb,                         -- {"revision": ["C", "D"], ...}
  errors     jsonb,                         -- [{"field": "max", "msg": "not numeric"}]
  accepted   boolean NOT NULL DEFAULT true,
  CHECK ((action = 'missing') = (source_row IS NULL)),
  CHECK (action <> 'invalid' OR errors IS NOT NULL)
);
CREATE INDEX import_row_batch_idx ON import_row (batch_id, action);

-- ---------------------------------------------------------------- label names & aliases
-- User-defined names (e.g. "10-32 x 1/2 16") that resolve to exactly one part.
-- Owned by users, never touched by imports, so re-importing the parts file can't wipe them.
-- is_label_name marks the one alias printed as the part's label name (field key: 'label_name').
CREATE OR REPLACE FUNCTION normalize_alias(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  -- "10-32 X 1/2  16" and "10 32 x 1/2 16" both -> "10 32 x 1/2 16"
  SELECT btrim(regexp_replace(lower(t), '[^a-z0-9/.]+', ' ', 'g'))
$$;

CREATE TABLE part_alias (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  part_id       uuid NOT NULL REFERENCES part(id) ON DELETE CASCADE,
  alias         text NOT NULL CHECK (btrim(alias) <> '' AND length(alias) <= 120),
  alias_norm    text GENERATED ALWAYS AS (normalize_alias(alias)) STORED,
  is_label_name boolean NOT NULL DEFAULT false,
  created_by    uuid NOT NULL REFERENCES app_user(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (normalize_alias(alias) <> '')
);
CREATE UNIQUE INDEX part_alias_norm_uq       ON part_alias (alias_norm);            -- one alias -> one part
CREATE UNIQUE INDEX part_alias_label_name_uq ON part_alias (part_id) WHERE is_label_name;
CREATE INDEX        part_alias_trgm          ON part_alias USING gin (alias_norm gin_trgm_ops);

-- An alias must not equal another part's part number, or lookups become ambiguous.
CREATE OR REPLACE FUNCTION part_alias_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM part
              WHERE part_number_norm = upper(btrim(NEW.alias))
                AND id <> NEW.part_id) THEN
    RAISE EXCEPTION 'alias "%" is another part''s part number', NEW.alias;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER part_alias_guard_trg BEFORE INSERT OR UPDATE ON part_alias
  FOR EACH ROW EXECUTE FUNCTION part_alias_guard();

-- Reverse direction: a part number must not equal another part's alias.
CREATE OR REPLACE FUNCTION part_number_alias_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM part_alias
              WHERE upper(btrim(alias)) = upper(btrim(NEW.part_number))  -- generated column isn't set yet in BEFORE triggers
                AND part_id <> NEW.id) THEN
    RAISE EXCEPTION 'part number "%" is already a label name of another part', NEW.part_number;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER part_number_alias_guard_trg BEFORE INSERT OR UPDATE OF part_number ON part
  FOR EACH ROW EXECUTE FUNCTION part_number_alias_guard();
CREATE INDEX part_alias_upper_idx ON part_alias (upper(btrim(alias)));

-- One search box: part number, label name/alias, part name, description.
-- Exact matches score 1.0; prefix matches 0.9; otherwise trigram similarity.
CREATE OR REPLACE FUNCTION like_prefix(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT replace(replace(replace(t, '\', '\\'), '%', '\%'), '_', '\_') || '%'
$$;

CREATE OR REPLACE FUNCTION search_parts(p_query text, p_limit integer DEFAULT 25)
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

-- ---------------------------------------------------------------- label sizes
-- width_in = across the media (perpendicular to feed); height_in = along the feed.
CREATE TABLE label_size (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL UNIQUE,
  width_in   numeric(5,3) NOT NULL CHECK (width_in > 0 AND width_in <= 12),
  height_in  numeric(5,3) NOT NULL CHECK (height_in > 0 AND height_in <= 40),
  active     boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- serial sequences
CREATE TABLE serial_sequence (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL UNIQUE,
  prefix     text NOT NULL CHECK (prefix ~ '^[A-Z0-9]{1,12}$'),
  separator  text NOT NULL DEFAULT '-' CHECK (separator IN ('', '-', '_')),
  digits     smallint NOT NULL DEFAULT 8 CHECK (digits BETWEEN 4 AND 12),
  next_value bigint NOT NULL DEFAULT 1 CHECK (next_value >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER serial_sequence_updated BEFORE UPDATE ON serial_sequence
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------- label configurations (immutable versions)
-- One current global default + optional current per-part override.
-- spec: {"fields": [...], "manual_fields": [...], "style": {...}} — validated by the API.
CREATE TABLE label_config (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  config_key         uuid NOT NULL,         -- stable identity across versions
  version            integer NOT NULL CHECK (version >= 1),
  scope              text NOT NULL CHECK (scope IN ('default', 'part')),
  part_id            uuid REFERENCES part(id),
  label_size_id      uuid NOT NULL REFERENCES label_size(id),
  spec               jsonb NOT NULL CHECK (jsonb_typeof(spec) = 'object'),
  qr_mode            text NOT NULL DEFAULT 'none' CHECK (qr_mode IN ('none', 'part', 'serial')),
  serial_mode        text NOT NULL DEFAULT 'none' CHECK (serial_mode IN ('none', 'required')),
  serial_sequence_id uuid REFERENCES serial_sequence(id),
  is_current         boolean NOT NULL DEFAULT true,
  created_by         uuid NOT NULL REFERENCES app_user(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (config_key, version),
  CHECK ((scope = 'part') = (part_id IS NOT NULL)),
  CHECK ((serial_mode = 'required') = (serial_sequence_id IS NOT NULL)),
  CHECK (qr_mode <> 'serial' OR serial_mode = 'required')   -- QR per label needs a serial to encode
);
CREATE UNIQUE INDEX label_config_current_key_uq     ON label_config (config_key) WHERE is_current;
CREATE UNIQUE INDEX label_config_current_default_uq ON label_config ((true))    WHERE scope = 'default' AND is_current;
CREATE UNIQUE INDEX label_config_current_part_uq    ON label_config (part_id)   WHERE scope = 'part' AND is_current;

-- Only allowed mutation: retiring a version (is_current true -> false).
CREATE OR REPLACE FUNCTION label_config_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (to_jsonb(NEW) - 'is_current') IS DISTINCT FROM (to_jsonb(OLD) - 'is_current')
     OR (NOT OLD.is_current AND NEW.is_current) THEN
    RAISE EXCEPTION 'label_config % is immutable; insert a new version', OLD.id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER label_config_immutable_trg BEFORE UPDATE ON label_config
  FOR EACH ROW EXECUTE FUNCTION label_config_immutable();

-- ---------------------------------------------------------------- print agents & printers
-- The agent runs on the laptop, holds the USB connection, and pulls jobs from the API.
CREATE TABLE print_agent (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL UNIQUE,
  token_hash   text NOT NULL,
  host_info    jsonb NOT NULL DEFAULT '{}',
  last_seen_at timestamptz,
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE printer (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                 text NOT NULL UNIQUE,
  model                text NOT NULL,                  -- e.g. 'Zebra ZQ630 Plus'
  command_language     text NOT NULL DEFAULT 'zpl' CHECK (command_language IN ('zpl')),
  print_method         text NOT NULL CHECK (print_method IN ('direct_thermal', 'thermal_transfer')),
  dpi                  smallint NOT NULL CHECK (dpi IN (203, 300, 600)),
  print_width_in       numeric(5,3) NOT NULL CHECK (print_width_in > 0),
  media_min_width_in   numeric(5,3) NOT NULL CHECK (media_min_width_in > 0),
  media_max_width_in   numeric(5,3) NOT NULL,
  agent_id             uuid NOT NULL REFERENCES print_agent(id),
  connection           jsonb NOT NULL DEFAULT '{}',    -- {"type": "usb", "serial": "..."}
  loaded_label_size_id uuid REFERENCES label_size(id),
  offset_x_dots        smallint NOT NULL DEFAULT 0 CHECK (offset_x_dots BETWEEN -200 AND 200),
  offset_y_dots        smallint NOT NULL DEFAULT 0 CHECK (offset_y_dots BETWEEN -200 AND 200),
  darkness             smallint CHECK (darkness BETWEEN 0 AND 30),   -- ZPL ~SD range
  speed_ips            numeric(3,1) CHECK (speed_ips > 0),
  is_default           boolean NOT NULL DEFAULT false,
  last_status          text NOT NULL DEFAULT 'unknown'
                       CHECK (last_status IN ('ready', 'printing', 'offline', 'out_of_media',
                                              'head_open', 'paused', 'error', 'unknown')),
  last_status_at       timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (media_min_width_in <= media_max_width_in),
  CHECK (print_width_in <= media_max_width_in)
);
CREATE UNIQUE INDEX printer_one_default_uq ON printer ((true)) WHERE is_default;
CREATE TRIGGER printer_updated BEFORE UPDATE ON printer
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------- box groups (BOX 1/3 ...)
CREATE TABLE label_group (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  part_id    uuid NOT NULL REFERENCES part(id),
  noun       text NOT NULL DEFAULT 'BOX' CHECK (noun ~ '^[A-Z]{1,16}$'),
  total      smallint NOT NULL CHECK (total BETWEEN 1 AND 999),
  created_by uuid NOT NULL REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- issued serials
-- Never reused. 'unconfirmed' = job sent but printer did not confirm.
CREATE TABLE issued_serial (
  value             text PRIMARY KEY,
  sequence_id       uuid NOT NULL REFERENCES serial_sequence(id),
  seq_value         bigint NOT NULL,
  part_id           uuid NOT NULL REFERENCES part(id),
  status            text NOT NULL DEFAULT 'allocated'
                    CHECK (status IN ('allocated', 'printed', 'unconfirmed', 'voided')),
  void_reason       text,
  allocated_by      uuid NOT NULL REFERENCES app_user(id),
  allocated_at      timestamptz NOT NULL DEFAULT now(),
  status_changed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (sequence_id, seq_value),
  CHECK ((status = 'voided') = (void_reason IS NOT NULL))
);
CREATE INDEX issued_serial_part_idx ON issued_serial (part_id, allocated_at DESC);

-- Atomic allocation: the UPDATE row-locks the sequence, so concurrent callers serialize.
-- Any failure rolls back both the counter and the inserted serials.
CREATE OR REPLACE FUNCTION allocate_serials(
  p_sequence_id uuid, p_part_id uuid, p_count integer, p_user uuid
) RETURNS SETOF text
LANGUAGE plpgsql AS $$
DECLARE
  v_start  bigint;
  v_prefix text;
  v_sep    text;
  v_digits smallint;
BEGIN
  IF p_count IS NULL OR p_count < 1 OR p_count > 1000 THEN
    RAISE EXCEPTION 'serial count out of range: %', p_count;
  END IF;

  UPDATE serial_sequence
     SET next_value = next_value + p_count
   WHERE id = p_sequence_id
  RETURNING next_value - p_count, prefix, separator, digits
       INTO v_start, v_prefix, v_sep, v_digits;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'serial sequence % not found', p_sequence_id;
  END IF;

  IF (v_start + p_count - 1) >= power(10::numeric, v_digits) THEN
    RAISE EXCEPTION 'serial sequence % exhausted at % digits', p_sequence_id, v_digits;
  END IF;

  RETURN QUERY
  INSERT INTO issued_serial (value, sequence_id, seq_value, part_id, allocated_by)
  SELECT v_prefix || v_sep || lpad(g::text, v_digits, '0'), p_sequence_id, g, p_part_id, p_user
    FROM generate_series(v_start, v_start + p_count - 1) AS g
  RETURNING issued_serial.value;
END $$;

-- ---------------------------------------------------------------- print requests & jobs
-- One user action (Print / Reprint). Owns the idempotency key; may fan out into several jobs (<= 200 labels each).
CREATE TABLE print_request (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key uuid NOT NULL UNIQUE,
  kind            text NOT NULL CHECK (kind IN ('print', 'reprint')),
  request_body    jsonb NOT NULL,          -- the validated request, for audit and idempotent replay
  created_by      uuid NOT NULL REFERENCES app_user(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE print_job (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id      uuid REFERENCES print_request(id),   -- NULL only for test labels
  seq_in_request  smallint,
  printer_id      uuid NOT NULL REFERENCES printer(id),
  kind            text NOT NULL CHECK (kind IN ('print', 'reprint', 'test')),
  payload_zpl     bytea NOT NULL CHECK (octet_length(payload_zpl) BETWEEN 1 AND 52428800),
  status          text NOT NULL DEFAULT 'created'
                  CHECK (status IN ('created', 'rendered', 'queued', 'sending', 'sent',
                                    'confirmed', 'failed', 'cancelled')),
  reprint_reason  text CHECK (reprint_reason IN ('damaged', 'missing', 'print_issue', 'other')),
  error           text,
  created_by      uuid NOT NULL REFERENCES app_user(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  claimed_at      timestamptz,             -- set when the agent claims the job (status 'sending')
  sent_at         timestamptz,
  finished_at     timestamptz,
  CHECK (kind = 'reprint' OR reprint_reason IS NULL),
  CHECK ((kind = 'test') = (request_id IS NULL)),
  CHECK ((request_id IS NULL) = (seq_in_request IS NULL)),
  CHECK (status <> 'failed' OR error IS NOT NULL),
  CHECK (status NOT IN ('sending', 'sent', 'confirmed') OR claimed_at IS NOT NULL)
);
-- Lease check: jobs stuck in 'sending' for 60 s are failed by the API's scheduler.
CREATE INDEX print_job_sending_idx ON print_job (claimed_at) WHERE status = 'sending';
-- Agent claims work with: ... WHERE status = 'queued' ORDER BY created_at FOR UPDATE SKIP LOCKED
CREATE UNIQUE INDEX print_job_request_seq_uq ON print_job (request_id, seq_in_request) WHERE request_id IS NOT NULL;
CREATE INDEX print_job_queue_idx ON print_job (printer_id, created_at) WHERE status = 'queued';

-- ---------------------------------------------------------------- printed labels (immutable)
-- snapshot: {"part": {...printed part fields}, "manual": {...}, "generated": {...}}
-- Keys in snapshot.part must match part column names / custom_data keys, with the same JSON types.
CREATE TABLE printed_label (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          uuid NOT NULL REFERENCES print_job(id),
  seq_in_job      integer NOT NULL CHECK (seq_in_job >= 1),
  part_id         uuid NOT NULL REFERENCES part(id),
  label_config_id uuid NOT NULL REFERENCES label_config(id),
  serial_value    text REFERENCES issued_serial(value),
  group_id        uuid REFERENCES label_group(id),
  group_index     smallint,
  copies          smallint NOT NULL DEFAULT 1 CHECK (copies BETWEEN 1 AND 500),
  snapshot        jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
  qr_payload      text,
  dpi             smallint NOT NULL CHECK (dpi IN (203, 300, 600)),
  bitmap_png      bytea NOT NULL,           -- the exact 1-bit raster sent to the printer
  bitmap_sha256   bytea NOT NULL,
  reprint_of      uuid REFERENCES printed_label(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, seq_in_job),
  CHECK ((group_id IS NULL) = (group_index IS NULL)),
  CHECK (group_index IS NULL OR group_index >= 1)
);
CREATE INDEX printed_label_part_idx   ON printed_label (part_id, created_at DESC) WHERE reprint_of IS NULL;
CREATE INDEX printed_label_serial_idx ON printed_label (serial_value);
CREATE INDEX printed_label_job_idx    ON printed_label (job_id);

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
    IF NEW.part_id <> o.part_id
       OR NEW.serial_value IS DISTINCT FROM o.serial_value
       OR NEW.snapshot IS DISTINCT FROM o.snapshot THEN
      RAISE EXCEPTION 'reprint must match original label %', o.id;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER printed_label_guard_trg BEFORE INSERT OR UPDATE OR DELETE ON printed_label
  FOR EACH ROW EXECUTE FUNCTION printed_label_guard();

-- ---------------------------------------------------------------- audit log (meaningful state changes only)
CREATE TABLE audit_log (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id  uuid REFERENCES app_user(id),
  action    text NOT NULL,                  -- 'part.update', 'import.commit', 'config.publish', ...
  entity    text NOT NULL,
  entity_id text NOT NULL,
  before    jsonb,
  after     jsonb,
  at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_entity_idx ON audit_log (entity, entity_id, at DESC);

-- ---------------------------------------------------------------- label freshness ("label out of date")
CREATE VIEW part_label_freshness AS
WITH last_print AS (
  SELECT DISTINCT ON (pl.part_id)
         pl.part_id, pl.created_at AS last_printed_at, pl.snapshot -> 'part' AS printed_fields
    FROM printed_label pl
   WHERE pl.reprint_of IS NULL
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

-- ---------------------------------------------------------------- seed
-- Serial sequence, sizes, printer and default config are created by POST /setup (spec section 5, seed data).

COMMIT;
