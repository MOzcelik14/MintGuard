"""Bounded, read-only home directory analysis and cache previews.

Never follows symbolic links; never deletes personal files.
"""
from __future__ import annotations

import heapq
import os
import stat
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from modules.maintenance import format_size


@dataclass
class FileEntry:
    path: str
    size: int


@dataclass
class StorageReport:
    scanned_files: int = 0
    scanned_bytes: int = 0
    largest_files: list[FileEntry] = field(default_factory=list)
    folders: list[FileEntry] = field(default_factory=list)
    truncated: bool = False
    errors: int = 0


def scan_home(
    home: Path | None = None,
    limit: int = 250_000,
    largest: int = 20,
    on_progress: Callable[[int], None] | None = None,
) -> StorageReport:
    """Size totals by top-level home folder; capped to limit I/O on huge trees."""
    root = Path(home) if home is not None else Path.home()
    result = StorageReport()
    if root.is_symlink() or not root.is_dir():
        result.errors += 1
        return result

    folder_totals: dict[str, int] = {}
    heap: list[tuple[int, str]] = []

    def error(_err: OSError) -> None:
        result.errors += 1

    for base, dirs, files in os.walk(root, followlinks=False, onerror=error):
        dirs[:] = [
            name for name in dirs
            if not (Path(base) / name).is_symlink()
            and not ((Path(base) / name).is_mount())
        ]
        for filename in files:
            p = Path(base) / filename
            try:
                item = p.lstat()
                if not stat.S_ISREG(item.st_mode):
                    continue
                if result.scanned_files >= limit:
                    result.truncated = True
                    break
                result.scanned_files += 1
                result.scanned_bytes += item.st_size
                rel = p.relative_to(root).parts
                key = rel[0] if len(rel) > 1 else "Ana dizindeki dosyalar"
                folder_totals[key] = folder_totals.get(key, 0) + item.st_size
                if largest > 0:
                    candidate = (item.st_size, str(p))
                    if len(heap) < largest:
                        heapq.heappush(heap, candidate)
                    elif candidate > heap[0]:
                        heapq.heapreplace(heap, candidate)
                if on_progress and result.scanned_files % 5000 == 0:
                    on_progress(result.scanned_files)
            except OSError:
                result.errors += 1
        if result.truncated:
            break
    result.largest_files = [
        FileEntry(path, size) for size, path in sorted(heap, reverse=True)
    ]
    result.folders = [
        FileEntry(name, size)
        for name, size in sorted(folder_totals.items(), key=lambda row: row[1], reverse=True)
    ]
    return result


def directory_bytes(path: Path, limit: int = 200_000) -> int:
    """Approximate regular-file bytes; skips links and caps filesystem walks."""
    if path.is_symlink() or not path.is_dir():
        return 0
    total = count = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            try:
                item = (Path(base) / name).lstat()
                if stat.S_ISREG(item.st_mode):
                    total += item.st_size
                    count += 1
            except OSError:
                continue
            if count >= limit:
                return total
    return total


def cache_preview(home: Path | None = None) -> list[FileEntry]:
    root = Path(home) if home is not None else Path.home()
    locations = {
        "Çöp kutusu": root / ".local/share/Trash/files",
        "Küçük resimler": root / ".cache/thumbnails",
        "Firefox": root / ".cache/mozilla/firefox",
        "Chromium": root / ".cache/chromium",
        "Google Chrome": root / ".cache/google-chrome",
        "Brave": root / ".cache/BraveSoftware",
        "Zen Browser": root / ".cache/zen",
    }
    return [
        FileEntry(name, directory_bytes(path))
        for name, path in locations.items() if path.is_dir() and not path.is_symlink()
    ]


def storage_lines(report: StorageReport, count: int = 12) -> str:
    lines = [f"Taranan: {report.scanned_files:,} dosya · {format_size(report.scanned_bytes)}"]
    if report.truncated:
        lines.append("⚠ Dosya sınırına ulaşıldı; sonuçlar eksik olabilir.")
    if report.errors:
        lines.append(f"⚠ {report.errors} erişim hatası (atlanmış).")
    lines.append("\nEn büyük klasörler (taranan dosyalara göre):")
    lines.extend(f"  {e.path}: {format_size(e.size)}" for e in report.folders[:count])
    lines.append("\nEn büyük dosyalar (otomatik silinmez):")
    lines.extend(f"  {format_size(e.size)}  {e.path}" for e in report.largest_files[:count])
    return "\n".join(lines)


@dataclass
class Volume:
    mountpoint: str
    device: str
    filesystem: str
    total: int
    used: int
    free: int


REAL_FILESYSTEMS = frozenset({
    "ext4", "ext3", "btrfs", "xfs", "f2fs", "vfat", "exfat",
    "ntfs", "ntfs3", "fuseblk", "zfs",
})


def mounted_volumes(mounts_file: Path = Path("/proc/mounts")) -> list[Volume]:
    """Read-only overview of locally mounted storage; skip pseudo filesystems."""
    try:
        text = mounts_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    seen: set[str] = set()
    volumes = []
    for row in text.splitlines():
        fields = row.split()
        if len(fields) < 3 or fields[2] not in REAL_FILESYSTEMS:
            continue
        device, path, fs = fields[:3]
        path = path.replace(r"\040", " ")
        if path in seen:
            continue
        seen.add(path)
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        volumes.append(Volume(
            path, device, fs, usage.total, usage.used, usage.free,
        ))
    if "/" not in seen:
        try:
            usage = shutil.disk_usage("/")
            volumes.insert(0, Volume(
                "/", "/", "root", usage.total, usage.used, usage.free,
            ))
        except OSError:
            pass
    return sorted(volumes, key=lambda item: (item.mountpoint != "/", item.mountpoint))


def volume_lines(volumes: list[Volume]) -> str:
    return "\n".join(
        f"{v.mountpoint} · {v.filesystem}\n  "
        f"{format_size(v.used)} / {format_size(v.total)}"
        f" ({format_size(v.free)} free)"
        for v in volumes
    ) or "—"
