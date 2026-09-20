"""Side-effect-free scanning and opt-in maintenance tasks for MintGuard."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

CACHE_ROOT = Path.home() / ".cache"
APT_ARCHIVES = Path("/var/cache/apt/archives")
TASK_LABELS = {
    "apt": "APT paket önbelleği",
    "cache": "Kullanıcı önbelleği",
    "journal": "Sistem günlükleri",
    "flatpak": "Kullanılmayan Flatpak bağımlılıkları",
}
JOURNAL_RE = re.compile(r"take up\s+([\d.]+)\s*([KMGTPE]?)(?:i?B)?", re.I)


@dataclass
class CacheStats:
    total_bytes: int = 0
    eligible_bytes: int = 0
    eligible_count: int = 0
    largest: list[tuple[str, int]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Snapshot:
    apt_bytes: int | None
    cache: CacheStats
    journal_bytes: int | None
    flatpak_available: bool
    disk_total: int
    disk_used: int
    disk_free: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    name: str
    ok: bool
    detail: str
    freed_bytes: int | None = None


def format_size(value: int | None) -> str:
    if value is None:
        return "Bilinmiyor"
    size = float(max(value, 0))
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if size < 1024 or suffix == "PiB":
            return f"{size:.0f} {suffix}" if suffix == "B" else f"{size:.1f} {suffix}"
        size /= 1024
    return "Bilinmiyor"


def scan_cache(
    root: Path = CACHE_ROOT, days: int = 7, now: float | None = None
) -> CacheStats:
    """Only count regular files; never follow symlinked folders or files."""
    stats = CacheStats()
    root = Path(root)
    if not root.exists():
        return stats
    if root.is_symlink() or not root.is_dir():
        stats.errors.append(f"Önbellek klasörü güvenli bir dizin değil: {root}")
        return stats

    cutoff = (time.time() if now is None else now) - days * 86400
    groups: dict[str, int] = {}

    def on_error(error: OSError) -> None:
        stats.errors.append(str(error))

    for base, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
        dirs[:] = [name for name in dirs if not (Path(base) / name).is_symlink()]
        for name in files:
            path = Path(base) / name
            try:
                item = path.lstat()
                if not stat.S_ISREG(item.st_mode):
                    continue
                stats.total_bytes += item.st_size
                relative = path.relative_to(root)
                group = relative.parts[0] if len(relative.parts) > 1 else "Diğer"
                groups[group] = groups.get(group, 0) + item.st_size
                if item.st_mtime < cutoff:
                    stats.eligible_bytes += item.st_size
                    stats.eligible_count += 1
            except OSError as error:
                stats.errors.append(str(error))
    stats.largest = sorted(groups.items(), key=lambda row: row[1], reverse=True)[:5]
    return stats


def clean_cache(
    root: Path = CACHE_ROOT, days: int = 7, now: float | None = None
) -> TaskResult:
    """Remove only regular files older than the chosen threshold.

    Symlinked cache roots, directories and entries are never traversed or removed.
    Empty directories are intentionally retained.
    """
    root = Path(root)
    if not root.exists():
        return TaskResult("cache", True, "Önbellek klasörü bulunamadı; işlem gerekmedi.", 0)
    if root.is_symlink() or not root.is_dir():
        return TaskResult("cache", False, "Güvenli olmayan önbellek dizini atlandı.")

    cutoff = (time.time() if now is None else now) - days * 86400
    removed = 0
    freed = 0
    failures = 0

    def on_error(_error: OSError) -> None:
        nonlocal failures
        failures += 1

    for base, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
        dirs[:] = [name for name in dirs if not (Path(base) / name).is_symlink()]
        for name in files:
            path = Path(base) / name
            try:
                item = path.lstat()
                if stat.S_ISREG(item.st_mode) and item.st_mtime < cutoff:
                    path.unlink()
                    removed += 1
                    freed += item.st_size
            except OSError:
                failures += 1

    detail = f"{removed} eski dosya silindi; yaklaşık {format_size(freed)} temizlendi."
    if failures:
        detail += f" {failures} dosya/dizine erişilemedi."
    return TaskResult("cache", failures == 0, detail, freed)


def apt_cache_bytes(root: Path = APT_ARCHIVES) -> int | None:
    try:
        return sum(
            file.lstat().st_size
            for file in root.iterdir()
            if file.suffix in (".deb", ".bin") and stat.S_ISREG(file.lstat().st_mode)
        )
    except OSError:
        return None


def parse_journal_bytes(output: str) -> int | None:
    match = JOURNAL_RE.search(output)
    if not match:
        return None
    exponent = "KMGTPE".find(match.group(2).upper()) + 1 if match.group(2) else 0
    return int(float(match.group(1)) * 1024**exponent)


def run_command(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Never invoke a shell; preserve diagnostics and use stable English CLI output."""
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        env=env, timeout=timeout, check=False,
    )


