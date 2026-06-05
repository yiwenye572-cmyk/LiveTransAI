# Development Notes

## AST Smoke Test

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

2. Copy `.env.example` to `.env` and fill `DOUBAO_API_KEY`.

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
