import type {
  GraphBuildRequest, GraphFeedback, GraphSession, GraphSessionSummary, GraphSourceContext, RhymeGraphResponse,
} from "../types/rhymeGraph";

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/rhymes/graph${path}`, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let explanation = response.statusText;
    try {
      const data = await response.json();
      explanation = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch { /* Keep the HTTP status if no structured response is available. */ }
    throw new Error(`Reimgraph: ${response.status} · ${explanation}`);
  }
  return response.json();
}

export const rhymeGraphApi = {
  build: (body: GraphBuildRequest) => request<RhymeGraphResponse>("/build", body),
  sessions: () => request<{ sessions: GraphSessionSummary[] }>("/sessions"),
  saveSession: (title: string, body: GraphBuildRequest, fingerprint?: string) => request<GraphSession>("/sessions", { title, request: body, expected_graph_fingerprint: fingerprint }),
  session: (id: string) => request<GraphSession>(`/sessions/${encodeURIComponent(id)}`),
  feedback: (id: string, body: GraphFeedback) => request<GraphFeedback>(`/sessions/${encodeURIComponent(id)}/feedback`, body),
  source: (id: string, line: number, hash?: string) => request<GraphSourceContext>(`/sources/${encodeURIComponent(id)}?line_no=${line}${hash ? `&expected_line_hash=${encodeURIComponent(hash)}` : ""}`),
};
