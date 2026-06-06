const scenarioInput = document.getElementById("glossary-scenario");
const instructionInput = document.getElementById("glossary-instruction");
const btnGenerate = document.getElementById("btn-generate-glossary");
const setupStatus = document.getElementById("setup-status");
const glossaryPreview = document.getElementById("glossary-preview");
const glossaryCount = document.getElementById("glossary-count");
const setupHeaderAction = document.getElementById("setup-header-action");
const setupMain = document.getElementById("setup-main");
const setupFormPanel = document.getElementById("setup-form-panel");
const setupHeaderSubtitle = document.querySelector(".setup-header .subtitle");

const params = new URLSearchParams(window.location.search);
const isViewMode = params.get("mode") === "view" || isLiveSessionActive();

function setStatus(message, isError = false) {
  setupStatus.textContent = message;
  setupStatus.classList.toggle("setup-status-error", isError);
}

function renderPreview(data) {
  const termMap = data?.term_map || {};
  const count = Object.keys(termMap).length;
  glossaryCount.textContent = `${count} 条`;
  renderTermMap(glossaryPreview, termMap);
}

function applyViewModeUi() {
  if (!isViewMode) {
    return;
  }

  document.body.classList.add("setup-view-only");
  setupMain.classList.add("setup-main-view");
  scenarioInput.readOnly = true;
  instructionInput.readOnly = true;
  btnGenerate.hidden = true;
  document.getElementById("btn-enter-live").hidden = true;
  setupHeaderAction.textContent = "返回同传";
  setupHeaderAction.href = "/";
  setupHeaderSubtitle.textContent = "本场术语表（只读），查看后可返回当前同传会话";
  setupFormPanel.querySelector(".setup-actions").hidden = true;
}

function restoreFormFromStorage() {
  const stored = loadStoredGlossary();
  if (!stored) {
    if (isViewMode) {
      setStatus("本场尚未配置术语表");
    }
    return;
  }
  if (stored.scenario) {
    scenarioInput.value = stored.scenario;
  }
  if (stored.instruction) {
    instructionInput.value = stored.instruction;
  }
  if (stored.term_map && Object.keys(stored.term_map).length > 0) {
    renderPreview(stored);
    if (isViewMode) {
      const scenario = (stored.scenario || "").trim();
      setStatus(
        scenario
          ? `${scenario} · 共 ${Object.keys(stored.term_map).length} 条术语（只读）`
          : `共 ${Object.keys(stored.term_map).length} 条术语（只读）`
      );
    } else {
      setStatus(`已加载上次生成的 ${Object.keys(stored.term_map).length} 条术语`);
    }
  } else if (isViewMode) {
    setStatus("本场尚未配置术语表");
  }
}

async function generateGlossary() {
  if (isViewMode) {
    return;
  }

  const scenario = scenarioInput.value.trim();
  const instruction = instructionInput.value.trim();
  if (!scenario || !instruction) {
    setStatus("请填写业务场景和一句话说明", true);
    return;
  }

  btnGenerate.disabled = true;
  setStatus("正在生成术语表…");
  try {
    const response = await fetch("/api/glossary/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario, instruction }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }

    saveStoredGlossary(payload);
    renderPreview(payload);
    setStatus(`生成成功，共 ${payload.term_count || 0} 条术语。可进入同传。`);
  } catch (error) {
    setStatus(`生成失败：${error.message}`, true);
  } finally {
    btnGenerate.disabled = false;
  }
}

applyViewModeUi();
btnGenerate.addEventListener("click", generateGlossary);
restoreFormFromStorage();
