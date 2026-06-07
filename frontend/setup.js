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
const sourceLanguageSelect = document.getElementById("source-language-select");
const targetLanguageLabel = document.getElementById("target-language-label");
const btnEnterLive = document.getElementById("btn-enter-live");
const setupDemoPanel = document.getElementById("setup-demo-panel");
const setupDemoGrid = document.getElementById("setup-demo-grid");
const setupDemoLoadPregen = document.getElementById("setup-demo-load-pregen");

const params = new URLSearchParams(window.location.search);
const isViewMode = params.get("mode") === "view" || isLiveSessionActive();

let selectedDemoScenarioId = null;
let demoScenarioLoading = false;

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

function populateLanguageSelect(sources, defaultSource, storedSource) {
  if (!sourceLanguageSelect) {
    return;
  }
  sourceLanguageSelect.innerHTML = "";
  for (const item of sources) {
    const option = document.createElement("option");
    option.value = item.code;
    option.textContent = item.label;
    sourceLanguageSelect.appendChild(option);
  }
  const preferred = storedSource || defaultSource;
  if (sources.some((item) => item.code === preferred)) {
    sourceLanguageSelect.value = preferred;
  }
}

function persistLanguageSelection() {
  if (!sourceLanguageSelect) {
    return;
  }
  setStoredSourceLanguage(sourceLanguageSelect.value);
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
  btnEnterLive.hidden = true;
  if (sourceLanguageSelect) {
    sourceLanguageSelect.disabled = true;
  }
  if (setupDemoPanel) {
    setupDemoPanel.hidden = true;
  }
  setupHeaderAction.textContent = "返回同传";
  setupHeaderAction.href = "/";
  setupHeaderSubtitle.textContent = "本场会话配置（只读），查看后可返回当前同传会话";
  setupFormPanel.querySelector(".setup-actions").hidden = true;
}

function setSelectedDemoCard(scenarioId) {
  selectedDemoScenarioId = scenarioId;
  if (!setupDemoGrid) {
    return;
  }
  for (const card of setupDemoGrid.querySelectorAll(".setup-demo-card")) {
    card.classList.toggle("is-selected", card.dataset.scenarioId === scenarioId);
  }
}

function renderDemoCards() {
  if (!setupDemoGrid || !Array.isArray(DEMO_SCENARIOS)) {
    return;
  }

  setupDemoGrid.innerHTML = "";
  for (const scenario of DEMO_SCENARIOS) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "setup-demo-card";
    card.dataset.scenarioId = scenario.id;
    card.setAttribute("role", "option");
    card.innerHTML = `
      <p class="setup-demo-card-title">${escapeHtml(scenario.label)}</p>
      <p class="setup-demo-card-desc">${escapeHtml(scenario.description || scenario.scenario)}</p>
      <span class="setup-demo-card-meta">${scenario.termCountHint || 0} 条预置术语</span>
    `;
    card.addEventListener("click", () => {
      applyDemoScenario(scenario);
    });
    setupDemoGrid.appendChild(card);
  }
}

function syncSelectedDemoFromStorage(stored) {
  if (!stored?.scenario || !Array.isArray(DEMO_SCENARIOS)) {
    return;
  }
  const match = DEMO_SCENARIOS.find((item) => item.scenario === stored.scenario);
  if (match) {
    setSelectedDemoCard(match.id);
  }
}

async function loadPregenGlossary(scenarioDef) {
  const response = await fetch(scenarioDef.glossaryUrl);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const payload = await response.json();
  const termMap = payload?.term_map || {};
  if (!termMap || Object.keys(termMap).length === 0) {
    throw new Error("预置术语为空");
  }

  const sourceLanguage = scenarioDef.source_language || getStoredSourceLanguage();
  saveSessionConfig({
    ...payload,
    scenario: scenarioDef.scenario,
    instruction: scenarioDef.instruction,
    source_language: sourceLanguage,
  });
  renderPreview(payload);
  return Object.keys(termMap).length;
}

