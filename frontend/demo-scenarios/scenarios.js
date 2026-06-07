const DEMO_SCENARIOS = [
  {
    id: "general",
    label: "通用场景",
    description: "演讲 / 分享 / 日常口译",
    scenario: "通用外语演讲或分享",
    instruction: "用语自然流畅，专有名词保持前后一致",
    source_language: "en",
    glossaryUrl: null,
    termCountHint: 0,
    detailText:
      "适用于无明确行业标签的英语内容，如公开演讲、播客片段或日常分享。不会自动加载预置术语，可在下方填写场景说明后手动生成术语表，或不带术语直接进入同传。",
  },
  {
    id: "academic",
    label: "学术会议",
    description: "论文报告 · 学术严谨译法",
    scenario: "国际 AI 学术会议",
    instruction: "论文报告与 Q&A，术语用大陆学术常用译法，保持严谨统一",
    source_language: "en",
    glossaryUrl: "/demo-scenarios/academic-conference.json",
    termCountHint: 18,
    detailText:
      "当前模板为「国际 AI 学术会议」。预置 18 条学术常用英中术语（如 federated learning、ablation study），适合论文报告与 Q&A 答辩演示，识别与翻译更稳定。",
  },
  {
    id: "business",
    label: "商务洽谈",
    description: "合同报价 · 正式商务口吻",
    scenario: "跨国商务洽谈",
    instruction: "合同与报价讨论，用语正式简洁，采用大陆商务常用译法",
    source_language: "en",
    glossaryUrl: "/demo-scenarios/business-negotiation.json",
    termCountHint: 18,
    detailText:
      "当前模板为「跨国商务洽谈」。预置 ROI、deliverables、due diligence 等 18 条商务术语，译法偏正式简洁，适合合同与报价类对话演示。",
  },
  {
    id: "online-course",
    label: "网课",
    description: "在线课程 · 通俗易懂",
    scenario: "英语在线课程",
    instruction: "计算机或通识课程讲解，术语通俗易懂，适合自学跟听",
    source_language: "en",
    glossaryUrl: "/demo-scenarios/online-course.json",
    termCountHint: 18,
    detailText:
      "当前模板为「英语在线课程」。预置 deep learning、syllabus、office hours 等 18 条网课高频词，译法通俗易懂，推荐作为 30 秒答辩 Demo 默认场景。",
  },
];
