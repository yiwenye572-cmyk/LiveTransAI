const WS_URL = `ws://${window.location.hostname}:8765/stream`;

const statusBadge = document.getElementById("status-badge");
const subtitleList = document.getElementById("subtitle-list");
const metricsBar = document.getElementById("metrics-bar");
const summaryMeta = document.getElementById("summary-meta");
const summaryTopic = document.getElementById("summary-topic");
const summaryTerms = document.getElementById("summary-terms");
const summaryBullets = document.getElementById("summary-bullets");
const formattedMeta = document.getElementById("formatted-meta");
const formattedContent = document.getElementById("formatted-content");
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");
const btnHistory = document.getElementById("btn-history");
const btnHistoryClose = document.getElementById("btn-history-close");
const historyOverlay = document.getElementById("history-overlay");
const historyList = document.getElementById("history-list");
const historyDetail = document.getElementById("history-detail");

let selectedHistoryId = null;

let socket = null;
let sentenceCount = 0;
let correctionCount = 0;
let memoryCount = 0;
let formattedSentenceCount = 0;

const STATUS_LABELS = {
  ready: "就绪",
  speaking: "翻译中",
  finished: "已完成",
  error: "错误",
};

function setStatus(state, message) {
  statusBadge.className = `status-badge status-${state}`;
  statusBadge.textContent = message || STATUS_LABELS[state] || state;
  btnStart.disabled = state === "speaking";
  btnStop.disabled = state !== "speaking";
}

function sendCommand(action) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(JSON.stringify({ type: "command", action }));
}

function renderEmptySubtitleState() {
  if (subtitleList.children.length === 0) {
    subtitleList.innerHTML = '<div class="empty-state">点击“开始翻译”，然后播放英文音频</div>';
  }
}

function renderEmptyFormattedState() {
  formattedContent.innerHTML = '<div class="empty-state">纠错批次完成后，规整段落将在此追加</div>';
  formattedMeta.textContent = "等待纠错批次…";
  formattedSentenceCount = 0;
}

function appendSubtitle(payload) {
  const empty = subtitleList.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  const item = document.createElement("article");
  item.className = "subtitle-item";
  item.dataset.id = payload.id;
  item.dataset.version = String(payload.version || 1);
  item.innerHTML = `
    <div class="subtitle-meta">
      <span>${payload.id}</span>
      <span class="subtitle-tag">${payload.confidence || "fast"}</span>
    </div>
    <div class="subtitle-source">EN ${escapeHtml(payload.source || "")}</div>
    <div class="subtitle-translation">ZH ${escapeHtml(payload.translation || "")}</div>
  `;
  subtitleList.appendChild(item);
  subtitleList.scrollTop = subtitleList.scrollHeight;
}

function applyCorrection(payload) {
  const item = subtitleList.querySelector(`[data-id="${payload.target_id}"]`);
  if (!item) {
    return;
  }
  if (String(item.dataset.version) !== String(payload.base_version)) {
    return;
  }

  const translationEl = item.querySelector(".subtitle-translation");
  const tagEl = item.querySelector(".subtitle-tag");
  if (!translationEl) {
    return;
  }

  const reasonHtml = payload.reason
    ? `<div class="correction-reason">修正：${escapeHtml(payload.reason)}</div>`
    : "";

  translationEl.innerHTML = `ZH <span class="translation-old">${escapeHtml(payload.old_translation || "")}</span> <span class="translation-new">${escapeHtml(payload.new_translation || "")}</span>${reasonHtml}`;
  item.dataset.version = String(payload.new_version);
  item.classList.add("subtitle-corrected");
  if (tagEl) {
    tagEl.textContent = "corrected";
  }
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

function updateMetrics(payload) {
  sentenceCount = payload.sentence_count ?? sentenceCount;
  correctionCount = payload.correction_count ?? correctionCount;
  memoryCount = payload.memory_count ?? memoryCount;
  const mergeCount = payload.merge_count ?? 0;
  const fragmentCount = payload.ast_fragment_count ?? 0;
  const mergeHint =
    fragmentCount > sentenceCount
      ? ` · 合并 ${mergeCount} 次（AST ${fragmentCount} 段 → ${sentenceCount} 句）`
      : "";
  metricsBar.textContent = `已翻译: ${sentenceCount} 句 · 已修正: ${correctionCount} 处 · 记忆: ${memoryCount} 条${mergeHint}`;
}

function renderSummary(payload) {
  const at = payload.updated_at_sentence ?? 0;
  summaryMeta.textContent = at > 0 ? `已更新至第 ${at} 句` : "等待更新…";

  const topic = (payload.topic || "").trim();
  summaryTopic.textContent = topic ? `主题：${topic}` : "主题：—";

  const terms = payload.term_map || {};
  const termEntries = Object.entries(terms);
  if (termEntries.length === 0) {
    summaryTerms.textContent = "";
  } else {
    summaryTerms.innerHTML = termEntries
      .map(([source, target]) => `<span class="summary-term">${escapeHtml(source)} → ${escapeHtml(target)}</span>`)
      .join("");
  }

  summaryBullets.innerHTML = "";
  for (const point of payload.bullet_points || []) {
    const li = document.createElement("li");
    li.textContent = point;
    summaryBullets.appendChild(li);
  }
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
    ? sentences
        .map(
          (item) => `
            <article class="subtitle-item">
              <div class="subtitle-meta">
                <span>${escapeHtml(item.id || "")}</span>
                <span class="subtitle-tag">v${escapeHtml(String(item.version || 1))}</span>
              </div>
              <div class="subtitle-source">EN ${escapeHtml(item.source || "")}</div>
              <div class="subtitle-translation">ZH ${escapeHtml(item.translation || "")}</div>
            </article>
          `
        )
        .join("")
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

  socket.addEventListener("open", () => {
    setStatus("ready");
    renderEmptySubtitleState();
    renderEmptyFormattedState();
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "status") {
      setStatus(payload.state, payload.message);
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

btnStart.addEventListener("click", () => sendCommand("start"));
btnStop.addEventListener("click", () => sendCommand("stop"));
btnHistory.addEventListener("click", openHistoryPanel);
btnHistoryClose.addEventListener("click", closeHistoryPanel);
historyOverlay.addEventListener("click", (event) => {
  if (event.target === historyOverlay) {
    closeHistoryPanel();
  }
});

renderEmptySubtitleState();
renderEmptyFormattedState();
resetSummary();
connect();
