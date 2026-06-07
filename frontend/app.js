const WS_URL = `ws://${window.location.hostname}:8765/stream`;

const statusBadge = document.getElementById("status-badge");
const appSubtitle = document.getElementById("app-subtitle");
const subtitleList = document.getElementById("subtitle-list");
const subtitleMetricsBar = document.getElementById("subtitle-metrics-bar");
const metricsBar = document.getElementById("metrics-bar");
const sessionScenarioChip = document.getElementById("session-scenario-chip");
const sessionConfigPill = document.getElementById("session-config-pill");
const summaryMeta = document.getElementById("summary-meta");
const summaryTopic = document.getElementById("summary-topic");
const summaryTerms = document.getElementById("summary-terms");
const summaryBullets = document.getElementById("summary-bullets");
const formattedMeta = document.getElementById("formatted-meta");
const formattedContent = document.getElementById("formatted-content");
const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnStop = document.getElementById("btn-stop");
const btnTts = document.getElementById("btn-tts");
const btnNewSession = document.getElementById("btn-new-session");
const btnGlossaryView = document.getElementById("btn-glossary-view");
const btnHistory = document.getElementById("btn-history");
const btnHistoryClose = document.getElementById("btn-history-close");
const historyOverlay = document.getElementById("history-overlay");
const historyList = document.getElementById("history-list");
const historyDetail = document.getElementById("history-detail");
const loopbackSelect = document.getElementById("loopback-select");
const ttsOutputSelect = document.getElementById("tts-output-select");
const audioRouteControls = document.getElementById("audio-route-controls");
const audioRouteStatus = document.getElementById("audio-route-status");
const audioRouteHint = document.getElementById("audio-route-hint");

const LOOPBACK_STORAGE_KEY = "livetransai-loopback-index";
const TTS_OUTPUT_STORAGE_KEY = "livetransai-tts-output-id";
const SUBTITLE_FOCUS_KEY = "livetransai_subtitle_focus";
const FOCUS_SETTINGS_KEY = "livetransai_focus_subtitle_settings";
const FOCUS_SUMMARY_OPEN_KEY = "livetransai_focus_summary_open";
const DEFAULT_FOCUS_SETTINGS = {
  fontSize: "medium",
  showSource: true,
  showTranslation: true,
  showCorrection: true,
  visibleCount: 5,
};

const appRoot = document.querySelector(".app");
const btnSubtitleFocus = document.getElementById("btn-subtitle-focus");
const btnSubtitleSettings = document.getElementById("btn-subtitle-settings");
const btnSubtitleSettingsClose = document.getElementById("btn-subtitle-settings-close");
const btnSubtitleSettingsApply = document.getElementById("btn-subtitle-settings-apply");
const subtitleSettingsOverlay = document.getElementById("subtitle-settings-overlay");
const subtitleSettingsForm = document.getElementById("subtitle-settings-form");
const focusSettingsFontSize = document.getElementById("focus-settings-font-size");
const focusSettingsShowSource = document.getElementById("focus-settings-show-source");
const focusSettingsShowTranslation = document.getElementById("focus-settings-show-translation");
const focusSettingsShowCorrection = document.getElementById("focus-settings-show-correction");
const focusSettingsVisibleCount = document.getElementById("focus-settings-visible-count");
const focusSettingsError = document.getElementById("focus-settings-error");
const btnFocusSummary = document.getElementById("btn-focus-summary");
const focusSummaryDrawer = document.getElementById("focus-summary-drawer");
const focusSummaryMeta = document.getElementById("focus-summary-meta");
const focusSummaryTopic = document.getElementById("focus-summary-topic");
const focusSummaryTerms = document.getElementById("focus-summary-terms");
const focusSummaryBullets = document.getElementById("focus-summary-bullets");

let subtitleFocusMode = false;
let focusSummaryOpen = false;
let focusSubtitleSettings = { ...DEFAULT_FOCUS_SETTINGS };
let subtitleBuffer = [];

let selectedHistoryId = null;
let audioDevicesLoaded = false;
let sessionIsSpeaking = false;

let socket = null;
let sentenceCount = 0;
let correctionCount = 0;
let memoryCount = 0;
let formattedSentenceCount = 0;
let pendingInitialSync = true;
let lastSessionState = null;
let lastUiState = "ready";

const STATUS_LABELS = {
  ready: "就绪",
  speaking: "翻译中",
  paused: "已暂停",
  finished: "已完成",
  error: "错误",
};

const DEFAULT_APP_SUBTITLE = "AI 同声传译助手";

function renderLanguageRoute(payload) {
  if (!appSubtitle) {
    return;
  }
  if (!payload?.source?.label || !payload?.target?.label) {
    appSubtitle.textContent = DEFAULT_APP_SUBTITLE;
    return;
  }
  appSubtitle.textContent = `${DEFAULT_APP_SUBTITLE} · ${payload.source.label} → ${payload.target.label}`;
}

const SOURCE_LANGUAGE_LABELS = {
  en: "英语",
  ja: "日语",
  pt: "葡萄牙语",
  es: "西班牙语",
  id: "印尼语",
  de: "德语",
  fr: "法语",
};

function getStoredSourceLanguageLabel() {
  const stored = loadSessionConfig();
  const code = stored?.source_language || "en";
  return SOURCE_LANGUAGE_LABELS[code] || code;
}

function updateGlossaryViewLink() {
  if (!btnGlossaryView) {
    return;
  }
  btnGlossaryView.href = isLiveSessionActive() ? "/setup-view.html" : "/setup.html";
}

