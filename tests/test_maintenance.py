"""Safe, dependency-free tests for the MintGuard maintenance backend."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.maintenance import (
    clean_cache, command_task, format_size, parse_journal_bytes,
    run_command, run_maintenance, scan_cache,
)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "cache"
        self.root.mkdir()
        self.outside = Path(self.temp.name) / "outside.txt"
        self.outside.write_text("protected", encoding="utf-8")
        self.old = self.root / "app" / "old.bin"
        self.old.parent.mkdir()
        self.old.write_bytes(b"old")
        self.recent = self.root / "app" / "recent.bin"
        self.recent.write_bytes(b"recent")
        self.now = 1_800_000_000
        os.utime(self.old, (self.now - 15 * 86400,) * 2)
        os.utime(self.recent, (self.now - 3600,) * 2)
        (self.root / "link-file").symlink_to(self.outside)
        (self.root / "link-dir").symlink_to(self.outside.parent, target_is_directory=True)

    def test_scan_counts_only_real_cache_files(self):
        result = scan_cache(self.root, days=7, now=self.now)
        self.assertEqual(result.total_bytes, 9)
        self.assertEqual(result.eligible_bytes, 3)
        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(result.largest[0], ("app", 9))

    def test_clean_keeps_recent_files_symlinks_and_outside_data(self):
        result = clean_cache(self.root, days=7, now=self.now)
        self.assertTrue(result.ok)
        self.assertEqual(result.freed_bytes, 3)
        self.assertFalse(self.old.exists())
        self.assertTrue(self.recent.exists())
        self.assertTrue((self.root / "link-file").is_symlink())
        self.assertTrue((self.root / "link-dir").is_symlink())
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "protected")
        self.assertTrue(self.old.parent.is_dir())

    def test_symlink_cache_root_is_rejected(self):
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        result = clean_cache(alias, now=self.now)
        self.assertFalse(result.ok)
        self.assertTrue(self.old.exists())

    def test_nonexistent_cache_is_no_op(self):
        result = clean_cache(self.root / "missing", now=self.now)
        self.assertTrue(result.ok)
        self.assertEqual(result.freed_bytes, 0)


class CommandTests(unittest.TestCase):
    def test_human_sizes(self):
        self.assertEqual(format_size(1024), "1.0 KiB")
        self.assertEqual(format_size(None), "Bilinmiyor")

    def test_journal_parsing(self):
        self.assertEqual(
            parse_journal_bytes(
                "Archived and active journals take up 12.5M in the file system."
            ),
            int(12.5 * 1024**2),
        )
        self.assertIsNone(parse_journal_bytes("error"))

    def test_nonzero_exit_is_not_reported_as_success(self):
        with patch(
            "modules.maintenance.run_command",
            return_value=subprocess.CompletedProcess(
                args=["apt", "clean"], returncode=126,
                stdout="", stderr="authorization denied",
            ),
        ):
            result = command_task("apt", ["apt", "clean"])
        self.assertFalse(result.ok)
        self.assertIn("authorization denied", result.detail)

    def test_unknown_task_is_rejected(self):
        result = run_maintenance(["unknown"])
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].ok)

    def test_command_is_run_without_shell(self):
        with patch("modules.maintenance.subprocess.run") as execute:
            execute.return_value = subprocess.CompletedProcess(["echo"], 0, "", "")
            run_command(["echo", "hello"])
        self.assertEqual(execute.call_args.args[0], ["echo", "hello"])
        self.assertNotIn("shell", execute.call_args.kwargs)
        self.assertFalse(execute.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
