#!/usr/bin/env python3
"""Package a PyInstaller --onedir MintGuard bundle into a Linux .deb.

Run on Ubuntu 24.04 for binary compatibility with Linux Mint 22.x.
Requires: dpkg-deb and an existing dist/mintguard/ directory.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(dist: Path, output: Path, version: str) -> Path:
    if not (dist / "mintguard").is_file():
        raise FileNotFoundError("Missing PyInstaller executable: " + str(dist / "mintguard"))
    if not shutil.which("dpkg-deb"):
        raise RuntimeError("dpkg-deb is required")
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"mintguard_{version}_amd64.deb"
    with tempfile.TemporaryDirectory(prefix="mintguard-deb-") as workspace:
        package = Path(workspace) / "mintguard"
        app_dir = package / "opt/mintguard"
        app_dir.parent.mkdir(parents=True)
        shutil.copytree(dist, app_dir, symlinks=True)
        (app_dir / "mintguard").chmod(0o755)
        icons = package / "usr/share/icons/hicolor/scalable/apps"
        icons.mkdir(parents=True)
        shutil.copy2(ROOT / "assets/mintguard.svg", icons / "mintguard.svg")
        desktop = package / "usr/share/applications"
        desktop.mkdir(parents=True)
        (desktop / "mintguard.desktop").write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=MintGuard\n"
            "Name[tr]=MintGuard\n"
            "Comment=Linux Mint maintenance and health dashboard\n"
            "Comment[tr]=Linux Mint sistem bakım ve sağlık merkezi\n"
            "Exec=/opt/mintguard/mintguard\n"
            "Icon=mintguard\n"
            "Terminal=false\n"
            "Categories=System;Utility;\n"
            "StartupNotify=true\n",
            encoding="utf-8",
        )
        control = package / "DEBIAN"
        control.mkdir()
        (control / "control").write_text(
            f"Package: mintguard\nVersion: {version}\n"
            "Section: utils\nPriority: optional\nArchitecture: amd64\n"
            "Maintainer: MintGuard contributors <noreply@github.com>\n"
            "Depends: libc6 (>= 2.39), libgl1, libegl1, libopengl0, libxkbcommon-x11-0, libxcb-cursor0\n"
            "Recommends: polkitd, flatpak\n"
            "Description: Linux Mint maintenance and health dashboard\n"
            " View system health, analyze storage and perform opt-in cleanup.\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(package), str(target)],
            check=True,
        )
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=ROOT / "dist/mintguard")
    parser.add_argument("--output", type=Path, default=ROOT / "build")
    parser.add_argument("--version", default="2.0.0")
    args = parser.parse_args()
    print(build(args.dist, args.output, args.version))


if __name__ == "__main__":
    main()
