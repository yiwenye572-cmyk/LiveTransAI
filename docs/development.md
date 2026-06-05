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

Open the browser:

```text
http://127.0.0.1:8765
```

Click **开始翻译**, then play English audio on your computer. Subtitles should appear in the page in real time.

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
