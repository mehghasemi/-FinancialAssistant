from __future__ import annotations

import threading
import webbrowser

import uvicorn

from .main import app


HOST = "127.0.0.1"
PORT = 8000


def open_application() -> None:
    webbrowser.open_new_tab(f"http://{HOST}:{PORT}")


def main() -> None:
    threading.Timer(0.8, open_application).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=None, access_log=False)


if __name__ == "__main__":
    main()
