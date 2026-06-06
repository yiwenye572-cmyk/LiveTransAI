const GLOSSARY_STORAGE_KEY = "livetransai_glossary";
const LIVE_SESSION_KEY = "livetransai_live_active";

function loadStoredGlossary() {
  try {
    const raw = sessionStorage.getItem(GLOSSARY_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") {
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

function saveStoredGlossary(data) {
  sessionStorage.setItem(GLOSSARY_STORAGE_KEY, JSON.stringify(data));
}

function markLiveSessionActive() {
  sessionStorage.setItem(LIVE_SESSION_KEY, "1");
}

function clearLiveSessionActive() {
  sessionStorage.removeItem(LIVE_SESSION_KEY);
}

function isLiveSessionActive() {
  return sessionStorage.getItem(LIVE_SESSION_KEY) === "1";
}

function renderTermMap(container, termMap) {
  if (!container) {
    return;
  }
  const entries = Object.entries(termMap || {});
  if (entries.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无术语，可在配置页生成</div>';
    return;
  }
  container.innerHTML = entries
    .map(
      ([source, target]) =>
        `<span class="summary-term">${escapeHtml(source)} → ${escapeHtml(target)}</span>`
    )
    .join("");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
