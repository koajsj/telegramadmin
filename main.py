from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE_FILE = BASE_DIR / ".env.example"


def _build_env_content(example_path: Path, bot_token: str) -> str:
    if example_path.exists():
        lines = example_path.read_text(encoding="utf-8").splitlines()
        updated_lines = [
            f"BOT_TOKEN={bot_token}" if line.startswith("BOT_TOKEN=") else line
            for line in lines
        ]
        return "\n".join(updated_lines).strip() + "\n"

    return (
        f"BOT_TOKEN={bot_token}\n"
        "ACTION=mute\n"
        "AUTO_LOAD_TXT=true\n"
        "LEARNING_ENABLED=true\n"
        "RULE_ENABLE_USERNAME=true\n"
    )


def _ensure_env_file(base_dir: Path) -> None:
    if ENV_FILE.exists() or os.getenv("BOT_TOKEN"):
        return

    try:
        token = input("Telegram bot token: ").strip()
    except EOFError as exc:
        raise RuntimeError(
            "BOT_TOKEN is required. Set BOT_TOKEN or create .env before starting the bot."
        ) from exc

    if not token:
        raise RuntimeError("BOT_TOKEN is required.")

    env_file = base_dir / ".env"
    env_file.write_text(_build_env_content(ENV_EXAMPLE_FILE, token), encoding="utf-8")


_ensure_env_file(BASE_DIR)

from app.main import main  # noqa: E402


if __name__ == "__main__":
    main()
