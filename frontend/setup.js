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
const setupGlossaryBlock = document.getElementById("setup-glossary-block");
const setupAccordionTabs = document.getElementById("setup-accordion-tabs");
const setupDemoLoadPregen = document.getElementById("setup-demo-load-pregen");
const setupScenarioDesc = document.getElementById("setup-scenario-desc");
const setupGeneralFields = document.getElementById("setup-general-fields");
const setupPregenOption = document.querySelector(".setup-pregen-option");

const params = new URLSearchParams(window.location.search);
const isViewMode = params.get("mode") === "view" || isLiveSessionActive();

const SCENARIO_DESC_PLACEHOLDER = "点选上方场景卡片查看说明";
const DEFAULT_SCENARIO_ID = "online-course";

let expandedScenarioId = null;
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

function findScenarioById(id) {
  return DEMO_SCENARIOS?.find((item) => item.id === id) || null;
}

function findScenarioByStoredScenario(scenarioText) {
  if (!scenarioText || !Array.isArray(DEMO_SCENARIOS)) {
    return null;
  }
  return DEMO_SCENARIOS.find((item) => item.scenario === scenarioText) || null;
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
  if (scenarioInput) {
    scenarioInput.readOnly = true;
  }
  if (instructionInput) {
    instructionInput.readOnly = true;
  }
  btnGenerate.hidden = true;
  btnEnterLive.hidden = true;
  if (sourceLanguageSelect) {
    sourceLanguageSelect.disabled = true;
  }
  if (setupGlossaryBlock) {
    setupGlossaryBlock.hidden = true;
  }
  setupHeaderAction.textContent = "返回同传";
  setupHeaderAction.href = "/live.html";
  setupHeaderSubtitle.textContent = "本场会话配置（只读），查看后可返回当前同传会话";
  setupFormPanel.querySelector(".setup-actions").hidden = true;
}

function updateGeneralFieldsVisibility(scenarioDef) {
  if (!setupGeneralFields) {
    return;
  }
  const isGeneral = scenarioDef?.id === "general";
  setupGeneralFields.hidden = !isGeneral;
}

function updatePregenCheckbox(scenarioDef) {
  if (!setupDemoLoadPregen) {
    return;
  }
  const hasPregen = Boolean(scenarioDef?.glossaryUrl);
  setupDemoLoadPregen.disabled = !hasPregen;
  if (setupPregenOption) {
    setupPregenOption.classList.toggle("is-disabled", !hasPregen);
  }
}

function renderScenarioDesc(scenarioDef) {
  if (!setupScenarioDesc) {
    return;
  }
  setupScenarioDesc.classList.remove("is-expanded");
  if (!scenarioDef) {
    setupScenarioDesc.innerHTML = `<p class="setup-scenario-desc-placeholder">${SCENARIO_DESC_PLACEHOLDER}</p>`;
    return;
  }
  setupScenarioDesc.innerHTML = `<p>${escapeHtml(scenarioDef.detailText || scenarioDef.description || "")}</p>`;
}

function updateAccordionTabs(scenarioDef) {
  if (!setupAccordionTabs) {
    return;
  }
  for (const tab of setupAccordionTabs.querySelectorAll(".setup-accordion-tab")) {
    const isExpanded = Boolean(scenarioDef && tab.dataset.scenarioId === scenarioDef.id);
    tab.classList.toggle("is-expanded", isExpanded);
    tab.setAttribute("aria-selected", isExpanded ? "true" : "false");
  }
}

function setTabLoading(scenarioId, loading) {
  if (!setupAccordionTabs) {
    return;
  }
  for (const tab of setupAccordionTabs.querySelectorAll(".setup-accordion-tab")) {
    if (!scenarioId || tab.dataset.scenarioId === scenarioId) {
      tab.classList.toggle("is-loading", loading);
    }
  }
}

function expandScenario(scenarioDef, { apply = false } = {}) {
  expandedScenarioId = scenarioDef?.id || null;
  updateAccordionTabs(scenarioDef);
  renderScenarioDesc(scenarioDef);
  if (scenarioDef) {
    updateGeneralFieldsVisibility(scenarioDef);
    updatePregenCheckbox(scenarioDef);
  }
  if (apply && scenarioDef) {
    applyDemoScenario(scenarioDef);
  }
}

function collapseScenario() {
  expandedScenarioId = null;
  updateAccordionTabs(null);
  renderScenarioDesc(null);
  if (setupGeneralFields) {
    setupGeneralFields.hidden = true;
  }
  if (setupDemoLoadPregen) {
    setupDemoLoadPregen.disabled = false;
  }
  if (setupPregenOption) {
    setupPregenOption.classList.remove("is-disabled");
  }
}

function onScenarioTabClick(scenarioDef) {
  if (demoScenarioLoading) {
    return;
  }
  if (expandedScenarioId === scenarioDef.id) {
    collapseScenario();
    return;
  }
  expandScenario(scenarioDef, { apply: true });
}

