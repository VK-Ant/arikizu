// Tiny API client. Prefers relative URLs so dev proxy and prod serve both work.

export type Status = {
  runtime: string;
  version: string;
  uptime_s: number;
  pipeline: string;
  workers: { name: string; state: string; capabilities: string[] }[];
  device: { platform: string; is_jetson: boolean; cpus: number; gpus: number };
  capability_count: number;
  audit_rows: number;
  pending_approvals: number;
};

export type Capability = {
  name: string;
  worker: string;
  timeout_ms: number;
  priority: number;
};

export type PendingAction = {
  action_id: string;
  pipeline: string;
  stage: string;
  triggered_at: string;
  expires_at: string;
  severity: string;
  approver_role: string;
  proposed_action: unknown;
};

export type AuditRow = {
  id: number;
  ts: string;
  kind: string;
  actor: string | null;
  subject: string | null;
  payload: unknown;
};

export type AppEvent = {
  subject: string;
  timestamp: string;
  source: string;
  payload: unknown;
};

const BASE = '/api/v1';

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json();
}

export const api = {
  status: () => json<Status>('/status'),
  capabilities: () => json<Capability[]>('/capabilities'),
  workers: () =>
    json<{ name: string; state: string; capabilities: string[] }[]>('/workers'),
  pending: () => json<PendingAction[]>('/feedback/pending'),
  audit: (limit = 100, kind?: string) =>
    json<AuditRow[]>(`/audit?limit=${limit}${kind ? `&kind=${encodeURIComponent(kind)}` : ''}`),
  pipelineConfig: () => json<unknown>('/pipeline/config'),
  runPipeline: () =>
    json<unknown>('/pipeline/run', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({}),
    }),
  approve: (action_id: string, approver: string, note?: string) =>
    fetch(`${BASE}/feedback/approve`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action_id, approver, note }),
    }),
  reject: (action_id: string, approver: string, reason: string) =>
    fetch(`${BASE}/feedback/reject`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action_id, approver, reason }),
    }),
  rate: (query_id: string, label: 'good' | 'bad', note?: string) =>
    fetch(`${BASE}/feedback/rate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ query_id, label, note }),
    }),
  call: (domain: string, op: string, payload: unknown) =>
    json<unknown>(`/call/${encodeURIComponent(domain)}/${encodeURIComponent(op)}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ payload }),
    }),
};

/** Open a WebSocket on /api/v1/events. */
export function openEventStream(onEvent: (e: AppEvent) => void): () => void {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}${BASE}/events`);
  ws.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch (e) {
      console.error('event parse', e);
    }
  };
  return () => ws.close();
}