async function applyDemoScenario(scenarioDef) {
  if (isViewMode || demoScenarioLoading) {
    return;
  }

  scenarioInput.value = scenarioDef.scenario;
  instructionInput.value = scenarioDef.instruction;
  setSelectedDemoCard(scenarioDef.id);

  if (sourceLanguageSelect && scenarioDef.source_language) {
    sourceLanguageSelect.value = scenarioDef.source_language;
    persistLanguageSelection();
  }

  const loadPregen = setupDemoLoadPregen?.checked !== false;
  if (!loadPregen) {
    setStatus(`已填入「${scenarioDef.label}」场景描述，可生成术语表或进入同传。`);
    return;
  }

  demoScenarioLoading = true;
  setStatus(`正在加载「${scenarioDef.label}」预置术语…`);
  try {
    const count = await loadPregenGlossary(scenarioDef);
    setStatus(`已加载「${scenarioDef.label}」预置术语，共 ${count} 条，可进入同传。`);
  } catch (error) {
    setStatus(`预置术语加载失败：${error.message}。已填入场景描述。`, true);
  } finally {
    demoScenarioLoading = false;
  }
}

function restoreFormFromStorage() {
  const stored = loadSessionConfig();
  if (!stored) {
    if (isViewMode) {
      setStatus("本场尚未保存会话配置");
    }
    return;
  }
  if (stored.scenario) {
    scenarioInput.value = stored.scenario;
  }
  if (stored.instruction) {
    instructionInput.value = stored.instruction;
  }
  if (sourceLanguageSelect && stored.source_language) {
    sourceLanguageSelect.value = stored.source_language;
  }
  if (stored.term_map && Object.keys(stored.term_map).length > 0) {
    renderPreview(stored);
    syncSelectedDemoFromStorage(stored);
    if (isViewMode) {
      const sourceLabel =
        sourceLanguageSelect?.selectedOptions?.[0]?.textContent || stored.source_language;
      const scenario = (stored.scenario || "").trim();
      setStatus(
        scenario
          ? `${sourceLabel} → 中文 · ${scenario} · 共 ${Object.keys(stored.term_map).length} 条术语（只读）`
          : `${sourceLabel} → 中文 · 共 ${Object.keys(stored.term_map).length} 条术语（只读）`
      );
    } else {
      setStatus(`已加载上次生成的 ${Object.keys(stored.term_map).length} 条术语`);
    }
  } else if (isViewMode) {
    const sourceLabel =
      sourceLanguageSelect?.selectedOptions?.[0]?.textContent || stored.source_language || "英语";
    setStatus(`${sourceLabel} → 中文（只读）`);
  }
}

async function loadLanguages() {
  if (!sourceLanguageSelect) {
    return;
  }
  try {
    const response = await fetch("/api/languages");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const stored = loadSessionConfig();
    populateLanguageSelect(
      payload.sources || [],
      payload.default_source,
      stored?.source_language
    );
    if (targetLanguageLabel && payload.target?.label) {
      targetLanguageLabel.textContent = payload.target.label;
    }
    persistLanguageSelection();
  } catch (error) {
    setStatus("无法加载语言列表，请确认后端已启动。", true);
    console.error("Failed to load languages:", error);
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
      body: JSON.stringify({
        scenario,
        instruction,
        source_language: sourceLanguageSelect?.value || getStoredSourceLanguage(),
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }

    const existing = loadSessionConfig() || {};
    saveSessionConfig({
      ...existing,
      ...payload,
      source_language: sourceLanguageSelect?.value || getStoredSourceLanguage(),
    });
    renderPreview(payload);
    setStatus(`生成成功，共 ${payload.term_count || 0} 条术语。可进入同传。`);
  } catch (error) {
    setStatus(`生成失败：${error.message}`, true);
  } finally {
    btnGenerate.disabled = false;
  }
}

if (sourceLanguageSelect) {
  sourceLanguageSelect.addEventListener("change", () => {
    persistLanguageSelection();
  });
}

if (btnEnterLive) {
  btnEnterLive.addEventListener("click", () => {
    persistLanguageSelection();
  });
}

applyViewModeUi();
if (!isViewMode) {
  renderDemoCards();
}
btnGenerate.addEventListener("click", generateGlossary);
loadLanguages().then(() => {
  restoreFormFromStorage();
});
