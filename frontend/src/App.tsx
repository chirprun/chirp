import { useCallback, useEffect, useState } from "react";
import {
  fetchCostTrend,
  fetchHealth,
  fetchQualityTrend,
  fetchRuns,
  fetchScenarios,
  toggleScenario,
  triggerScenario,
  type CostPoint,
  type QualityPoint,
  type Run,
  type Scenario,
} from "./api";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function statusChip(status: string | null) {
  if (!status) return <span className="chip none">—</span>;
  const s = status.toUpperCase();
  if (s === "PASS") return <span className="chip pass">PASS</span>;
  if (s === "RUNNING") return <span className="chip run">RUNNING</span>;
  if (s === "ERROR") return <span className="chip err">ERROR</span>;
  return <span className="chip fail">{s}</span>;
}

function ScenarioDetail({ scenarioId, onClose }: { scenarioId: string; onClose: () => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [quality, setQuality] = useState<QualityPoint[]>([]);
  const [cost, setCost] = useState<CostPoint[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [r, q, c] = await Promise.all([
          fetchRuns(scenarioId),
          fetchQualityTrend(scenarioId),
          fetchCostTrend(scenarioId),
        ]);
        if (!cancelled) {
          setRuns(r);
          setQuality(q);
          setCost(c);
        }
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Load failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  const costChartData = cost.map((row) => ({
    id: row.run_id.slice(0, 8),
    prompt: row.prompt_cost,
    tool: row.tool_cost,
    response: row.response_cost,
  }));

  const qualityChartData = quality.map((p, i) => ({
    label: String(i + 1),
    score: Math.round(p.quality_score * 10) / 10,
    hour: p.hour,
  }));

  return (
    <div className="expand">
      <button type="button" className="btn-ghost" onClick={onClose} style={{ marginBottom: "0.75rem" }}>
        Close details
      </button>
      {err && <p className="error-banner" style={{ marginTop: 0 }}>{err}</p>}
      <div className="chart-row">
        <div className="chart-box">
          <p className="chart-title">Quality trend (last runs)</p>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={qualityChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3544" />
              <XAxis dataKey="label" tick={{ fill: "#8b98a8", fontSize: 11 }} stroke="#2a3544" />
              <YAxis domain={[0, 100]} tick={{ fill: "#8b98a8", fontSize: 11 }} stroke="#2a3544" />
              <Tooltip
                contentStyle={{ background: "#1c2430", border: "1px solid #2a3544", borderRadius: 8 }}
                labelFormatter={(_, payload) =>
                  payload?.[0]?.payload?.hour ? String(payload[0].payload.hour) : ""
                }
              />
              <Line type="monotone" dataKey="score" stroke="#3ecf8e" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-box">
          <p className="chart-title">Cost split (USD)</p>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={costChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3544" />
              <XAxis dataKey="id" tick={{ fill: "#8b98a8", fontSize: 10 }} stroke="#2a3544" />
              <YAxis tick={{ fill: "#8b98a8", fontSize: 11 }} stroke="#2a3544" />
              <Tooltip contentStyle={{ background: "#1c2430", border: "1px solid #2a3544", borderRadius: 8 }} />
              <Legend />
              <Bar dataKey="prompt" stackId="a" fill="#6cb3ff" name="Prompt" />
              <Bar dataKey="tool" stackId="a" fill="#f0b429" name="Tool" />
              <Bar dataKey="response" stackId="a" fill="#3ecf8e" name="Response" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <p className="chart-title" style={{ marginTop: "1rem" }}>
        Recent runs
      </p>
      {!runs ? (
        <p className="loading" style={{ padding: "1rem" }}>
          Loading runs…
        </p>
      ) : (
        <table className="runs">
          <thead>
            <tr>
              <th>Started</th>
              <th>Status</th>
              <th>Code</th>
              <th>Latency</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {runs.slice(0, 8).map((run) => (
              <tr key={run.id}>
                <td style={{ fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
                  {new Date(run.started_at).toLocaleString()}
                </td>
                <td>{statusChip(run.status)}</td>
                <td style={{ fontFamily: "var(--mono)", fontSize: "0.72rem", color: "var(--muted)" }}>
                  {run.error_code ?? "—"}
                </td>
                <td>{run.latency_ms != null ? `${run.latency_ms} ms` : "—"}</td>
                <td>{run.total_cost_usd != null ? `$${run.total_cost_usd.toFixed(4)}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {runs && runs[0] && runs[0].assertion_results.length > 0 && (
        <>
          <p className="chart-title" style={{ marginTop: "1rem" }}>
            Latest run assertions
          </p>
          <ul className="assertion-list">
            {runs[0].assertion_results.map((a) => (
              <li key={a.id} className={a.passed ? "pass" : "fail"}>
                {a.assertion_type}: {a.passed ? "pass" : "fail"} — {a.detail.slice(0, 120)}
                {a.detail.length > 120 ? "…" : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailRefresh, setDetailRefresh] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [list, h] = await Promise.all([
        fetchScenarios(),
        fetchHealth()
          .then(() => true as const)
          .catch(() => false as const),
      ]);
      setScenarios(list);
      setHealthOk(h);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load");
      setHealthOk(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, [refresh]);

  async function handleTrigger(id: string) {
    setBusy(id);
    try {
      await triggerScenario(id);
      await refresh();
      if (expandedId === id) setDetailRefresh((n) => n + 1);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Trigger failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleToggle(s: Scenario) {
    setBusy(s.id);
    try {
      await toggleScenario(s.id);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Toggle failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="layout">
      <header className="header">
        <div>
          <h1 className="title">Chirp</h1>
          <p className="subtitle">
            Synthetic monitoring for AI agents — quality, latency, and cost in one place.
          </p>
        </div>
        <div className={healthOk === false ? "status-pill error" : "status-pill"}>
          <span className="dot" />
          API {healthOk === null ? "…" : healthOk ? "connected" : "offline"}
        </div>
      </header>

      {loadError && (
        <div className="error-banner">
          {loadError}. Start the backend:{" "}
          <code style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>
            uv run uvicorn backend.main:app --reload
          </code>
        </div>
      )}

      {!loadError && scenarios.length === 0 && (
        <p className="loading">No scenarios yet. Seed runs on API startup — check your database.</p>
      )}

      <div className="grid">
        {scenarios.map((s) => (
          <article key={s.id} className="card">
            <div className="card-header">
              <h2 className="card-title">{s.name}</h2>
              <span className={`badge ${s.scenario_type === "adversarial" ? "adversarial" : ""}`}>
                {s.scenario_type}
              </span>
            </div>
            <div className="metrics">
              <span>
                Last run: {statusChip(s.last_run_status)}
              </span>
              <span>
                Latency: <strong>{s.last_latency_ms != null ? `${s.last_latency_ms} ms` : "—"}</strong>
              </span>
              <span>
                Cost:{" "}
                <strong>
                  {s.last_cost_usd != null ? `$${s.last_cost_usd.toFixed(4)}` : "—"}
                </strong>
              </span>
              <span>
                Schedule: <strong>{s.schedule_minutes} min</strong>
              </span>
              <span>
                Monitoring: <strong>{s.is_active ? "on" : "off"}</strong>
              </span>
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn-primary"
                disabled={busy === s.id}
                onClick={() => handleTrigger(s.id)}
              >
                {busy === s.id ? "Running…" : "Trigger run"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={busy === s.id}
                onClick={() => handleToggle(s)}
              >
                {s.is_active ? "Pause" : "Resume"}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}>
                {expandedId === s.id ? "Hide details" : "Details"}
              </button>
            </div>

            {expandedId === s.id && (
              <ScenarioDetail key={detailRefresh} scenarioId={s.id} onClose={() => setExpandedId(null)} />
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
