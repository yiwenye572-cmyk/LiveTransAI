import uvicorn

from backend.server.ws_server import create_app

app = create_app()


def main() -> None:
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
