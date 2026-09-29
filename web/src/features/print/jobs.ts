import { api } from "../../lib/api";
import type { JobStatus } from "../../lib/status";

export interface JobLabel {
  id: string;
  seq_in_job: number;
  part_id: string;
  serial_value: string | null;
  group_index: number | null;
  copies: number;
}

export interface Job {
  id: string;
  kind: "print" | "reprint" | "test";
  status: JobStatus;
  error: string | null;
  printer_id: string;
  created_at: string;
  claimed_at: string | null;
  sent_at: string | null;
  finished_at: string | null;
  labels: JobLabel[];
}

const TERMINAL: JobStatus[] = ["sent", "confirmed", "failed", "cancelled"];

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL.includes(status);
}

/** Polls jobs until every one reaches a terminal state (sent counts as terminal per 8.3). */
export async function waitForJobs(ids: string[], onUpdate: (jobs: Job[]) => void, signal?: AbortSignal): Promise<Job[]> {
  for (;;) {
    const jobs = await Promise.all(ids.map((id) => api<Job>(`/jobs/${id}`, { signal })));
    onUpdate(jobs);
    if (jobs.every((j) => isTerminal(j.status))) return jobs;
    await new Promise((r) => setTimeout(r, 700));
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
  }
}
