/** API base: empty in dev (Vite proxies /api); set VITE_API_URL for production builds. */
export function apiPath(path: string): string {
  const base = import.meta.env.VITE_API_URL ?? "";
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export type Scenario = {
  id: string;
  name: string;
  description: string | null;
  agent_endpoint: string;
  schedule_minutes: number;
  scenario_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  assertions: { id: string; assertion_type: string; config: Record<string, unknown> }[];
  last_run_status: string | null;
  last_run_timestamp: string | null;
  last_latency_ms: number | null;
  last_cost_usd: number | null;
};

export type AssertionResult = {
  id: string;
  assertion_type: string;
  passed: boolean;
  expected: string;
  actual: string;
  detail: string;
  confidence: number | null;
};

export type Run = {
  id: string;
  scenario_id: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  latency_ms: number | null;
  prompt_cost_usd: number | null;
  tool_cost_usd: number | null;
  response_cost_usd: number | null;
  total_cost_usd: number | null;
  error_message: string | null;
  error_code: string | null;
  assertion_results: AssertionResult[];
};

export type QualityPoint = { hour: string; quality_score: number };
export type CostPoint = {
  run_id: string;
  prompt_cost: number;
  tool_cost: number;
  response_cost: number;
};

export async function fetchScenarios(): Promise<Scenario[]> {
  const r = await fetch(apiPath("/api/scenarios"));
  if (!r.ok) throw new Error(`Failed to load scenarios: ${r.status}`);
  return r.json();
}

export async function fetchRuns(scenarioId: string): Promise<Run[]> {
  const r = await fetch(apiPath(`/api/scenarios/${scenarioId}/runs`));
  if (!r.ok) throw new Error(`Failed to load runs: ${r.status}`);
  return r.json();
}

export async function fetchQualityTrend(scenarioId: string): Promise<QualityPoint[]> {
  const r = await fetch(apiPath(`/api/scenarios/${scenarioId}/quality-trend`));
  if (!r.ok) throw new Error(`Failed to load quality trend: ${r.status}`);
  return r.json();
}

export async function fetchCostTrend(scenarioId: string): Promise<CostPoint[]> {
  const r = await fetch(apiPath(`/api/scenarios/${scenarioId}/cost-trend`));
  if (!r.ok) throw new Error(`Failed to load cost trend: ${r.status}`);
  return r.json();
}

export async function triggerScenario(scenarioId: string): Promise<{ id: string; status: string }> {
  const r = await fetch(apiPath(`/api/scenarios/${scenarioId}/trigger`), { method: "POST" });
  if (!r.ok) throw new Error(`Trigger failed: ${r.status}`);
  return r.json();
}

export async function toggleScenario(scenarioId: string): Promise<Scenario> {
  const r = await fetch(apiPath(`/api/scenarios/${scenarioId}/toggle`), { method: "PATCH" });
  if (!r.ok) throw new Error(`Toggle failed: ${r.status}`);
  return r.json();
}

export async function fetchHealth(): Promise<{ status: string; scheduler: string }> {
  const r = await fetch(apiPath("/api/health"));
  if (!r.ok) throw new Error("API unreachable");
  return r.json();
}
