"""Read-only Linux hardware and operating-system metrics (no extra dependencies)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from modules.maintenance import format_size

VERSION = "2.0.0"


@dataclass
class SystemSnapshot:
    distro: str
    kernel: str
    uptime_seconds: int
    cpu_name: str
    cpu_percent: float
    memory_total: int
    memory_used: int
    swap_total: int
    swap_used: int
    zram_total: int
    zram_used: int
    battery_percent: int | None
    battery_health: int | None
    battery_charging: str
    nvidia: str
    root_total: int
    root_used: int


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def meminfo(text: str) -> dict[str, int]:
    data = {}
    for row in text.splitlines():
        match = re.match(r"^(\w+):\s+(\d+)\s+kB", row)
        if match:
            data[match.group(1)] = int(match.group(2)) * 1024
    return data


def cpu_ticks(text: str) -> tuple[int, int]:
    line = text.splitlines()[0] if text else ""
    fields = line.split()
    if not fields or fields[0] != "cpu":
        return (0, 0)
    try:
        ticks = [int(v) for v in fields[1:]]
    except ValueError:
        return (0, 0)
    idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
    return (sum(ticks), idle)


def cpu_usage(before: tuple[int, int], after: tuple[int, int]) -> float:
    total = after[0] - before[0]
    idle = after[1] - before[1]
    return round(max(0, min(100, (1 - idle / total) * 100)), 1) if total > 0 else 0.0


def cpu_name() -> str:
    for line in read_text(Path("/proc/cpuinfo")).splitlines():
        if line.startswith("model name"):
            return line.partition(":")[2].strip()
    return "Bilinmiyor"


def distro_name() -> str:
    for line in read_text(Path("/etc/os-release")).splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.partition("=")[2].strip().strip('"')
    return "Linux"


def zram_info(sys_block: Path = Path("/sys/block")) -> tuple[int, int]:
    total = used = 0
    try:
        devices = list(sys_block.glob("zram*"))
    except OSError:
        return 0, 0
    for device in devices:
        try:
            total += int(read_text(device / "disksize") or 0)
            values = read_text(device / "mm_stat").split()
            if values:
                used += int(values[0])  # uncompressed data in RAM-backed swap
        except ValueError:
            continue
    return total, used


def battery_info(root: Path = Path("/sys/class/power_supply")) -> tuple[int | None, int | None, str]:
    try:
        batteries = [p for p in root.iterdir() if read_text(p / "type") == "Battery"]
    except OSError:
        return None, None, "Bilinmiyor"
    if not batteries:
        return None, None, "Pil bulunamadı"
    bat = batteries[0]
    capacity = read_text(bat / "capacity")
    level = int(capacity) if capacity.isdecimal() else None
    health = None
    for stem in ("energy", "charge"):
        full = read_text(bat / f"{stem}_full")
        design = read_text(bat / f"{stem}_full_design")
        if full.isdecimal() and design.isdecimal() and int(design):
            health = min(100, round(int(full) / int(design) * 100))
            break
    return level, health, read_text(bat / "status") or "Bilinmiyor"


def nvidia_driver() -> str:
    if not shutil.which("nvidia-smi"):
        return "Bulunamadı"
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version,name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        return result.stdout.strip().splitlines()[0][:120] if result.returncode == 0 else "Kullanılamıyor"
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "Kullanılamıyor"


def snapshot(sample_seconds: float = 0.12) -> SystemSnapshot:
    before = cpu_ticks(read_text(Path("/proc/stat")))
    time.sleep(sample_seconds)
    after = cpu_ticks(read_text(Path("/proc/stat")))
    m = meminfo(read_text(Path("/proc/meminfo")))
    mem_total = m.get("MemTotal", 0)
    available = m.get("MemAvailable", m.get("MemFree", 0))
    swap_total = m.get("SwapTotal", 0)
    z_total, z_used = zram_info()
    battery, health, charging = battery_info()
    try:
        space = shutil.disk_usage("/")
        disk_total, disk_used = space.total, space.used
    except OSError:
        disk_total = disk_used = 0
    try:
        uptime = int(float(read_text(Path("/proc/uptime")).split()[0]))
    except (ValueError, IndexError):
        uptime = 0
    return SystemSnapshot(
        distro=distro_name(), kernel=os.uname().release, uptime_seconds=uptime,
        cpu_name=cpu_name(), cpu_percent=cpu_usage(before, after),
        memory_total=mem_total, memory_used=max(0, mem_total - available),
        swap_total=swap_total, swap_used=max(0, swap_total - m.get("SwapFree", 0)),
        zram_total=z_total, zram_used=z_used, battery_percent=battery,
        battery_health=health, battery_charging=charging, nvidia=nvidia_driver(),
        root_total=disk_total, root_used=disk_used,
    )


def uptime_display(seconds: int) -> str:
    days, remainder = divmod(max(seconds, 0), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return f"{days}g {hours}sa {minutes}dk" if days else f"{hours}sa {minutes}dk"


def storage_display(used: int, total: int) -> str:
    return f"{format_size(used)} / {format_size(total)}"
