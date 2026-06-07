const scenariosContainer = document.getElementById("setup-view-scenarios");
const pregenBadge = document.getElementById("setup-view-pregen");
const detailEl = document.getElementById("setup-view-detail");
const scenarioField = document.getElementById("setup-view-scenario");
const instructionField = document.getElementById("setup-view-instruction");
const sourceLangField = document.getElementById("setup-view-source-lang");
const targetLangField = document.getElementById("setup-view-target-lang");
const footerStatus = document.getElementById("setup-view-footer-status");
const glossaryPreview = document.getElementById("glossary-preview");
const glossaryCount = document.getElementById("glossary-count");

if (!isLiveSessionActive()) {
  window.location.replace("/setup.html");
}

function findScenarioByStoredScenario(scenarioText) {
  if (!scenarioText || !Array.isArray(DEMO_SCENARIOS)) {
    return null;
  }
  return DEMO_SCENARIOS.find((item) => item.scenario === scenarioText) || null;
}

function renderPreview(config) {
  const termMap = config?.term_map || {};
  const count = Object.keys(termMap).length;
  glossaryCount.textContent = `${count} 条`;
  renderTermMap(glossaryPreview, termMap);
}

function renderScenarioCards(matchedId) {
  if (!scenariosContainer || !Array.isArray(DEMO_SCENARIOS)) {
    return;
  }

  scenariosContainer.innerHTML = "";
  for (const scenario of DEMO_SCENARIOS) {
    const isSelected = Boolean(matchedId && scenario.id === matchedId);
    const termLabel =
      scenario.termCountHint > 0 ? `${scenario.termCountHint} 条预置术语` : "无预置术语";
    const card = document.createElement("div");
    card.className = "setup-accordion-tab setup-scenario-card";
    card.dataset.scenarioId = scenario.id;
    card.setAttribute("role", "listitem");
    if (isSelected) {
      card.classList.add("is-expanded", "is-selected");
    } else {
      card.classList.add("is-inactive");
    }
    card.innerHTML = `
      <span class="setup-accordion-tab-label">${escapeHtml(scenario.label)}</span>
      <div class="setup-accordion-tab-body">
        <div class="setup-accordion-tab-head">
          <span class="setup-accordion-tab-title">${escapeHtml(scenario.label)}</span>
          <span class="setup-accordion-tab-meta">${escapeHtml(termLabel)}</span>
        </div>
        <p class="setup-accordion-tab-desc">${escapeHtml(scenario.description || scenario.scenario)}</p>
      </div>
    `;
    scenariosContainer.appendChild(card);
  }
}

function renderDetailText(matched, config) {
  if (!detailEl) {
    return;
  }
  let text = "";
  if (matched?.detailText) {
    text = matched.detailText;
  } else if (config.scenario) {
    text = config.scenario;
  } else {
    text = "暂无场景说明";
  }
  detailEl.innerHTML = `<p>${escapeHtml(text)}</p>`;
}

function renderPregenBadge(matched, termCount) {
  if (!pregenBadge) {
    return;
  }
  const hasPregenScenario = Boolean(matched?.glossaryUrl);
  if (hasPregenScenario && termCount > 0) {
    pregenBadge.textContent = "✓ 已加载预置术语";
    pregenBadge.classList.add("is-loaded");
  } else {
    pregenBadge.textContent = "未加载预置术语";
    pregenBadge.classList.remove("is-loaded");
  }
}

function renderFooterStatus(config, termCount) {
  if (!footerStatus) {
    return;
  }
  if (!config || (!config.scenario && !config.instruction && termCount === 0)) {
    footerStatus.textContent = "本场尚未保存配置，配置不可修改";
    return;
  }
  if (termCount > 0) {
    footerStatus.textContent = `已加载 ${termCount} 条术语，配置不可修改`;
    return;
  }
  footerStatus.textContent = "本场无术语表，配置不可修改";
}

function resolveSourceLanguageLabel(sources, code) {
  const match = sources.find((item) => item.code === code);
  return match?.label || code || "—";
}

async function initSetupView() {
  const config = loadSessionConfig() || {};
  const matched = findScenarioByStoredScenario(config.scenario);
  const termCount = Object.keys(config.term_map || {}).length;

  renderScenarioCards(matched?.id);
  renderDetailText(matched, config);
  renderPregenBadge(matched, termCount);

  if (scenarioField) {
    scenarioField.textContent = (config.scenario || "").trim() || "—";
  }
  if (instructionField) {
    instructionField.textContent = (config.instruction || "").trim() || "—";
  }

  renderPreview(config);
  renderFooterStatus(config, termCount);

  try {
    const response = await fetch("/api/languages");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const sourceCode = config.source_language || getStoredSourceLanguage();
    if (sourceLangField) {
      sourceLangField.textContent = resolveSourceLanguageLabel(payload.sources || [], sourceCode);
    }
    if (targetLangField && payload.target?.label) {
      targetLangField.textContent = payload.target.label;
    }
  } catch (error) {
    if (sourceLangField) {
      sourceLangField.textContent = config.source_language || "—";
    }
    console.error("Failed to load languages for setup view:", error);
  }
}

initSetupView();
