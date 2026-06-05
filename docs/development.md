# Development Notes

## AST Smoke Test

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

2. Copy `.env.example` to `.env` and fill `DOUBAO_API_KEY`.

3. Run the smoke test from the repository root:

```bash
python -m backend.smoke_ast --audio ast_python\test_audio.wav
```

The expected result is a `SessionStarted` event followed by source and translation subtitle events.