function initScenarioAccordion() {
  if (!setupAccordionTabs || !Array.isArray(DEMO_SCENARIOS)) {
    return;
  }

  setupAccordionTabs.innerHTML = "";
  for (const scenario of DEMO_SCENARIOS) {
    const termLabel =
      scenario.termCountHint > 0 ? `${scenario.termCountHint} 条预置术语` : "无预置术语";
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "setup-accordion-tab";
    tab.dataset.scenarioId = scenario.id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", "false");
    tab.innerHTML = `
      <span class="setup-accordion-tab-label">${escapeHtml(scenario.label)}</span>
      <div class="setup-accordion-tab-body">
        <div class="setup-accordion-tab-head">
          <span class="setup-accordion-tab-title">${escapeHtml(scenario.label)}</span>
          <span class="setup-accordion-tab-meta">${escapeHtml(termLabel)}</span>
        </div>
        <p class="setup-accordion-tab-desc">${escapeHtml(scenario.description || scenario.scenario)}</p>
      </div>
    `;
    tab.addEventListener("click", () => onScenarioTabClick(scenario));
    setupAccordionTabs.appendChild(tab);
  }

  if (setupScenarioDesc) {
    setupScenarioDesc.addEventListener("click", () => {
      if (!expandedScenarioId) {
        return;
      }
      setupScenarioDesc.classList.toggle("is-expanded");
    });
    setupScenarioDesc.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setupScenarioDesc.click();
      }
    });
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

function persistScenarioFields(scenarioDef) {
  if (scenarioInput) {
    scenarioInput.value = scenarioDef.scenario;
  }
  if (instructionInput) {
    instructionInput.value = scenarioDef.instruction;
  }
  if (sourceLanguageSelect && scenarioDef.source_language) {
    sourceLanguageSelect.value = scenarioDef.source_language;
    persistLanguageSelection();
  }

  const existing = loadSessionConfig() || {};
  saveSessionConfig({
    ...existing,
    scenario: scenarioDef.scenario,
    instruction: scenarioDef.instruction,
    source_language: scenarioDef.source_language || getStoredSourceLanguage(),
  });
}

async function applyDemoScenario(scenarioDef) {
  if (isViewMode || demoScenarioLoading) {
    return;
  }

  persistScenarioFields(scenarioDef);
  updateGeneralFieldsVisibility(scenarioDef);
  updatePregenCheckbox(scenarioDef);

  const hasPregen = Boolean(scenarioDef.glossaryUrl);
  const loadPregen = hasPregen && setupDemoLoadPregen?.checked !== false;

  if (!loadPregen) {
    if (scenarioDef.id === "general") {
      setStatus(`已选择「${scenarioDef.label}」，请填写场景说明或生成术语表。`);
    } else {
      setStatus(`已填入「${scenarioDef.label}」场景描述，可生成术语表或进入同传。`);
    }
    return;
  }

  demoScenarioLoading = true;
  setTabLoading(scenarioDef.id, true);
  setStatus(`正在加载「${scenarioDef.label}」预置术语…`);
  try {
    const count = await loadPregenGlossary(scenarioDef);
    setStatus(`已加载「${scenarioDef.label}」预置术语，共 ${count} 条，可进入同传。`);
  } catch (error) {
    setStatus(`预置术语加载失败：${error.message}。已填入场景描述。`, true);
  } finally {
    demoScenarioLoading = false;
    setTabLoading(null, false);
  }
}

function restoreFormFromStorage() {
  const stored = loadSessionConfig();
  if (!stored) {
    if (isViewMode) {
      setStatus("本场尚未保存会话配置");
      return;
    }
    const defaultScenario = findScenarioById(DEFAULT_SCENARIO_ID);
    if (defaultScenario) {
      expandScenario(defaultScenario, { apply: true });
    }
    return;
  }

  if (stored.scenario && scenarioInput) {
    scenarioInput.value = stored.scenario;
  }
  if (stored.instruction && instructionInput) {
    instructionInput.value = stored.instruction;
  }
  if (sourceLanguageSelect && stored.source_language) {
    sourceLanguageSelect.value = stored.source_language;
  }

  const matchedScenario = findScenarioByStoredScenario(stored.scenario);
  if (!isViewMode) {
    if (matchedScenario) {
      expandScenario(matchedScenario, { apply: false });
    } else {
      collapseScenario();
    }
  }

  if (stored.term_map && Object.keys(stored.term_map).length > 0) {
    renderPreview(stored);
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
      setStatus(`已加载上次保存的 ${Object.keys(stored.term_map).length} 条术语`);
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

  const scenario = scenarioInput?.value.trim() || "";
  const instruction = instructionInput?.value.trim() || "";
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
  initScenarioAccordion();
  renderScenarioDesc(null);
}
btnGenerate.addEventListener("click", generateGlossary);
loadLanguages().then(() => {
  restoreFormFromStorage();
});
