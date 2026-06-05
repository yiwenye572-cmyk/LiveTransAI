const WS_URL = `ws://${window.location.hostname}:8765/stream`;

const statusBadge = document.getElementById("status-badge");
const subtitleList = document.getElementById("subtitle-list");
const metricsBar = document.getElementById("metrics-bar");
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");

let socket = null;
let sentenceCount = 0;

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

function renderEmptyState() {
  if (subtitleList.children.length === 0) {
    subtitleList.innerHTML = '<div class="empty-state">点击“开始翻译”，然后播放英文音频</div>';
  }
}

function appendSubtitle(payload) {
  const empty = subtitleList.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  const item = document.createElement("article");
  item.className = "subtitle-item";
  item.innerHTML = `
    <div class="subtitle-meta">
      <span>${payload.id}</span>
      <span>${payload.confidence || "fast"}</span>
    </div>
    <div class="subtitle-source">EN ${escapeHtml(payload.source || "")}</div>
    <div class="subtitle-translation">ZH ${escapeHtml(payload.translation || "")}</div>
  `;
  subtitleList.appendChild(item);
  subtitleList.scrollTop = subtitleList.scrollHeight;
}

function updateMetrics(payload) {
  sentenceCount = payload.sentence_count ?? sentenceCount;
  metricsBar.textContent = `已翻译: ${sentenceCount} 句`;
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function connect() {
  socket = new WebSocket(WS_URL);

  socket.addEventListener("open", () => {
    setStatus("ready");
    renderEmptyState();
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

renderEmptyState();
connect();