function syncLiveSessionFlag(state) {
  if (state === "speaking" || state === "paused") {
    markLiveSessionActive();
  } else if (state === "finished") {
    clearLiveSessionActive();
  } else if (state === "ready") {
    const wasActive =
      lastSessionState === "speaking" ||
      lastSessionState === "paused" ||
      lastSessionState === "finished";
    if (wasActive) {
      clearLiveSessionActive();
      if (window.translationTts) {
        window.translationTts.stop();
      }
    }
  }
  lastSessionState = state;
  updateGlossaryViewLink();
}

function renderStoredLanguageHint() {
  if (!appSubtitle) {
    return;
  }
  const sourceLabel = getStoredSourceLanguageLabel();
  appSubtitle.textContent = `${DEFAULT_APP_SUBTITLE} · ${sourceLabel} → 中文`;
}

function findScenarioByStoredScenario(scenarioText) {
  if (!scenarioText || !Array.isArray(DEMO_SCENARIOS)) {
    return null;
  }
  return DEMO_SCENARIOS.find((item) => item.scenario === scenarioText) || null;
}

function renderSessionContextChips() {
  const config = loadSessionConfig();
  const matched = findScenarioByStoredScenario(config?.scenario);
  const termCount = Object.keys(config?.term_map || {}).length;

  if (sessionScenarioChip) {
    if (matched || config?.scenario) {
      const label = matched?.label || (config.scenario || "").trim();
      const suffix = termCount > 0 ? ` · ${termCount} 条术语` : "";
      sessionScenarioChip.textContent = `${label}${suffix}`;
      sessionScenarioChip.classList.remove("hidden");
    } else {
      sessionScenarioChip.classList.add("hidden");
    }
  }

  if (sessionConfigPill) {
    sessionConfigPill.classList.toggle("hidden", termCount === 0);
  }
}

function setStatus(state, message) {
  lastUiState = state;
  statusBadge.className = `status-badge status-${state}`;
  statusBadge.textContent = message || STATUS_LABELS[state] || state;
  btnStart.disabled = state === "speaking" || state === "paused";
  if (state === "speaking" || state === "paused") {
    btnStart.textContent = "翻译中";
  } else {
    btnStart.textContent = "开始翻译";
  }
  const sessionActive = state === "speaking" || state === "paused";
  btnStop.disabled = !sessionActive;
  if (btnPause) {
    btnPause.disabled = !sessionActive;
    btnPause.textContent = state === "paused" ? "恢复" : "暂停";
  }
  if (sessionActive) {
    setAudioRouteEditing(false);
  } else if (state === "ready" || state === "finished" || state === "error") {
    setAudioRouteEditing(true);
  }
  updateCompactMetricsBar();
}

function sendCommand(action) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  const payload = { type: "command", action };
  if (action === "start") {
    const stored = loadStoredGlossary();
    if (stored && stored.term_map && Object.keys(stored.term_map).length > 0) {
      payload.glossary = stored;
    }
    const audio = getSelectedAudioConfig();
    if (audio) {
      payload.audio = audio;
    }
    if (window.translationTts) {
      payload.tts_enabled = window.translationTts.isEnabled();
    }
    payload.source_language = getStoredSourceLanguage();
  }
  socket.send(JSON.stringify(payload));
}

function sendTtsEnabled(enabled) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(JSON.stringify({ type: "command", action: "tts_enabled", enabled: Boolean(enabled) }));
}

function getSelectedAudioConfig() {
  if (!loopbackSelect || !ttsOutputSelect) {
    return null;
  }
  const loopbackIndex = Number(loopbackSelect.value);
  const ttsOutputId = ttsOutputSelect.value;
  if (!Number.isFinite(loopbackIndex) || !ttsOutputId) {
    return null;
  }
  return {
    loopback_index: loopbackIndex,
    tts_output_id: ttsOutputId,
  };
}

function persistAudioSelections() {
  if (loopbackSelect && loopbackSelect.value) {
    localStorage.setItem(LOOPBACK_STORAGE_KEY, loopbackSelect.value);
  }
  if (ttsOutputSelect && ttsOutputSelect.value) {
    localStorage.setItem(TTS_OUTPUT_STORAGE_KEY, ttsOutputSelect.value);
  }
}

function setAudioRouteEditing(enabled) {
  sessionIsSpeaking = !enabled;
  if (loopbackSelect) {
    loopbackSelect.disabled = !enabled;
  }
  if (ttsOutputSelect) {
    ttsOutputSelect.disabled = !enabled;
  }
  if (audioRouteControls) {
    audioRouteControls.classList.toggle("hidden", !enabled);
  }
  if (audioRouteStatus) {
    audioRouteStatus.classList.toggle("hidden", enabled);
  }
}

function renderAudioRouteStatus(payload) {
  if (!audioRouteStatus) {
    return;
  }
  const captureName = payload?.capture?.name || "—";
  const outputName = payload?.tts_output?.name || "—";
  const playback = payload?.playback === "backend" ? "后端播放" : "浏览器播放";
  audioRouteStatus.textContent = `监听：${captureName} · 译文：${outputName}（${playback}）`;
}

function populateSelect(select, options, valueKey, labelKey, storedValue) {
  if (!select) {
    return;
  }
  select.innerHTML = "";
  for (const option of options) {
    const element = document.createElement("option");
    element.value = String(option[valueKey]);
    element.textContent = option[labelKey];
    if (option.is_default) {
      element.textContent += "（默认）";
    }
    select.appendChild(element);
  }
  if (storedValue && options.some((option) => String(option[valueKey]) === String(storedValue))) {
    select.value = String(storedValue);
    return;
  }
  const defaultOption = options.find((option) => option.is_default) || options[0];
  if (defaultOption) {
    select.value = String(defaultOption[valueKey]);
  }
}

