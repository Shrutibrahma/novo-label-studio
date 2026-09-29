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
}