def journal_bytes() -> int | None:
    if not shutil.which("journalctl"):
        return None
    try:
        result = run_command(["journalctl", "--disk-usage", "--no-pager"], 30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    return parse_journal_bytes(result.stdout + "\n" + result.stderr)


def scan_system(cache_days: int = 7, cache_root: Path = CACHE_ROOT) -> Snapshot:
    cache = scan_cache(cache_root, cache_days)
    warnings = cache.errors[:3]
    try:
        usage = shutil.disk_usage(Path.home())
        total, used, free = usage.total, usage.used, usage.free
    except OSError as error:
        total = used = free = 0
        warnings.append(f"Disk okunamadı: {error}")
    apt = apt_cache_bytes()
    journal = journal_bytes()
    if apt is None:
        warnings.append("APT önbelleği okunamadı.")
    if journal is None:
        warnings.append("Journal disk kullanımı okunamadı.")
    return Snapshot(
        apt_bytes=apt,
        cache=cache,
        journal_bytes=journal,
        flatpak_available=bool(shutil.which("flatpak")),
        disk_total=total,
        disk_used=used,
        disk_free=free,
        warnings=warnings,
    )


def privileged(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    if not shutil.which("pkexec"):
        raise FileNotFoundError("pkexec bulunamadı; yönetici yetkisi alınamıyor.")
    return ["pkexec", *command]


def command_task(name: str, command: list[str], timeout: int = 1200) -> TaskResult:
    try:
        result = run_command(command, timeout)
    except subprocess.TimeoutExpired:
        return TaskResult(name, False, "İşlem zaman aşımına uğradı.")
    except OSError as error:
        return TaskResult(name, False, str(error))
    output = (result.stderr.strip() or result.stdout.strip())
    if result.returncode:
        return TaskResult(
            name, False,
            f"Çıkış kodu {result.returncode}: {output[-260:] or 'Ayrıntı verilmedi.'}",
        )
    return TaskResult(name, True, output[-200:] or "İşlem başarıyla tamamlandı.")


def run_maintenance(
    selected: Iterable[str],
    cache_days: int = 7,
    cache_root: Path = CACHE_ROOT,
    on_progress: Callable[[str], None] | None = None,
) -> list[TaskResult]:
    results: list[TaskResult] = []
    for name in selected:
        if on_progress:
            on_progress(TASK_LABELS.get(name, name))
        if name == "cache":
            results.append(clean_cache(cache_root, cache_days))
        elif name == "apt":
            if not shutil.which("apt"):
                results.append(TaskResult(name, False, "apt komutu bulunamadı."))
                continue
            before = apt_cache_bytes()
            try:
                result = command_task(name, privileged(["apt", "clean"]))
            except OSError as error:
                result = TaskResult(name, False, str(error))
            after = apt_cache_bytes()
            if result.ok and before is not None and after is not None:
                result.freed_bytes = max(before - after, 0)
                result.detail = f"APT önbelleği temizlendi; yaklaşık {format_size(result.freed_bytes)}."
            results.append(result)
        elif name == "journal":
            if not shutil.which("journalctl"):
                results.append(TaskResult(name, False, "journalctl bulunamadı."))
                continue
            before = journal_bytes()
            try:
                result = command_task(
                    name, privileged(["journalctl", "--vacuum-time=7d"]), 180,
                )
            except OSError as error:
                result = TaskResult(name, False, str(error))
            after = journal_bytes()
            if result.ok:
                result.freed_bytes = (
                    max(before - after, 0)
                    if before is not None and after is not None else None
                )
                result.detail = (
                    "7 günden eski arşiv günlükleri temizlendi. "
                    "Etkin günlükler korunur."
                )
                if result.freed_bytes is not None:
                    result.detail += f" Yaklaşık {format_size(result.freed_bytes)}."
            results.append(result)
        elif name == "flatpak":
            if not shutil.which("flatpak"):
                results.append(TaskResult(name, False, "flatpak bulunamadı."))
                continue
            for scope, title in (("--user", "Kullanıcı"), ("--system", "Sistem")):
                result = command_task(
                    name,
                    ["flatpak", "uninstall", "--unused", scope,
                     "--assumeyes", "--noninteractive"],
                )
                result.detail = f"{title}: {result.detail}"
                results.append(result)
        else:
            results.append(TaskResult(name, False, "Bilinmeyen bakım işlemi."))
    return results