async function loadAudioDevices() {
  if (!loopbackSelect || !ttsOutputSelect) {
    return;
  }
  try {
    const response = await fetch("/api/audio/devices");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    populateSelect(
      loopbackSelect,
      payload.loopbacks || [],
      "index",
      "name",
      localStorage.getItem(LOOPBACK_STORAGE_KEY)
    );
    populateSelect(
      ttsOutputSelect,
      payload.outputs || [],
      "id",
      "name",
      localStorage.getItem(TTS_OUTPUT_STORAGE_KEY)
    );
    if (audioRouteHint && payload.hint) {
      audioRouteHint.textContent = payload.hint;
    }
    audioDevicesLoaded = true;
    persistAudioSelections();
  } catch (error) {
    if (audioRouteHint) {
      audioRouteHint.textContent = "无法加载音频设备列表，请确认后端已启动。";
    }
    console.error("Failed to load audio devices:", error);
  }
}

function sendCaptureSuppress(suppress) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(JSON.stringify({ type: "command", action: "suppress_capture", suppress: Boolean(suppress) }));
}

function resetUiForFreshSession() {
  if (window.translationTts) {
    window.translationTts.stop();
  }
  subtitleBuffer = [];
  subtitleList.innerHTML = "";
  renderEmptySubtitleState();
  renderEmptyFormattedState();
  resetSummary();
  sentenceCount = 0;
  correctionCount = 0;
  memoryCount = 0;
  updateCompactMetricsBar();
}

function restoreSessionSync(payload) {
  subtitleBuffer = [];
  subtitleList.innerHTML = "";
  const subtitles = payload.subtitles || [];
  if (subtitles.length === 0) {
    renderEmptySubtitleState();
  } else {
    for (const item of subtitles) {
      subtitleBuffer.push(normalizeSubtitlePayload(item));
    }
    if (subtitleFocusMode) {
      renderVisibleSubtitles();
    } else {
      for (const item of subtitles) {
        appendSubtitleToDom(item);
      }
    }
  }

  if (payload.summary) {
    renderSummary(payload.summary);
  }

  if (payload.formatted) {
    renderFormattedSnapshot({
      paragraphs: payload.formatted.paragraphs || [],
      updated_at_sentence: payload.formatted.updated_at_sentence || 0,
    });
  } else {
    renderEmptyFormattedState();
  }

  if (payload.metrics) {
    updateMetrics(payload.metrics);
  }

  if (payload.status) {
    setStatus(payload.status);
  }
}

function refreshSubtitleLiveHighlight() {
  const items = subtitleList.querySelectorAll(".subtitle-item");
  items.forEach((item, index) => {
    item.classList.toggle("subtitle-item-live", index === items.length - 1);
  });
}

function renderEmptySubtitleState() {
  if (subtitleList.children.length === 0) {
    const sourceLabel = getStoredSourceLanguageLabel();
    subtitleList.innerHTML = `<div class="empty-state"><p>点击「开始翻译」，然后播放${sourceLabel}音频</p><p class="subtitle-empty-steps">① 选择监听设备 → ② 开始翻译 → ③ 播放音频</p></div>`;
  }
}

function renderEmptyFormattedState() {
  formattedContent.innerHTML =
    '<div class="empty-state">翻译结束后，纠错后的完整段落将在此展示</div>';
  formattedMeta.textContent = "翻译结束后展示";
  formattedSentenceCount = 0;
}

function isCorrectedSubtitle(payload) {
  const version = Number(payload.version || payload.new_version || 1);
  return Boolean(payload.old_translation) || version > 1 || payload.confidence === "corrected";
}

function getSubtitleTag(payload) {
  return isCorrectedSubtitle(payload) ? "corrected" : payload.confidence || "fast";
}

function buildSubtitleTranslationHtml(payload, options = {}) {
  const showCorrection = options.showCorrection !== false;
  const oldTranslation = payload.old_translation || "";
  const newTranslation = payload.new_translation || payload.translation || "";
  if (showCorrection && oldTranslation) {
    const reasonHtml = payload.reason
      ? `<div class="correction-reason">修正：${escapeHtml(payload.reason)}</div>`
      : "";
    return `ZH <span class="translation-old">${escapeHtml(oldTranslation)}</span> <span class="translation-new">${escapeHtml(newTranslation)}</span>${reasonHtml}`;
  }
  return `ZH ${escapeHtml(newTranslation)}`;
}

function getSubtitleSourceFromItem(item) {
  const sourceEl = item.querySelector(".subtitle-source");
  if (!sourceEl) {
    return "";
  }
  return sourceEl.textContent.replace(/^EN\s*/, "").trim();
}

function mountSubtitleItem(item, payload, options = {}) {
  const subtitleId = payload.id || payload.target_id || "";
  const version = payload.new_version || payload.version || 1;
  const showCorrection = options.showCorrection !== false;
  item.className = "subtitle-item";
  if (isCorrectedSubtitle(payload)) {
    item.classList.add("subtitle-corrected");
  }
  item.dataset.id = subtitleId;
  item.dataset.version = String(version);
  item.innerHTML = `
    <div class="subtitle-meta">
      <span>${escapeHtml(subtitleId)}</span>
      <span class="subtitle-tag">${escapeHtml(getSubtitleTag(payload))}</span>
    </div>
    <div class="subtitle-source">EN ${escapeHtml(payload.source || "")}</div>
    <div class="subtitle-translation">${buildSubtitleTranslationHtml(payload, { showCorrection })}</div>
  `;
}

