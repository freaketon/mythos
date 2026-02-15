from __future__ import annotations

import os
import uvicorn

from src.env import load_dotenv


def main() -> None:
    load_dotenv()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.web_app:create_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    main()
