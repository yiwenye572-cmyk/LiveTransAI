const WS_URL = `ws://${window.location.hostname}:8765/stream`;

const connectionEl = document.getElementById("metrics-connection");
const emptyEl = document.getElementById("metrics-empty");
const sessionPanel = document.getElementById("metrics-session-panel");
const latencyPanel = document.getElementById("metrics-latency-panel");
const llmPanel = document.getElementById("metrics-llm-panel");

const STATUS_LABELS = {
  ready: "就绪",
  speaking: "翻译中",
  paused: "已暂停",
  finished: "已完成",
  error: "错误",
};

const SOURCE_LANGUAGE_LABELS = {
  en: "英语",
  ja: "日语",
  pt: "葡萄牙语",
  es: "西班牙语",
  id: "印尼语",
  de: "德语",
  fr: "法语",
  zh: "中文",
};

let sessionStatus = "ready";
let latestDetail = null;

function formatSeconds(value) {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${Number(value).toFixed(2)}s`;
}

function formatMs(value) {
  if (value == null || Number.isNaN(value) || Number(value) <= 0) {
    return "—";
  }
  return `${Math.round(Number(value))}ms`;
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) {
    return "0s";
  }
  const total = Math.floor(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins <= 0) {
    return `${secs}s`;
  }
  return `${mins}m ${secs}s`;
}

function languageLabel(code) {
  if (!code) {
    return "—";
  }
  return SOURCE_LANGUAGE_LABELS[code] || code;
}

function setConnectionState(connected) {
  if (!connectionEl) {
    return;
  }
  connectionEl.textContent = connected ? "已连接" : "未连接";
  connectionEl.classList.toggle("connected", connected);
}

function isSessionActive(status) {
  return status === "speaking" || status === "paused" || status === "finished";
}

function setPanelsVisible(active) {
  emptyEl.classList.toggle("hidden", active);
  sessionPanel.classList.toggle("hidden", !active);
  latencyPanel.classList.toggle("hidden", !active);
  llmPanel.classList.toggle("hidden", !active);
}

function renderLatencyRows(rows) {
  const tbody = document.getElementById("metric-latency-rows");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  const items = Array.isArray(rows) ? rows.slice().reverse() : [];
  if (items.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="4">暂无样本</td>';
    tbody.appendChild(row);
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${item.id || "—"}</td>
      <td>${formatMs(item.latency_ms)}</td>
      <td>${item.merge_count ?? "—"}</td>
      <td>${formatMs(item.wait_ms)}</td>
    `;
    tbody.appendChild(row);
  });
}

function renderMetricsDetail(detail, status) {
  if (!detail) {
    return;
  }
  latestDetail = { ...latestDetail, ...detail };
  sessionStatus = status || sessionStatus;
  const active = isSessionActive(sessionStatus);
  setPanelsVisible(active);
  if (!active) {
    return;
  }

  document.getElementById("metric-status").textContent = STATUS_LABELS[sessionStatus] || sessionStatus;
  document.getElementById("metric-elapsed").textContent = formatDuration(latestDetail.session_elapsed_sec);
  document.getElementById("metric-language").textContent =
    `${languageLabel(latestDetail.source_language)} → ${languageLabel(latestDetail.target_language || "zh")}`;
  document.getElementById("metric-fragments").textContent = latestDetail.ast_fragment_count ?? 0;
  document.getElementById("metric-corrections").textContent = latestDetail.correction_count ?? 0;

  document.getElementById("metric-latency-p50").textContent = formatSeconds(latestDetail.latency_p50);
  document.getElementById("metric-latency-p99").textContent = formatSeconds(latestDetail.latency_p99);
  renderLatencyRows(latestDetail.recent_display_latencies);

  document.getElementById("metric-correction-calls").textContent = latestDetail.correction_llm_calls ?? 0;
  document.getElementById("metric-summary-calls").textContent = latestDetail.summary_llm_calls ?? 0;
  document.getElementById("metric-glossary-calls").textContent = latestDetail.glossary_llm_calls ?? 0;
  document.getElementById("metric-llm-errors").textContent = latestDetail.llm_errors ?? 0;
  document.getElementById("metric-tokens-total").textContent = latestDetail.llm_tokens_total ?? 0;
  document.getElementById("metric-tokens-split").textContent =
    `${latestDetail.llm_tokens_prompt ?? 0} / ${latestDetail.llm_tokens_completion ?? 0}`;
  document.getElementById("metric-correction-latency").textContent = formatMs(
    latestDetail.correction_latency_ms_p50
  );
  document.getElementById("metric-summary-latency").textContent = formatMs(latestDetail.summary_latency_ms_p50);
}

function handleStatus(payload) {
  sessionStatus = payload.state || "ready";
  setPanelsVisible(isSessionActive(sessionStatus));
  if (isSessionActive(sessionStatus) && latestDetail) {
    renderMetricsDetail(latestDetail, sessionStatus);
  } else if (isSessionActive(sessionStatus)) {
    document.getElementById("metric-status").textContent = STATUS_LABELS[sessionStatus] || sessionStatus;
  }
}

function handleSessionSync(payload) {
  sessionStatus = payload.status || "ready";
  if (payload.metrics_detail) {
    renderMetricsDetail(payload.metrics_detail, sessionStatus);
    return;
  }
  if (payload.metrics) {
    renderMetricsDetail(payload.metrics, sessionStatus);
    return;
  }
  handleStatus({ state: sessionStatus });
}

function connect() {
  const socket = new WebSocket(WS_URL);

  socket.addEventListener("open", () => {
    setConnectionState(true);
  });

  socket.addEventListener("close", () => {
    setConnectionState(false);
    setTimeout(connect, 1500);
  });

  socket.addEventListener("error", () => {
    setConnectionState(false);
  });

  socket.addEventListener("message", (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (payload.type) {
      case "status":
        handleStatus(payload);
        break;
      case "session_sync":
        handleSessionSync(payload);
        break;
      case "metrics":
        renderMetricsDetail(payload, sessionStatus);
        break;
      case "metrics_detail":
        renderMetricsDetail(payload, sessionStatus);
        break;
      default:
        break;
    }
  });
}

connect();