function normalizeSubtitlePayload(payload) {
  return {
    id: payload.id || payload.target_id || "",
    version: payload.new_version || payload.version || 1,
    source: payload.source || "",
    translation: payload.translation || payload.new_translation || "",
    old_translation: payload.old_translation || "",
    new_translation: payload.new_translation || payload.translation || "",
    reason: payload.reason || "",
    confidence: payload.confidence || "fast",
  };
}

function getVisibleBufferSlice() {
  const count = Number(focusSubtitleSettings.visibleCount) || 0;
  if (count <= 0) {
    return subtitleBuffer.slice();
  }
  return subtitleBuffer.slice(-count);
}

function appendSubtitleToDom(payload) {
  const empty = subtitleList.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  const item = document.createElement("article");
  mountSubtitleItem(item, payload);
  subtitleList.appendChild(item);
  refreshSubtitleLiveHighlight();
  subtitleList.scrollTop = subtitleList.scrollHeight;
}

function renderAllSubtitlesToDom() {
  subtitleList.innerHTML = "";
  if (subtitleBuffer.length === 0) {
    renderEmptySubtitleState();
    return;
  }
  for (const payload of subtitleBuffer) {
    const item = document.createElement("article");
    mountSubtitleItem(item, payload);
    subtitleList.appendChild(item);
  }
  refreshSubtitleLiveHighlight();
  subtitleList.scrollTop = subtitleList.scrollHeight;
}

function renderVisibleSubtitles() {
  if (!subtitleFocusMode) {
    return;
  }

  const visible = getVisibleBufferSlice();
  subtitleList.innerHTML = "";
  if (visible.length === 0) {
    renderEmptySubtitleState();
    return;
  }

  for (const payload of visible) {
    const item = document.createElement("article");
    mountSubtitleItem(item, payload, {
      showCorrection: focusSubtitleSettings.showCorrection,
    });
    subtitleList.appendChild(item);
  }
  refreshSubtitleLiveHighlight();
  subtitleList.scrollTop = subtitleList.scrollHeight;
}

function updateSubtitleBufferCorrection(payload) {
  const targetId = payload.target_id;
  const index = subtitleBuffer.findIndex((entry) => entry.id === targetId);
  if (index === -1) {
    return false;
  }
  if (String(subtitleBuffer[index].version) !== String(payload.base_version)) {
    return false;
  }

  subtitleBuffer[index] = {
    ...subtitleBuffer[index],
    version: payload.new_version,
    old_translation: payload.old_translation,
    new_translation: payload.new_translation,
    translation: payload.new_translation,
    reason: payload.reason,
    confidence: "corrected",
  };
  return true;
}

function appendSubtitle(payload) {
  subtitleBuffer.push(normalizeSubtitlePayload(payload));
  if (subtitleFocusMode) {
    renderVisibleSubtitles();
  } else {
    appendSubtitleToDom(payload);
  }
}

function applyCorrection(payload) {
  const updated = updateSubtitleBufferCorrection(payload);
  if (subtitleFocusMode) {
    if (updated) {
      renderVisibleSubtitles();
    }
    return;
  }

  const item = subtitleList.querySelector(`[data-id="${payload.target_id}"]`);
  if (!item) {
    return;
  }
  if (String(item.dataset.version) !== String(payload.base_version)) {
    return;
  }

  mountSubtitleItem(item, {
    id: payload.target_id,
    version: payload.new_version,
    source: getSubtitleSourceFromItem(item),
    old_translation: payload.old_translation,
    new_translation: payload.new_translation,
    translation: payload.new_translation,
    reason: payload.reason,
    confidence: "corrected",
  });
}

function ensureParagraph(paragraphId, paragraphIndex) {
  let paragraph = formattedContent.querySelector(`[data-paragraph-id="${paragraphId}"]`);
  if (paragraph) {
    return paragraph;
  }

  const empty = formattedContent.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  paragraph = document.createElement("div");
  paragraph.className = "formatted-paragraph";
  paragraph.dataset.paragraphId = paragraphId;

  const paragraphs = formattedContent.querySelectorAll(".formatted-paragraph");
  if (paragraphs.length === 0 || paragraphIndex >= paragraphs.length) {
    formattedContent.appendChild(paragraph);
  } else {
    formattedContent.insertBefore(paragraph, paragraphs[paragraphIndex]);
  }
  return paragraph;
}

function appendFormattedDelta(payload) {
  const paragraph = ensureParagraph(payload.paragraph_id, payload.paragraph_index ?? 0);
  const span = document.createElement("span");
  span.className = "formatted-sentence";
  span.dataset.sentenceId = payload.sentence_id;
  span.dataset.version = String(payload.version || 1);
  span.textContent = payload.text || "";
  paragraph.appendChild(span);
  formattedSentenceCount += 1;
  formattedMeta.textContent = `已规整 ${formattedSentenceCount} 句`;
  formattedContent.scrollTop = formattedContent.scrollHeight;
}

function applyFormattedPatch(payload) {
  const span = formattedContent.querySelector(`[data-sentence-id="${payload.target_id}"]`);
  if (!span) {
    return;
  }
  if (String(span.dataset.version) !== String(payload.base_version)) {
    return;
  }
  span.textContent = payload.new_text || "";
  span.dataset.version = String(payload.new_version);
  span.classList.add("formatted-patched");
}

