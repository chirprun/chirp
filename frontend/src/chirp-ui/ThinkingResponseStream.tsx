import { useCallback, useState } from "react";
import { apiPath, type Run } from "../api";

export type CheckStreamPhase = "idle" | "thinking" | "response" | "error";

function parseSseBlocks(buffer: string): { events: string[]; rest: string } {
  const events: string[] = [];
  let rest = buffer;
  let idx: number;
  while ((idx = rest.indexOf("\n\n")) !== -1) {
    const block = rest.slice(0, idx);
    rest = rest.slice(idx + 2);
    const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
    if (dataLine) events.push(dataLine.slice(6).trim());
  }
  return { events, rest };
}

/**
 * Consume ``GET /api/scenarios/:id/check-stream`` (SSE) and return the final run payload.
 */
export async function consumeScenarioCheckStream(
  scenarioId: string,
  onPhase: (phase: "thinking" | "response", payload: Record<string, unknown>) => void,
): Promise<Run> {
  const url = apiPath(`/api/scenarios/${scenarioId}/check-stream`);
  const res = await fetch(url);
  if (!res.ok) {
    const hint =
      res.status === 404
        ? " Set `VITE_API_PROXY_TARGET` in `frontend/.env` (API port), use `npm run dev`/`preview` with proxy, or deploy a backend that exposes `…/check-stream`."
        : "";
    throw new Error(`Stream failed: ${res.status}.${hint}`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");
  const decoder = new TextDecoder();
  let buf = "";
  let lastRun: Run | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const { events, rest } = parseSseBlocks(buf);
    buf = rest;
    for (const raw of events) {
      const data = JSON.parse(raw) as Record<string, unknown>;
      const phase = data.phase as string;
      if (phase === "thinking") onPhase("thinking", data);
      if (phase === "response" && data.run) {
        onPhase("response", data);
        lastRun = data.run as Run;
      }
    }
  }
  if (!lastRun) throw new Error("Stream ended without response phase");
  return lastRun;
}

export function useScenarioCheckStream() {
  const [phase, setPhase] = useState<CheckStreamPhase>("idle");
  const [thinkingMessage, setThinkingMessage] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setPhase("idle");
    setThinkingMessage(null);
    setRun(null);
    setError(null);
  }, []);

  const start = useCallback(async (scenarioId: string) => {
    reset();
    setPhase("thinking");
    try {
      const final = await consumeScenarioCheckStream(scenarioId, (p, payload) => {
        if (p === "thinking") setThinkingMessage(String(payload.message ?? "Working…"));
        if (p === "response") setRun(payload.run as Run);
      });
      setRun(final);
      setPhase("response");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stream error");
      setPhase("error");
    }
  }, [reset]);

  return { phase, thinkingMessage, run, error, start, reset };
}

export type ThinkingResponsePanelProps = {
  phase: CheckStreamPhase;
  thinkingMessage?: string | null;
  run?: Run | null;
  error?: string | null;
};

/**
 * UI block: animated “thinking” state, then run summary when the stream completes.
 */
export function ThinkingResponsePanel({ phase, thinkingMessage, run, error }: ThinkingResponsePanelProps) {
  if (phase === "idle") return null;
  return (
    <div className="chirp-stream-panel" role="status" aria-live="polite">
      {phase === "thinking" && (
        <div className="chirp-stream-thinking">
          <span className="chirp-stream-dots" aria-hidden>
            <span />
            <span />
            <span />
          </span>
          <span className="chirp-stream-thinking-label">{thinkingMessage ?? "Thinking…"}</span>
        </div>
      )}
      {phase === "error" && error && <p className="chirp-stream-error">{error}</p>}
      {(phase === "response" || (phase === "error" && run)) && run && (
        <div className="chirp-stream-response">
          <p className="chirp-stream-response-title">Response</p>
          <p className="chirp-stream-meta">
            <strong>{run.status}</strong>
            {run.error_code ? (
              <>
                {" "}
                · <code>{run.error_code}</code>
              </>
            ) : null}
            {run.latency_ms != null ? (
              <>
                {" "}
                · {run.latency_ms} ms
              </>
            ) : null}
            {run.total_cost_usd != null ? (
              <>
                {" "}
                · ${run.total_cost_usd.toFixed(4)}
              </>
            ) : null}
          </p>
        </div>
      )}
    </div>
  );
}
