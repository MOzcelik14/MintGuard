"""Local-only maintenance history and on-demand GitHub release checks."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from modules.system_info import VERSION

RELEASES_URL = "https://github.com/MOzcelik14/MintGuard/releases"
API_URL = "https://api.github.com/repos/MOzcelik14/MintGuard/releases/latest"


def history_path() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local/state"))
    return base / "mintguard" / "history.json"


def load_history(path: Path | None = None) -> list[dict]:
    file = path if path is not None else history_path()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        return data[-100:] if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def save_history(results: list, path: Path | None = None) -> None:
    file = path if path is not None else history_path()
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    entries = load_history(file)
    entries.append({
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "results": [{"action": r.name, "ok": r.ok, "detail": r.detail}
                    for r in results],
    })
    payload = json.dumps(entries[-100:], ensure_ascii=False, indent=2)
    # Create in user's state directory; do not write privileged logs or credentials.
    with file.open("w", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(payload)


def version_tuple(tag: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", tag)
    if not match:
        raise ValueError("Unrecognized release tag")
    return tuple(int(x or 0) for x in match.groups())


def check_releases() -> tuple[bool, str, str]:
    request = urllib.request.Request(
        API_URL, headers={"Accept": "application/vnd.github+json",
                          "User-Agent": f"MintGuard/{VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        data = json.load(response)
    tag = str(data["tag_name"])
    return version_tuple(tag) > version_tuple(VERSION), tag, RELEASES_URL
