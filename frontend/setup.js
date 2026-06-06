const scenarioInput = document.getElementById("glossary-scenario");
const instructionInput = document.getElementById("glossary-instruction");
const btnGenerate = document.getElementById("btn-generate-glossary");
const setupStatus = document.getElementById("setup-status");
const glossaryPreview = document.getElementById("glossary-preview");
const glossaryCount = document.getElementById("glossary-count");

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

function restoreFormFromStorage() {
  const stored = loadStoredGlossary();
  if (!stored) {
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
    setStatus(`已加载上次生成的 ${Object.keys(stored.term_map).length} 条术语`);
  }
}

async function generateGlossary() {
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

btnGenerate.addEventListener("click", generateGlossary);
restoreFormFromStorage();
