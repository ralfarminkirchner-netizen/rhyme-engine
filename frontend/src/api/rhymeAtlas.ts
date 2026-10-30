import type {
  AtlasChain, AtlasChainInputMember, AtlasFilters, AtlasMap, AtlasNeighborhood, AtlasRegion,
  AtlasSearchRequest, AtlasSearchResponse, AtlasStatus,
} from "../types/rhymeAtlas";

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/atlas${path}`, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch { /* The HTTP status remains useful for an unavailable backend. */ }
    throw new Error(`Atlas ${response.status}: ${detail}`);
  }
  return response.json();
}

export const rhymeAtlasApi = {
  status: () => request<AtlasStatus>("/status"),
  map: (filters: AtlasFilters) => {
    const query = new URLSearchParams({
      kind: filters.kind, languages: filters.languages.join(","),
      min_syllables: String(filters.min_syllables), max_syllables: String(filters.max_syllables),
      origin: filters.origin, limit: "300",
    });
    return request<AtlasMap>(`/map?${query}`);
  },
  neighborhood: (region: AtlasRegion, filters: AtlasFilters) => {
    const query = new URLSearchParams({
      syllables: String(region.syllables), first_family: region.first_family,
      last_family: region.last_family, kind: filters.kind,
      languages: filters.languages.join(","), origin: filters.origin, limit: "100",
    });
    return request<AtlasNeighborhood>(`/neighborhood?${query}`);
  },
  search: (body: AtlasSearchRequest) => request<AtlasSearchResponse>("/search", body),
  expand: (entry_id: string | number, filters: AtlasFilters) => request<AtlasSearchResponse>("/expand", { entry_id, ...filters }),
  chains: () => request<{ chains: AtlasChain[] }>("/chains"),
  saveChain: (title: string, members: AtlasChainInputMember[]) => request<AtlasChain>("/chains", { title, members }),
};
