# 豆包 AST API 速查（LiveTransAI 项目用）

> 来源：[`豆包同声传译api文档.md`](../豆包同声传译api文档.md)  
> 开发 AST 集成、调试鉴权/音频/字幕事件时优先读本文，再查官方文档细节。

**重要区分**

| 通道 | 协议 | 用途 |
|------|------|------|
| 本地后端 ↔ 豆包 AST | WebSocket + **Protobuf 二进制** | 音频上传、字幕回传 |
| 本地后端 ↔ 浏览器 | WebSocket + **JSON** | 字幕展示、控制命令 |

文档里的 JSON 示例是字段说明，**不是** AST 实际传输格式。

---

## 1. 连接与鉴权

| 项目 | 值 |
|------|-----|
| WebSocket 地址 | `wss://openspeech.bytedance.com/api/v4/ast/v2/translate` |
| 鉴权（新版控制台，**本项目使用**） | `X-Api-Key` + `X-Api-Resource-Id` |
| Resource ID | `volc.service_type.10053`（固定值） |
| 调试 | 响应头 `X-Tt-Logid`，出问题必记 |

`.env` 对应项：

```env
DOUBAO_API_KEY=...
DOUBAO_RESOURCE_ID=volc.service_type.10053
DOUBAO_AST_WS_URL=wss://openspeech.bytedance.com/api/v4/ast/v2/translate
AST_MODE=s2t
SOURCE_LANGUAGE=en
TARGET_LANGUAGE=zh
```

**不要用** `ast_python/ast_demo.py` 里的旧鉴权：`X-Api-App-Key` / `X-Api-Access-Key`。

---

## 2. 模式与语言（MVP）

| 参数 | 本项目值 | 说明 |
|------|----------|------|
| `mode` | `s2t` | 语音→文本，只要字幕 |
| `source_language` | `en` | 源语言 |
| `target_language` | `zh` | 目标语言 |

S2T 约束：

- 源语种、目标语种都必须指定
- 源语种或目标语种至少一个是中/英
- 常见代号：`zh` 中文、`en` 英文、`ja` 日语等
- 中英反转互译：两者都传 `zhen`

---

## 3. 音频参数（必须严格遵守）

| 参数 | 值 |
|------|-----|
| format | `wav` |
| codec | `raw`（PCM） |
| rate | `16000` Hz |
| bits | `16` |
| channel | `1`（单声道） |
| 分包 | 建议 **80ms 一包** |
| 每包字节 | 16000 × 0.08 × 2 = **2560 bytes** |

代码对应：`backend/config.py` → `ASTConfig`（`sample_rate=16000`, `chunk_ms=80`）。

---

## 4. 交互流程

```text
Client                                    AST Server
  │                                           │
  │── WebSocket 握手（X-Api-Key 等）──────────→│
  │── StartSession (event=100) ──────────────→│
  │←── SessionStarted (event=150) ────────────│
  │── TaskRequest (event=200) + PCM ─────────→│  ← 循环，每 80ms
  │←── SourceSubtitle* / TranslationSubtitle* │  ← 651/652 原文，654/655 译文
  │←── UsageResponse (154) ───────────────────│
  │── FinishSession (event=102) ─────────────→│
  │←── SessionFinished (152) ─────────────────│
```

**规则**：必须收到 `SessionStarted` 后再发音频包。

---

## 5. 发送端 Event

| Event | 编号 | 用途 |
|-------|------|------|
| StartSession | 100 | 建联 |
| TaskRequest | 200 | 发送 PCM 音频帧 |
| UpdateConfig | 201 | 会话中更新热词/术语（不能改语言/mode） |
| FinishSession | 102 | 结束会话 |

### StartSession 核心字段（JSON 示意）

```json
{
  "request_meta": { "session_id": "uuid" },
  "event": 100,
  "source_audio": {
    "format": "wav",
    "codec": "raw",
    "rate": 16000,
    "bits": 16,
    "channel": 1
  },
  "request": {
    "mode": "s2t",
    "source_language": "en",
    "target_language": "zh",
    "corpus": {
      "hot_words_list": ["federated learning", "GPU"],
      "glossary_list": {
        "federated learning": "联邦学习"
      }
    }
  }
}
```

When a glossary bundle is loaded from setup, LiveTransAI injects the same bundle into `corpus` at StartSession: `hot_words_list` for source recognition and `glossary_list` for AST translation hints. Correction still uses the same terms via DeepSeek prompts.

S2S 额外需要 `target_audio`（如 `format: pcm`, `rate: 24000`）及可选 `speaker_id`。

### TaskRequest 核心字段

```json
{
  "event": 200,
  "source_audio": {
    "data": "<PCM 二进制 bytes>"
  }
}
```

### FinishSession

```json
{ "event": 102 }
```

Application-layer **pause** does not send a Doubao pause event; the backend simply stops sending `TaskRequest` audio while keeping the session open. **Stop** uses `FinishSession` as above.

---

## 6. 接收端 Event（本项目关注）

| Event | 编号 | 本项目用法 |
|-------|------|------------|
| SessionStarted | 150 | 确认建联成功 |
| SourceSubtitleStart | 650 | 原文句开始 |
| SourceSubtitleResponse | 651 | 原文增量 → buffer |
| SourceSubtitleEnd | 652 | 一句原文结束 |
| TranslationSubtitleStart | 653 | 译文句开始 |
| TranslationSubtitleResponse | 654 | 译文增量 → buffer |
| **TranslationSubtitleEnd** | **655** | **整句译文 → 推前端** |
| UsageResponse | 154 | 计费 |
| SessionFinished | 152 | 正常结束 |
| SessionFailed | 153 | 失败 |
| AudioMuted | 250 | 静音检测 |
| TTSSentenceStart/Response/End | 350/352/351 | 仅 S2S |

