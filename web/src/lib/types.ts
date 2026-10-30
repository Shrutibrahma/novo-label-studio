/** Shapes returned by the API (api/app/**). */

export type Role = "admin" | "operator";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
}

export interface UserRow extends User {
  active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface LabelSize {
  id: string;
  name: string;
  width_in: number;
  height_in: number;
  active: boolean;
  used_by: number;
}

export type PrinterStatus =
  | "ready"
  | "printing"
  | "offline"
  | "out_of_media"
  | "head_open"
  | "paused"
  | "error"
  | "unknown";

export interface Printer {
  id: string;
  name: string;
  model: string;
  dpi: number;
  print_method: string;
  print_width_in: number;
  status: PrinterStatus;
  reported_status: PrinterStatus;
  last_status_at: string | null;
  agent_last_seen_at: string | null;
  loaded_label_size: LabelSize | null;
  offset_x_dots: number;
  offset_y_dots: number;
  darkness: number | null;
  speed_ips: number | null;
  /** Border around each label: only when it's centered on a bigger roll, always, or never. */
  label_border: "never" | "smaller" | "always";
  is_default: boolean;
  updated_at: string;
}

export interface SerialSettings {
  id: string;
  prefix: string;
  separator: "" | "-" | "_";
  digits: number;
  next_value: number;
  locked: boolean;
  example: string;
}

export interface AppSettings {
  company_name: string;
  serial: SerialSettings;
  fonts_allowed: string[];
  backup: BackupStatus;
  qr: QrSettings;
}

/** QR codes open the part page: on/off, the address phones open, and whether a sign-in is needed. */
export interface QrSettings {
  link: boolean;
  link_base: string;
  scan_public: boolean;
}

/** The last backup and its copy off this machine (v1.1 D25). */
export interface BackupStatus {
  at: string | null;
  copy_enabled: boolean;
  copied: boolean | null;
  copy_error: string | null;
}

/** Settings → Label style (v1.1 D21): one look for every label. */
export interface HouseStyle {
  font: "inter" | "roboto_condensed" | "atkinson";
  frame: boolean;
  title_band: boolean;
  company_in_band: boolean;
  footer: boolean;
  /** The label type's name (LABEL, KANBAN) in the band. Off: only the company name. */
  title_in_band: boolean;
}
