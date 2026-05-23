from __future__ import annotations

from pathlib import Path


def normalize_keyword(value: str) -> str:
    return value.strip().lower()


def load_keywords_from_file(file_path: Path) -> list[str]:
    if not file_path.exists():
        return []
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    result: list[str] = []
    for raw_line in content.splitlines():
        line = normalize_keyword(raw_line)
        if line == "" or line.startswith("#"):
            continue
        result.append(line)
    return list(dict.fromkeys(result))


def load_keywords_from_directory(directory_path: Path) -> list[str]:
    if not directory_path.exists():
        return []
    keywords: list[str] = []
    for path in sorted(directory_path.glob("*.txt")):
        keywords.extend(load_keywords_from_file(path))
    return list(dict.fromkeys(keywords))