字幕响应关键字段：

```json
{
  "event": 655,
  "sequence": 1,
  "text": "完整的一句译文",
  "start_time": 712,
  "end_time": 2152,
  "spk_chg": false
}
```

增量 → 整句示例：

```text
TranslationSubtitleResponse: "大家好"
TranslationSubtitleResponse: "大家好，今天"
TranslationSubtitleEnd:        "大家好，今天我想谈谈AI"
```

映射实现：`backend/controller/subtitle_mapper.py`（在 `TranslationSubtitleEnd` 产出前端 JSON）。

---

## 7. 本地前后端 JSON 协议

通道：`ws://localhost:8765/stream`（见 `backend/server/ws_server.py`）。

### 后端 → 前端

**字幕**

```json
{
  "type": "subtitle",
  "id": "s_001",
  "version": 1,
  "speaker": "speaker",
  "source": "英文原文",
  "translation": "中文译文",
  "confidence": "fast"
}
```

**状态**

```json
{ "type": "status", "state": "ready" }
{ "type": "status", "state": "speaking" }
{ "type": "status", "state": "finished" }
{ "type": "status", "state": "error", "message": "错误信息" }
```

**指标**

```json
{
  "type": "metrics",
  "sentence_count": 23,
  "correction_count": 0,
  "latency_p50": 0,
  "latency_p99": 0,
  "cost_estimate": 0
}
```

**字幕修正**（技术方案已设计，待实现）

```json
{
  "type": "correction",
  "target_id": "s_038",
  "base_version": 1,
  "new_version": 2,
  "old_translation": "旧译文",
  "new_translation": "新译文",
  "reason": "修正原因",
  "confidence": 0.92
}
```

### 前端 → 后端

```json
{ "type": "command", "action": "start" }
{ "type": "command", "action": "stop" }
```

`start` 可附带会话配置（来自 `/setup.html` 的 sessionStorage）：

```json
{
  "type": "command",
  "action": "start",
  "source_language": "ja",
  "audio": {
    "loopback_index": -100,
    "tts_output_id": "{speaker-id}"
  },
  "tts_enabled": true,
  "glossary": {
    "scenario": "...",
    "instruction": "...",
    "term_map": { "GPU": "图形处理器" }
  }
}
```

- `source_language`：S2S 源语言（`en` / `ja` / `pt` / `es` / `id` / `de` / `fr`）；目标语言固定 `zh`
- 后端广播 `language_route`：`{ source: {code, label}, target: {code:"zh", label:"中文"} }`

### 语言列表 API

```http
GET /api/languages
```

```json
{
  "sources": [{ "code": "en", "label": "英语" }],
  "target": { "code": "zh", "label": "中文" },
  "default_source": "en"
}
```

`.env` 中 `SOURCE_LANGUAGE` 仅为默认值；配置页选择会覆盖。

前端**不上传音频**；音频由本地后端 loopback 采集后直连豆包 AST。

---

## 8. 端到端数据流

```text
系统播放英文
    ↓ loopback（16k / 16bit / mono / 80ms）
本地 Python 后端
    ↓ Protobuf WebSocket → 豆包 AST
    ↓ TranslationSubtitleEnd
SubtitleMapper → JSON
    ↓ WebSocket → 浏览器
前端显示字幕
```

---

## 9. 常见坑

1. AST 走 Protobuf，不是 JSON。
2. 鉴权用新版 `X-Api-Key`，勿抄 `ast_demo.py`。
3. 音频必须 16kHz / 16bit / mono / PCM，80ms 分包。
4. 等 `SessionStarted` 再发 `TaskRequest`。
5. AST **没有** correction 事件；回溯修正是应用层能力。
6. Windows 下 loopback 采集线程需 COM 初始化（见 `backend/audio/capture.py`）。

---

## 10. 相关代码与文档

| 文件 | 说明 |
|------|------|
| `backend/config.py` | AST 环境变量与音频分包参数 |
| `backend/translator/ast_client.py` | Protobuf WebSocket 客户端（StartSession 注入 corpus） |
| `backend/translator/ast_corpus.py` | AST 热词/术语 corpus 数据结构 |
| `backend/glossary/hot_words.py` | 从术语表派生 hot_words_list |
| `backend/controller/subtitle_mapper.py` | AST 事件 → 前端 JSON |
| `backend/audio/capture.py` | 系统音频 loopback |
| `backend/server/ws_server.py` | 本地 WebSocket 服务 |
| `技术方案.md` | 完整架构与 correction 设计 |
| `豆包同声传译api文档.md` | 官方完整 API 文档 |

## 11. 文档里提到、但我们暂未用的
功能	说明
s2s 模式
语音→语音，会返回 TTS 音频（350/352/351）
speaker_id
S2S 公版音色
UpdateConfig (201)
会话中更新热词，不能切换语言
spk_chg
说话人切换检测

**已接入：** setup 页生成的术语 bundle 在 StartSession 时写入 `corpus.hot_words_list` 与 `corpus.glossary_list`（见 [`backend/translator/ast_client.py`](../backend/translator/ast_client.py)）。
