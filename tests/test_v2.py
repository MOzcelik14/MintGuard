"""Read-only system, storage, release and packaging regression tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.history import load_history, save_history, version_tuple
from modules.maintenance import TaskResult
from modules.storage import cache_preview, scan_home
from modules.system_info import (
    battery_info, cpu_ticks, cpu_usage, meminfo, uptime_display, zram_info,
)


class HealthTests(unittest.TestCase):
    def test_meminfo_units(self):
        self.assertEqual(meminfo("MemTotal: 1024 kB\nMemAvailable: 512 kB"),
                         {"MemTotal": 1048576, "MemAvailable": 524288})

    def test_cpu_deltas(self):
        self.assertEqual(cpu_ticks("cpu  5 0 5 10 0 0 0 0"), (20, 10))
        self.assertEqual(cpu_usage((100, 50), (200, 80)), 70.0)
        self.assertEqual(cpu_usage((0, 0), (0, 0)), 0.0)

    def test_power_supply_energy_health(self):
        with tempfile.TemporaryDirectory() as temp:
            bat = Path(temp) / "BAT0"
            bat.mkdir()
            for name, value in {
                "type": "Battery", "capacity": "78", "status": "Charging",
                "energy_full": "42000", "energy_full_design": "56000",
            }.items():
                (bat / name).write_text(value, encoding="utf-8")
            self.assertEqual(battery_info(Path(temp)), (78, 75, "Charging"))

    def test_missing_battery(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(battery_info(Path(temp))[0:2], (None, None))

    def test_zram(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            device = root / "zram0"
            device.mkdir()
            (device / "disksize").write_text("8192")
            (device / "mm_stat").write_text("2048 512 256 0 0 0 0 0")
            self.assertEqual(zram_info(root), (8192, 2048))

    def test_uptime(self):
        self.assertEqual(uptime_display(90061), "1g 1sa 1dk")


class StorageTests(unittest.TestCase):
    def test_symlinks_and_home_file_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "home"
            root.mkdir()
            folder = root / "Videos"
            folder.mkdir()
            (folder / "movie.mp4").write_bytes(b"x" * 20)
            (folder / "other.mp4").write_bytes(b"y" * 10)
            (root / "outside").symlink_to(Path(temp), target_is_directory=True)
            report = scan_home(root, limit=1)
            self.assertEqual(report.scanned_files, 1)
            self.assertTrue(report.truncated)
            self.assertEqual(len(report.largest_files), 1)

    def test_browser_preview_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / ".cache/thumbnails"
            cache.mkdir(parents=True)
            (cache / "thumb.png").write_bytes(b"x" * 5)
            items = cache_preview(Path(temp))
            self.assertEqual([(i.path, i.size) for i in items],
                             [("Küçük resimler", 5)])
            self.assertTrue((cache / "thumb.png").exists())


class HistoryTests(unittest.TestCase):
    def test_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private/history.json"
            save_history([TaskResult("apt", True, "Clean")], path)
            result = load_history(path)
            self.assertEqual(result[0]["results"][0]["action"], "apt")
            self.assertEqual(result[0]["results"][0]["ok"], True)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_version_parser(self):
        self.assertTrue(version_tuple("v2.1.0") > version_tuple("2.0.0"))
        with self.assertRaises(ValueError):
            version_tuple("nightly/latest")


if __name__ == "__main__":
    unittest.main()
