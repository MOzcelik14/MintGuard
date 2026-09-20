"""Additional opt-in maintenance actions and preview-only package suggestions."""
from __future__ import annotations

import shutil
from pathlib import Path

from modules.maintenance import TaskResult, clean_cache, run_command


def unused_apt_preview() -> str:
    """Read-only suggestion, never invokes apt autoremove for real."""
    if not shutil.which("apt-get"):
        return "apt-get bulunamadı."
    try:
        result = run_command(["apt-get", "-s", "autoremove"], timeout=30)
    except (OSError, TimeoutError) as error:
        return f"APT kontrolü başarısız: {error}"
    if result.returncode:
        return f"APT kontrolü başarısız: {result.stderr.strip()[-250:]}"
    packages = [
        row.split()[1]
        for row in result.stdout.splitlines()
        if row.startswith("Remv ") and len(row.split()) > 1
    ]
    return (
        f"APT kaldırılabilir olarak {len(packages)} paket öneriyor:\n"
        + "\n".join(packages[:60])
        + ("\n…" if len(packages) > 60 else "")
        if packages else "APT tarafından kaldırılabilir bağımlılık önerilmedi."
    )


def run_extra(name: str, days: int) -> TaskResult:
    if name == "thumbs":
        result = clean_cache(Path.home() / ".cache/thumbnails", days)
        result.name = "thumbs"
        return result
    if name == "trash":
        if not shutil.which("gio"):
            return TaskResult("trash", False, "gio bulunamadı.")
        try:
            result = run_command(["gio", "trash", "--empty"], timeout=180)
        except (OSError, TimeoutError) as error:
            return TaskResult("trash", False, str(error))
        if result.returncode:
            return TaskResult("trash", False, result.stderr.strip()[-300:] or "Çöp kutusu boşaltılamadı.")
        return TaskResult("trash", True, "Çöp kutusu boşaltıldı (geri alınamaz).")
    return TaskResult(name, False, "Bilinmeyen işlem.")