function renderFormattedSnapshot(payload) {
  formattedContent.innerHTML = "";
  formattedSentenceCount = 0;
  const paragraphs = payload.paragraphs || [];
  if (paragraphs.length === 0) {
    renderEmptyFormattedState();
    return;
  }

  paragraphs.forEach((text, index) => {
    const paragraph = document.createElement("div");
    paragraph.className = "formatted-paragraph";
    paragraph.dataset.paragraphId = `p_${String(index + 1).padStart(3, "0")}`;
    paragraph.textContent = text;
    formattedContent.appendChild(paragraph);
  });

  formattedMeta.textContent = `已规整 ${payload.updated_at_sentence || paragraphs.length} 句`;
}

function updateCompactMetricsBar() {
  if (!subtitleMetricsBar) {
    return;
  }
  const sessionActive = lastUiState === "speaking" || lastUiState === "paused";
  const showBar = sessionActive || sentenceCount > 0;
  subtitleMetricsBar.classList.toggle("hidden", !showBar);
  if (showBar) {
    subtitleMetricsBar.textContent = `已翻译 ${sentenceCount} 句 · 已修正 ${correctionCount} 处`;
  }
}

function updateMetrics(payload) {
  sentenceCount = payload.sentence_count ?? sentenceCount;
  correctionCount = payload.correction_count ?? correctionCount;
  memoryCount = payload.memory_count ?? memoryCount;
  const mergeCount = payload.merge_count ?? 0;
  const fragmentCount = payload.ast_fragment_count ?? 0;
  const latencyP50 = payload.latency_p50;
  const latencyP99 = payload.latency_p99;
  const latencyPart =
    latencyP50 != null && latencyP50 > 0
      ? `延迟: ${Number(latencyP50).toFixed(1)}s (P99: ${Number(latencyP99 || 0).toFixed(1)}s) · `
      : "";
  const mergeHint =
    fragmentCount > sentenceCount
      ? ` · 合并 ${mergeCount} 次（AST ${fragmentCount} 段 → ${sentenceCount} 句）`
      : "";
  metricsBar.textContent = `${latencyPart}已翻译: ${sentenceCount} 句 · 已修正: ${correctionCount} 处 · 记忆: ${memoryCount} 条${mergeHint}`;
  updateCompactMetricsBar();
}

function fillSummaryElements(metaEl, topicEl, termsEl, bulletsEl, payload) {
  const at = payload.updated_at_sentence ?? 0;
  if (metaEl) {
    metaEl.textContent =
      at > 0 ? `已更新至第 ${at} 句` : "会话主题将在翻译开始后自动生成";
  }

  const topic = (payload.topic || "").trim();
  if (topicEl) {
    topicEl.textContent = topic ? `主题：${topic}` : "主题：—";
  }

  const terms = payload.term_map || {};
  const termEntries = Object.entries(terms);
  if (termsEl) {
    if (termEntries.length === 0) {
      termsEl.textContent = "";
    } else {
      termsEl.innerHTML = termEntries
        .map(
          ([source, target]) =>
            `<span class="summary-term">${escapeHtml(source)} → ${escapeHtml(target)}</span>`
        )
        .join("");
    }
  }

  if (bulletsEl) {
    bulletsEl.innerHTML = "";
    for (const point of payload.bullet_points || []) {
      const li = document.createElement("li");
      li.textContent = point;
      bulletsEl.appendChild(li);
    }
  }
}

function renderSummary(payload) {
  fillSummaryElements(summaryMeta, summaryTopic, summaryTerms, summaryBullets, payload);
  fillSummaryElements(
    focusSummaryMeta,
    focusSummaryTopic,
    focusSummaryTerms,
    focusSummaryBullets,
    payload
  );
}

