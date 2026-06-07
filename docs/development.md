# Development Notes

AST 集成参数、Event 编号、Protobuf/JSON 协议速查见 [`docs/ast-api-cheatsheet.md`](ast-api-cheatsheet.md)。

## AST Smoke Test

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

2. Copy `.env.example` to `.env` and fill `DOUBAO_API_KEY`. For async correction, also set `DEEPSEEK_API_KEY` from [DeepSeek Platform](https://platform.deepseek.com/api_keys).

3. Run the smoke test from the repository root:

```bash
python -m backend.smoke_ast --audio ast_python\test_audio.wav
```

The expected result is a `SessionStarted` event followed by source and translation subtitle events.

## Audio Capture Smoke Test

List local audio devices and the selected capture source:

```bash
python -m backend.smoke_audio --list
```

Record a short loopback test file:

```bash
python -m backend.smoke_audio --record --seconds 5 --out tmp\loopback_test.wav
```

On Windows, the selected source should usually be a `soundcard` loopback device for the active speaker.

If multiple devices are available, pass the selected index explicitly:

```bash
python -m backend.smoke_audio --record --device-index -100 --seconds 5 --out tmp\loopback_test.wav
```

The command prints `rms` and `peak` after recording. If `peak=0`, the capture opened successfully but received silence; check system mute, output device, and whether audio is actively playing.

Send the recorded file to AST:

```bash
python -m backend.smoke_ast --audio tmp\loopback_test.wav
```

## Realtime AST Stream

Stream loopback audio directly to AST without writing a wav file:

```bash
python -m backend.smoke_realtime_ast --seconds 10
```

While it runs, play English audio on your computer. You should see subtitle events printed in real time.

For automated testing without manual playback:

```bash
python -m backend.smoke_realtime_ast --seconds 8 --play-sample
```

Override the capture device if needed:

```bash
python -m backend.smoke_realtime_ast --device-index -100 --seconds 10
```

## Web UI

Start the backend server:

```bash
python -m backend.main
```

Open the browser at the landing page:

```text
http://127.0.0.1:8765/
```

From there:

- **配置会话** → `/setup.html` (optional glossary and scenario)
- **直接进入同传** → `/live.html`

On the live page, click **开始翻译**, then play English audio on your computer. Subtitles should appear in real time. For split-screen viewing (e.g. video on one half of the monitor), use **专注字幕** in the subtitle panel to hide the summary column and device settings while keeping enlarged bilingual subtitles (EN source + ZH translation) and the voice/start/pause/stop controls.

While a session is active (`livetransai_live_active` in sessionStorage), **会话配置** on the live page opens `/setup-view.html`: a read-only snapshot with the same left-config / right-preview layout as `/setup.html`, but all controls are static text (scenario cards, languages, glossary preview). Use **← 返回同传** to return without stopping the session. If you open `/setup-view.html` before a session starts, you are redirected to `/setup.html`. Use **开始新翻译** on the live page to end the session and start over from the landing page.

If you generate a glossary on `/setup.html` before starting, the same bundle is sent to Doubao AST at session start (`corpus.hot_words_list` for source recognition and `corpus.glossary_list` for translation hints) and to DeepSeek correction prompts (`static_glossary`).

### Demo Scenarios (答辩预设)

Recommended demo flow (under 30 seconds):

1. Open `http://127.0.0.1:8765/` → **配置会话**
2. On `/setup.html`, click the **网课** tab (default on first visit) → **进入同传**
3. On `/live.html`, click **开始翻译** → play English course audio

Four built-in scenarios are available as an accordion: **通用场景**, **学术会议**, **商务洽谈**, and **网课**. Scenario card backgrounds use local WebP images under `frontend/demo-scenarios/images/`. Click a tab to expand it; the description box below updates with template details. With **一并加载预置术语** checked (default for the three preset scenarios), pre-generated glossary JSON loads instantly without calling the LLM. **通用场景** has no preset JSON—fill the scenario fields and use **生成术语表**, or enter live without a glossary.

Quick path: landing page → **直接进入同传** → **开始翻译** (no glossary required).

To verify the read-only config page: start a session on `/live.html`, then open **会话配置** → `/setup-view.html`. Confirm scenario cards, languages, and glossary are static; click **← 返回同传** to resume without stopping the session.

### Pause / Resume / Stop

Doubao AST has no native pause API. LiveTransAI implements pause at the application layer:

- **Pause**: loopback capture switches to **silence chunks** at the same 80ms cadence (AST session stays alive; no new speech is translated).
- **Resume**: real loopback audio is sent again on the same AST session.
- **Stop**: send `FinishSession` (102), persist the session, return to ready.

Use **Pause** during breaks; use **Stop** when the talk is over or if paused for a long time (AST may time out on silence).

## Async Correction (DeepSeek)

The Web UI uses a dual-channel pipeline:

- **Fast path**: Doubao AST subtitles appear immediately.
- **Summary path**: Every 5 new sentences, an async DeepSeek call incrementally updates a running session summary (`topic`, `term_map`, `bullet_points`).
- **Correction path**: After at least 3 sentences and 8 seconds between runs, another async DeepSeek call reviews recent translations using the latest available summary snapshot.

Summary and correction run in parallel (`asyncio.create_task`) and do not block the fast path.

If `DEEPSEEK_API_KEY` is missing, both slow paths are skipped.

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

Corrections with `confidence < 0.85` are dropped on the backend.
