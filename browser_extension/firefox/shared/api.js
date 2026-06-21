const API_BASE = "http://localhost:8000";

const API_TIMEOUT_MS = 60000; // 60s for downloads, 10s for queries

function _timeoutFetch(url, options, ms) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { ...options, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}

async function _json(url, options, ms = 10000) {
  const resp = await _timeoutFetch(url, options, ms);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
  }
  return resp.json();
}

async function checkHealth() {
  const data = await _json(`${API_BASE}/api/health`, { method: "GET" });
  return data;
}

async function downloadToLibrary(youtubeUrl) {
  const data = await _json(
    `${API_BASE}/api/download-library`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: youtubeUrl, source: "firefox_extension" }),
    },
    API_TIMEOUT_MS
  );
  return data;
}

async function listSongs(q, limit = 200) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("limit", String(limit));
  const data = await _json(`${API_BASE}/api/library/songs?${params}`, { method: "GET" });
  return data;
}

async function listLibraryGroups() {
  const data = await _json(`${API_BASE}/api/library/groups`, { method: "GET" });
  return data;
}

function getStreamUrl(song) {
  const filePath = song.path || song.jellyfin_path || "";
  if (!filePath) return null;
  return `${API_BASE}/api/library/stream?path=${encodeURIComponent(filePath)}`;
}