function resetSummary() {
  renderSummary({
    topic: "",
    term_map: {},
    bullet_points: [],
    updated_at_sentence: 0,
  });
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTimestamp(ts) {
  if (!ts) {
    return "—";
  }
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function openHistoryPanel() {
  historyOverlay.classList.remove("hidden");
  historyOverlay.setAttribute("aria-hidden", "false");
  loadHistoryList();
}

function closeHistoryPanel() {
  historyOverlay.classList.add("hidden");
  historyOverlay.setAttribute("aria-hidden", "true");
}

function loadFocusSubtitleSettings() {
  try {
    const raw = localStorage.getItem(FOCUS_SETTINGS_KEY);
    if (!raw) {
      focusSubtitleSettings = { ...DEFAULT_FOCUS_SETTINGS };
      return;
    }
    const parsed = JSON.parse(raw);
    focusSubtitleSettings = {
      ...DEFAULT_FOCUS_SETTINGS,
      ...parsed,
    };
  } catch {
    focusSubtitleSettings = { ...DEFAULT_FOCUS_SETTINGS };
  }
}

function saveFocusSubtitleSettings() {
  try {
    localStorage.setItem(FOCUS_SETTINGS_KEY, JSON.stringify(focusSubtitleSettings));
  } catch {
    // ignore storage errors
  }
}

function syncFocusSettingsForm() {
  if (focusSettingsFontSize) {
    focusSettingsFontSize.value = focusSubtitleSettings.fontSize;
  }
  if (focusSettingsShowSource) {
    focusSettingsShowSource.checked = focusSubtitleSettings.showSource;
  }
  if (focusSettingsShowTranslation) {
    focusSettingsShowTranslation.checked = focusSubtitleSettings.showTranslation;
  }
  if (focusSettingsShowCorrection) {
    focusSettingsShowCorrection.checked = focusSubtitleSettings.showCorrection;
  }
  if (focusSettingsVisibleCount) {
    focusSettingsVisibleCount.value = String(focusSubtitleSettings.visibleCount);
  }
  if (focusSettingsError) {
    focusSettingsError.classList.add("hidden");
    focusSettingsError.textContent = "";
  }
}

function readFocusSettingsForm() {
  return {
    fontSize: focusSettingsFontSize?.value || DEFAULT_FOCUS_SETTINGS.fontSize,
    showSource: Boolean(focusSettingsShowSource?.checked),
    showTranslation: Boolean(focusSettingsShowTranslation?.checked),
    showCorrection: Boolean(focusSettingsShowCorrection?.checked),
    visibleCount: Number(focusSettingsVisibleCount?.value ?? DEFAULT_FOCUS_SETTINGS.visibleCount),
  };
}

function applyFocusSubtitleSettings() {
  if (!appRoot) {
    return;
  }

  appRoot.dataset.focusFont = focusSubtitleSettings.fontSize;
  appRoot.dataset.focusShowSource = focusSubtitleSettings.showSource ? "true" : "false";
  appRoot.dataset.focusShowTranslation = focusSubtitleSettings.showTranslation ? "true" : "false";

  if (subtitleFocusMode) {
    renderVisibleSubtitles();
  }
}

function openSubtitleSettingsPanel() {
  if (!subtitleSettingsOverlay) {
    return;
  }
  syncFocusSettingsForm();
  subtitleSettingsOverlay.classList.remove("hidden");
  subtitleSettingsOverlay.setAttribute("aria-hidden", "false");
}

function closeSubtitleSettingsPanel() {
  if (!subtitleSettingsOverlay) {
    return;
  }
  subtitleSettingsOverlay.classList.add("hidden");
  subtitleSettingsOverlay.setAttribute("aria-hidden", "true");
  if (focusSettingsError) {
    focusSettingsError.classList.add("hidden");
    focusSettingsError.textContent = "";
  }
}

function handleSubtitleSettingsSubmit(event) {
  event.preventDefault();
  const next = readFocusSettingsForm();
  if (!next.showSource && !next.showTranslation) {
    if (focusSettingsError) {
      focusSettingsError.textContent = "原文与译文至少显示一项";
      focusSettingsError.classList.remove("hidden");
    }
    return;
  }

  focusSubtitleSettings = next;
  saveFocusSubtitleSettings();
  applyFocusSubtitleSettings();
  closeSubtitleSettingsPanel();
}

function setFocusSummaryDrawer(open) {
  focusSummaryOpen = Boolean(open);
  if (appRoot) {
    appRoot.classList.toggle("focus-summary-open", focusSummaryOpen);
  }
  if (btnFocusSummary) {
    btnFocusSummary.setAttribute("aria-expanded", focusSummaryOpen ? "true" : "false");
    btnFocusSummary.textContent = focusSummaryOpen ? "摘要 ▴" : "摘要 ▾";
  }
  if (focusSummaryDrawer) {
    focusSummaryDrawer.setAttribute("aria-hidden", focusSummaryOpen ? "false" : "true");
  }
  try {
    if (focusSummaryOpen) {
      sessionStorage.setItem(FOCUS_SUMMARY_OPEN_KEY, "1");
    } else {
      sessionStorage.removeItem(FOCUS_SUMMARY_OPEN_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

function toggleFocusSummaryDrawer() {
  setFocusSummaryDrawer(!focusSummaryOpen);
}

function closeFocusSummaryDrawer() {
  setFocusSummaryDrawer(false);
}

function setSubtitleFocusMode(enabled) {
  subtitleFocusMode = Boolean(enabled);
  if (appRoot) {
    appRoot.classList.toggle("subtitle-focus-mode", subtitleFocusMode);
  }
  if (btnSubtitleFocus) {
    btnSubtitleFocus.textContent = subtitleFocusMode ? "退出专注" : "专注字幕";
    btnSubtitleFocus.setAttribute("aria-pressed", subtitleFocusMode ? "true" : "false");
    btnSubtitleFocus.title = subtitleFocusMode
      ? "恢复完整界面"
      : "隐藏摘要与控制区，放大字幕";
  }
  if (btnSubtitleSettings) {
    btnSubtitleSettings.classList.toggle("hidden", !subtitleFocusMode);
  }
  if (btnFocusSummary) {
    btnFocusSummary.classList.toggle("hidden", !subtitleFocusMode);
  }
  try {
    if (subtitleFocusMode) {
      sessionStorage.setItem(SUBTITLE_FOCUS_KEY, "1");
    } else {
      sessionStorage.removeItem(SUBTITLE_FOCUS_KEY);
    }
  } catch {
    // ignore storage errors
  }

  if (subtitleFocusMode) {
    applyFocusSubtitleSettings();
    renderVisibleSubtitles();
    let drawerOpen = false;
    try {
      drawerOpen = sessionStorage.getItem(FOCUS_SUMMARY_OPEN_KEY) === "1";
    } catch {
      drawerOpen = false;
    }
    setFocusSummaryDrawer(drawerOpen);
  } else {
    closeSubtitleSettingsPanel();
    closeFocusSummaryDrawer();
    renderAllSubtitlesToDom();
  }
}

function toggleSubtitleFocusMode() {
  setSubtitleFocusMode(!subtitleFocusMode);
}

function initSubtitleFocusMode() {
  loadFocusSubtitleSettings();
  applyFocusSubtitleSettings();
  let stored = false;
  try {
    stored = sessionStorage.getItem(SUBTITLE_FOCUS_KEY) === "1";
  } catch {
    stored = false;
  }
  setSubtitleFocusMode(stored);
}

async function startNewTranslation() {
  btnNewSession.disabled = true;
  try {
    await fetch("/api/session/stop", { method: "POST" });
  } catch {
    sendCommand("stop");
  }
  clearLiveSessionActive();
  updateGlossaryViewLink();
  window.location.href = "/";
}

async function loadHistoryList() {
  historyList.innerHTML = '<div class="empty-state">加载中…</div>';
  try {
    const response = await fetch("/api/sessions");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    renderHistoryList(payload.sessions || []);
  } catch (error) {
    historyList.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderHistoryList(sessions) {
  if (sessions.length === 0) {
    historyList.innerHTML = '<div class="empty-state">暂无历史会话</div>';
    historyDetail.innerHTML = '<div class="empty-state">完成一次翻译并停止后，会话将出现在这里</div>';
    return;
  }

  historyList.innerHTML = "";
  for (const session of sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.dataset.sessionId = session.session_id;
    if (session.session_id === selectedHistoryId) {
      button.classList.add("active");
    }

    const title = (session.topic || "").trim() || "未命名会话";
    const meta = `${formatTimestamp(session.stopped_at)} · ${session.sentence_count || 0} 句 · 修正 ${session.correction_count || 0} 处`;
    const preview = (session.preview_zh || "").trim() || "（无规整译文预览）";

    button.innerHTML = `
      <div class="history-item-title">${escapeHtml(title)}</div>
      <div class="history-item-meta">${escapeHtml(meta)}</div>
      <div class="history-item-preview">${escapeHtml(preview)}</div>
    `;
    button.addEventListener("click", () => loadHistoryDetail(session.session_id));
    historyList.appendChild(button);
  }

  if (!selectedHistoryId && sessions[0]) {
    loadHistoryDetail(sessions[0].session_id);
  }
}

async function loadHistoryDetail(sessionId) {
  selectedHistoryId = sessionId;
  for (const item of historyList.querySelectorAll(".history-item")) {
    item.classList.toggle("active", item.dataset.sessionId === sessionId);
  }

  historyDetail.innerHTML = '<div class="empty-state">加载详情…</div>';
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    renderHistoryDetail(payload);
  } catch (error) {
    historyDetail.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderHistorySentence(item) {
  const corrected = isCorrectedSubtitle(item);
  const tag = getSubtitleTag(item);
  const articleClass = corrected ? "subtitle-item subtitle-corrected" : "subtitle-item";
  const translationHtml = buildSubtitleTranslationHtml({
    translation: item.translation || "",
    old_translation: item.old_translation || "",
    new_translation: item.translation || "",
    reason: item.reason || "",
  });
  return `
    <article class="${articleClass}">
      <div class="subtitle-meta">
        <span>${escapeHtml(item.id || "")}</span>
        <span class="subtitle-tag">${escapeHtml(tag)}</span>
      </div>
      <div class="subtitle-source">EN ${escapeHtml(item.source || "")}</div>
      <div class="subtitle-translation">${translationHtml}</div>
    </article>
  `;
}

function renderHistoryDetail(payload) {
  const meta = payload.meta || {};
  const summary = payload.summary || {};
  const paragraphs = payload.formatted?.paragraphs || [];
  const sentences = payload.sentences || [];

  const topic = (summary.topic || meta.topic || "").trim() || "—";
  const termEntries = Object.entries(summary.term_map || {});
  const termsHtml = termEntries.length
    ? termEntries
        .map(([source, target]) => `<span class="summary-term">${escapeHtml(source)} → ${escapeHtml(target)}</span>`)
        .join("")
    : '<span class="summary-meta">无术语</span>';

  const bullets = summary.bullet_points || [];
  const bulletsHtml = bullets.length
    ? `<ul class="summary-bullets">${bullets.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`
    : '<div class="summary-meta">无要点</div>';

  const formattedHtml = paragraphs.length
    ? paragraphs
        .map((text) => `<div class="formatted-paragraph">${escapeHtml(text)}</div>`)
        .join("")
    : '<div class="empty-state">无规整译文</div>';

  const sentencesHtml = sentences.length
    ? sentences.map((item) => renderHistorySentence(item)).join("")
    : '<div class="empty-state">无句级记录</div>';

  historyDetail.innerHTML = `
    <div class="history-section">
      <h3>会话信息</h3>
      <div class="summary-meta">${escapeHtml(formatTimestamp(meta.started_at))} → ${escapeHtml(formatTimestamp(meta.stopped_at))}</div>
      <div class="summary-meta">${escapeHtml(String(meta.sentence_count || 0))} 句 · 修正 ${escapeHtml(String(meta.correction_count || 0))} 处 · 术语 ${escapeHtml(String(meta.term_count || 0))} 条</div>
    </div>
    <div class="history-section summary-panel">
      <h3>摘要</h3>
      <div class="summary-topic">主题：${escapeHtml(topic)}</div>
      <div class="summary-terms">${termsHtml}</div>
      ${bulletsHtml}
    </div>
    <div class="history-section formatted-panel">
      <h3>规整译文</h3>
      <div class="formatted-content">${formattedHtml}</div>
    </div>
    <div class="history-section">
      <h3>句级字幕</h3>
      <div class="history-sentences">${sentencesHtml}</div>
    </div>
  `;
}

function connect() {
  socket = new WebSocket(WS_URL);
  pendingInitialSync = true;

  socket.addEventListener("open", () => {
    pendingInitialSync = true;
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "session_sync") {
      restoreSessionSync(payload);
      pendingInitialSync = false;
      return;
    }
    if (payload.type === "status") {
      setStatus(payload.state, payload.message);
      syncLiveSessionFlag(payload.state);
      if (payload.state === "finished") {
        if (window.translationTts) {
          window.translationTts.stop();
        }
      }
      if (pendingInitialSync && payload.state === "ready") {
        resetUiForFreshSession();
        pendingInitialSync = false;
      }
      return;
    }
    if (payload.type === "tts_config") {
      if (window.translationTts) {
        window.translationTts.setConfig(payload);
        updateTtsButton();
      }
      return;
    }
    if (payload.type === "audio_route") {
      renderAudioRouteStatus(payload);
      setAudioRouteEditing(false);
      return;
    }
    if (payload.type === "language_route") {
      renderLanguageRoute(payload);
      return;
    }
    if (payload.type === "tts_start") {
      if (window.translationTts) {
        window.translationTts.onStart(payload);
      }
      return;
    }
    if (payload.type === "tts_audio") {
      if (window.translationTts) {
        window.translationTts.onAudio(payload);
      }
      return;
    }
    if (payload.type === "tts_end") {
      if (window.translationTts) {
        window.translationTts.onEnd(payload);
      }
      return;
    }
    if (payload.type === "subtitle") {
      appendSubtitle(payload);
      return;
    }
    if (payload.type === "correction") {
      applyCorrection(payload);
      return;
    }
    if (payload.type === "summary") {
      renderSummary(payload);
      return;
    }
    if (payload.type === "formatted_delta") {
      appendFormattedDelta(payload);
      return;
    }
    if (payload.type === "formatted_patch") {
      applyFormattedPatch(payload);
      return;
    }
    if (payload.type === "formatted_snapshot") {
      renderFormattedSnapshot(payload);
      return;
    }
    if (payload.type === "metrics") {
      updateMetrics(payload);
    }
  });

  socket.addEventListener("close", () => {
    setStatus("ready");
    setTimeout(connect, 2000);
  });
}

function updateTtsButton() {
  if (!btnTts || !window.translationTts) {
    return;
  }
  const player = window.translationTts;
  const on = player.isEnabled();
  btnTts.classList.toggle("active", on);
  btnTts.setAttribute("aria-pressed", on ? "true" : "false");
  btnTts.textContent = on ? "语音开" : "语音关";
  if (!player.supported) {
    btnTts.disabled = true;
    btnTts.title = "当前浏览器不支持音频播放";
    return;
  }
  if (!player.isAvailable()) {
    btnTts.title = "等待豆包 s2s 语音流（需 AST_MODE=s2s）";
  } else if (player.isBackendMode()) {
    btnTts.title = "控制后端译文语音播放（输出到所选「译文输出」设备）";
  } else {
    btnTts.title = "播放豆包同声传译中文语音（建议戴耳机避免回声）";
  }
}

btnStart.addEventListener("click", () => sendCommand("start"));
if (btnPause) {
  btnPause.addEventListener("click", () => {
    const isPaused = statusBadge.classList.contains("status-paused");
    sendCommand(isPaused ? "resume" : "pause");
  });
}
btnStop.addEventListener("click", () => sendCommand("stop"));
if (btnTts) {
  btnTts.addEventListener("click", () => {
    if (!window.translationTts) {
      return;
    }
    const enabled = window.translationTts.toggle();
    updateTtsButton();
    if (window.translationTts.isBackendMode() && sessionIsSpeaking) {
      sendTtsEnabled(enabled);
    }
  });
}
if (loopbackSelect) {
  loopbackSelect.addEventListener("change", persistAudioSelections);
}
if (ttsOutputSelect) {
  ttsOutputSelect.addEventListener("change", persistAudioSelections);
}
btnNewSession.addEventListener("click", () => {
  startNewTranslation();
});
btnHistory.addEventListener("click", openHistoryPanel);
btnHistoryClose.addEventListener("click", closeHistoryPanel);
historyOverlay.addEventListener("click", (event) => {
  if (event.target === historyOverlay) {
    closeHistoryPanel();
  }
});
if (btnSubtitleFocus) {
  btnSubtitleFocus.addEventListener("click", toggleSubtitleFocusMode);
}
if (btnFocusSummary) {
  btnFocusSummary.addEventListener("click", toggleFocusSummaryDrawer);
}
if (btnSubtitleSettings) {
  btnSubtitleSettings.addEventListener("click", openSubtitleSettingsPanel);
}
if (btnSubtitleSettingsClose) {
  btnSubtitleSettingsClose.addEventListener("click", closeSubtitleSettingsPanel);
}
if (subtitleSettingsOverlay) {
  subtitleSettingsOverlay.addEventListener("click", (event) => {
    if (event.target === subtitleSettingsOverlay) {
      closeSubtitleSettingsPanel();
    }
  });
}
if (subtitleSettingsForm) {
  subtitleSettingsForm.addEventListener("submit", handleSubtitleSettingsSubmit);
}
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  if (historyOverlay && !historyOverlay.classList.contains("hidden")) {
    closeHistoryPanel();
    return;
  }
  if (subtitleSettingsOverlay && !subtitleSettingsOverlay.classList.contains("hidden")) {
    closeSubtitleSettingsPanel();
    return;
  }
  if (subtitleFocusMode && focusSummaryOpen) {
    closeFocusSummaryDrawer();
    return;
  }
  if (subtitleFocusMode) {
    setSubtitleFocusMode(false);
  }
});

renderEmptySubtitleState();
renderEmptyFormattedState();
resetSummary();
updateTtsButton();
setAudioRouteEditing(true);
renderStoredLanguageHint();
renderSessionContextChips();
markLiveSessionActive();
updateGlossaryViewLink();
initSubtitleFocusMode();
loadAudioDevices();
if (window.translationTts) {
  window.translationTts.setCaptureControl(sendCaptureSuppress);
}
connect();
