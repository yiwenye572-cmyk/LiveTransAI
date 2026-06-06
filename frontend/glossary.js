const GLOSSARY_STORAGE_KEY = "livetransai_glossary";
const LIVE_SESSION_KEY = "livetransai_live_active";
const DEFAULT_SOURCE_LANGUAGE = "en";

function loadStoredGlossary() {
  return loadSessionConfig();
}

function loadSessionConfig() {
  try {
    const raw = sessionStorage.getItem(GLOSSARY_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") {
      return null;
    }
    if (!data.source_language) {
      data.source_language = DEFAULT_SOURCE_LANGUAGE;
    }
    return data;
  } catch {
    return null;
  }
}

function saveStoredGlossary(data) {
  saveSessionConfig(data);
}

function saveSessionConfig(data) {
  const payload = {
    source_language: DEFAULT_SOURCE_LANGUAGE,
    ...(data || {}),
  };
  if (!payload.source_language) {
    payload.source_language = DEFAULT_SOURCE_LANGUAGE;
  }
  sessionStorage.setItem(GLOSSARY_STORAGE_KEY, JSON.stringify(payload));
}

function getStoredSourceLanguage() {
  const config = loadSessionConfig();
  return config?.source_language || DEFAULT_SOURCE_LANGUAGE;
}

function setStoredSourceLanguage(code) {
  const config = loadSessionConfig() || {};
  config.source_language = code || DEFAULT_SOURCE_LANGUAGE;
  saveSessionConfig(config);
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
