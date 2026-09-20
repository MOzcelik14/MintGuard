"""MintGuard 2 — responsive Linux Mint desktop maintenance center."""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from modules.advanced_cleanup import run_extra, unused_apt_preview
from modules.history import RELEASES_URL, check_releases, load_history, save_history
from modules.i18n import tr
from modules.maintenance import (
    Snapshot, TaskResult, format_size, run_maintenance, scan_system,
)
from modules.storage import StorageReport, cache_preview, scan_home, storage_lines
from modules.system_info import (
    SystemSnapshot, VERSION, snapshot, storage_display, uptime_display,
)

COLORS = {
    "dark": {
        "window": "#101820", "sidebar": "#15212a", "card": "#1b2b35",
        "field": "#283a45", "line": "#38505b", "text": "#eef8f6",
        "muted": "#a9bdc4", "accent": "#72dcad", "accent_text": "#10291f",
    },
    "light": {
        "window": "#f1f7f4", "sidebar": "#e6f0eb", "card": "#ffffff",
        "field": "#eaf1ed", "line": "#cedfd5", "text": "#163128",
        "muted": "#536e63", "accent": "#19764f", "accent_text": "#ffffff",
    },
}
TASKS = ("apt", "cache", "journal", "flatpak", "thumbs", "trash")


def make_style(p: dict[str, str]) -> str:
    return f"""
    QWidget {{ background: {p["window"]}; color: {p["text"]}; font-size: 13px; }}
    QFrame#sidebar {{ background: {p["sidebar"]}; border: none; }}
    QFrame#card {{
        background: {p["card"]}; border: 1px solid {p["line"]};
        border-radius: 14px;
    }}
    QFrame#card QLabel, QFrame#card QCheckBox {{
        background: transparent; border: none;
    }}
    QLabel#heading {{ font-size: 25px; font-weight: 750; }}
    QLabel#section {{ font-size: 17px; font-weight: 720; }}
    QLabel#metric {{ font-size: 21px; font-weight: 750; color: {p["accent"]}; }}
    QLabel#muted {{ color: {p["muted"]}; }}
    QPushButton {{
        background: {p["field"]}; border: 1px solid {p["line"]};
        border-radius: 9px; padding: 10px 13px; font-weight: 650;
        text-align: center;
    }}
    QPushButton:hover {{ border-color: {p["accent"]}; }}
    QPushButton#primary {{
        color: {p["accent_text"]}; background: {p["accent"]};
        border-color: {p["accent"]};
    }}
    QPushButton#navigation {{ background: transparent; border: none; text-align: left; }}
    QPushButton#navigation[active="true"] {{
        color: {p["accent"]}; background: {p["card"]};
    }}
    QPushButton:disabled {{ color: {p["muted"]}; }}
    QCheckBox {{ spacing: 9px; background: transparent; }}
    QSpinBox {{
        background: {p["card"]}; border: 1px solid {p["line"]};
        border-radius: 7px; padding: 7px;
    }}
    QProgressBar {{
        border: none; border-radius: 5px; background: {p["field"]};
        height: 10px; text-align: center;
    }}
    QProgressBar::chunk {{ background: {p["accent"]}; border-radius: 5px; }}
    QPlainTextEdit {{
        background: {p["card"]}; border: 1px solid {p["line"]};
        border-radius: 9px; padding: 9px;
    }}
    QScrollArea {{ border: none; }}
    """


def card_layout() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(19, 16, 19, 16)
    layout.setSpacing(9)
    return frame, layout


def text_label(text: str = "", kind: str = "") -> QLabel:
    label = QLabel(text)
    if kind:
        label.setObjectName(kind)
    label.setWordWrap(True)
    return label


def progress_bar() -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    return bar


def scrolled_page() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    column = QVBoxLayout(body)
    column.setContentsMargins(22, 23, 22, 26)
    column.setSpacing(18)
    scroll.setWidget(body)
    return scroll, column


class Sparkline(QWidget):
    """Tiny CPU trend drawn with QPainter; no plotting dependency."""
    def __init__(self):
        super().__init__()
        self.values: deque[float] = deque(maxlen=60)
        self.setMinimumHeight(75)

    def add(self, value: float) -> None:
        self.values.append(max(0, min(100, value)))
        self.update()

    def paintEvent(self, event) -> None:
        if len(self.values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#59cda1")
        painter.setPen(QPen(color, 2))
        values = list(self.values)
        for i in range(1, len(values)):
            w = max(1, self.width() - 12)
            h = max(1, self.height() - 12)
            x1 = 6 + int((i - 1) * w / (len(values) - 1))
            x2 = 6 + int(i * w / (len(values) - 1))
            y1 = 6 + int((100 - values[i - 1]) * h / 100)
            y2 = 6 + int((100 - values[i]) * h / 100)
            painter.drawLine(x1, y1, x2, y2)
        painter.end()


class TaskCard(QFrame):
    def __init__(self, name: str, language: str, checked: bool = False):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(128)
        self.name = name
        col = QVBoxLayout(self)
        col.setContentsMargins(15, 14, 15, 14)
        self.check = QCheckBox(tr(name, language))
        self.check.setChecked(checked)
        self.metric = text_label("—", "metric")
        self.detail = text_label(tr(name + "_desc", language), "muted")
        col.addWidget(self.check)
        col.addWidget(self.metric)
        col.addWidget(self.detail)
        col.addStretch()


class Work(QThread):
    result = Signal(str, object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, action: str, days: int, selected: tuple[str, ...] = ()):
        super().__init__()
        self.action = action
        self.days = days
        self.selected = selected

    def run(self) -> None:
        try:
            if self.action == "scan":
                payload = scan_system(self.days)
            elif self.action == "health":
                payload = snapshot()
            elif self.action == "storage":
                report = scan_home(on_progress=lambda n: self.progress.emit(f"{n:,} files"))
                payload = (report, cache_preview())
            elif self.action == "apt-preview":
                payload = unused_apt_preview()
            elif self.action == "release":
                payload = check_releases()
            elif self.action == "clean":
                payload: list[TaskResult] = []
                for name in self.selected:
                    self.progress.emit(name)
                    if name in ("thumbs", "trash"):
                        payload.append(run_extra(name, self.days))
                    else:
                        payload.extend(run_maintenance((name,), self.days))
            else:
                raise ValueError(f"Unknown action: {self.action}")
            self.result.emit(self.action, payload)
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class MintGuard(QWidget):
    def __init__(self):
        super().__init__()
        self.language = "tr"
        self.worker: Work | None = None
        self.worker_action = ""
        self.pending_scan = False
        self.flatpak_available = True
        self.columns = 2
        self.setWindowTitle("MintGuard 2")
        self.resize(1080, 790)
        self.setMinimumSize(660, 510)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(186)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(12, 24, 12, 18)
        nav.setSpacing(8)
        nav.addWidget(text_label("  MintGuard", "heading"))
        nav.addWidget(text_label(f"  v{VERSION}", "muted"))
        nav.addSpacing(21)
        self.nav_buttons: list[QPushButton] = []
        self.stack = QStackedWidget()
        for index, name in enumerate(("overview", "cleanup", "storage", "system")):
            button = QPushButton(tr(name))
            button.setObjectName("navigation")
            button.clicked.connect(lambda _checked=False, index=index: self.navigate(index))
            self.nav_buttons.append(button)
            nav.addWidget(button)
        nav.addStretch()
        self.language_button = QPushButton("English")
        self.language_button.clicked.connect(self.toggle_language)
        nav.addWidget(self.language_button)
        self.releases_button = QPushButton(tr("release"))
        self.releases_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL))
        )
        nav.addWidget(self.releases_button)
        self.status = text_label(tr("ready"), "muted")
        nav.addWidget(self.status)
        self.activity = progress_bar()
        self.activity.hide()
        nav.addWidget(self.activity)
        outer.addWidget(sidebar)
        outer.addWidget(self.stack, 1)

        self.build_overview()
        self.build_cleanup()
        self.build_storage()
        self.build_system()
        self.navigate(0)
        self.apply_theme()
        self.refresh()

        self.timer = QTimer(self)
        self.timer.setInterval(6000)
        self.timer.timeout.connect(self.poll_health)
        self.timer.start()

    def apply_theme(self) -> None:
        is_dark = QApplication.palette().window().color().lightness() < 128
        self.setStyleSheet(make_style(COLORS["dark" if is_dark else "light"]))

    def build_overview(self) -> None:
        scroll, col = scrolled_page()
        self.stack.addWidget(scroll)
        self.overview_title = text_label(tr("health"), "heading")
        self.overview_subtitle = text_label(tr("subtitle"), "muted")
        col.addWidget(self.overview_title)
        col.addWidget(self.overview_subtitle)

        self.health_grid = QGridLayout()
        self.health_grid.setSpacing(12)
        self.health_tiles = {}
        for index, name in enumerate(("cpu", "memory", "swap", "zram", "battery", "disk")):
            frame, tile = card_layout()
            title = text_label(tr(name), "muted")
            value = text_label("—", "metric")
            bar = progress_bar()
            tile.addWidget(title)
            tile.addWidget(value)
            tile.addWidget(bar)
            self.health_tiles[name] = (title, value, bar)
            self.health_grid.addWidget(frame, index // 2, index % 2)
        col.addLayout(self.health_grid)

        graph_frame, graph = card_layout()
        self.graph_title = text_label(tr("cpu"), "section")
        self.graph = Sparkline()
        graph.addWidget(self.graph_title)
        graph.addWidget(self.graph)
        col.addWidget(graph_frame)

        self.overview_refresh = QPushButton(tr("refresh"))
        self.overview_refresh.clicked.connect(self.refresh)
        col.addWidget(self.overview_refresh)
        col.addStretch()

    def build_cleanup(self) -> None:
        scroll, col = scrolled_page()
        self.stack.addWidget(scroll)
        self.cleanup_title = text_label(tr("cleanup"), "heading")
        col.addWidget(self.cleanup_title)
        options = QHBoxLayout()
        self.age_label = text_label(tr("age"))
        self.days = QSpinBox()
        self.days.setRange(1, 90)
        self.days.setValue(7)
        self.days.setSuffix(tr("days"))
        self.days.valueChanged.connect(self.refresh)
        options.addWidget(self.age_label)
        options.addWidget(self.days)
        options.addStretch()
        col.addLayout(options)
        self.cards = {
            name: TaskCard(name, self.language, name in ("apt", "journal"))
            for name in TASKS
        }
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.reflow_cards(2)
        col.addLayout(self.grid)
        self.cache_warning = text_label(tr("cache_warn"), "muted")
        col.addWidget(self.cache_warning)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton(tr("refresh"))
        self.refresh_button.clicked.connect(self.refresh)
        self.clean_button = QPushButton(tr("run"))
        self.clean_button.setObjectName("primary")
        self.clean_button.clicked.connect(self.clean)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.clean_button)
        col.addLayout(actions)
        self.folders_title = text_label(tr("folders"), "section")
        self.cache_folders = text_label("—", "muted")
        col.addWidget(self.folders_title)
        col.addWidget(self.cache_folders)
        self.apt_preview_button = QPushButton(tr("apt_preview"))
        self.apt_preview_button.clicked.connect(lambda: self.start_worker("apt-preview"))
        self.apt_output = QPlainTextEdit()
        self.apt_output.setReadOnly(True)
        self.apt_output.setMinimumHeight(95)
        self.apt_output.setMaximumHeight(180)
        col.addWidget(self.apt_preview_button)
        col.addWidget(self.apt_output)
        self.report_title = text_label(tr("report"), "section")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        col.addWidget(self.report_title)
        col.addWidget(self.log)
        col.addStretch()

    def build_storage(self) -> None:
        scroll, col = scrolled_page()
        self.stack.addWidget(scroll)
        self.storage_title = text_label(tr("space"), "heading")
        self.storage_hint = text_label(tr("disk_hint"), "muted")
        self.disk_text = text_label("—", "metric")
        self.disk_progress = progress_bar()
        self.storage_scan = QPushButton(tr("scan"))
        self.storage_scan.clicked.connect(lambda: self.start_worker("storage"))
        self.storage_output = QPlainTextEdit()
        self.storage_output.setReadOnly(True)
        self.storage_output.setMinimumHeight(320)
        self.storage_note = text_label(tr("personal_note"), "muted")
        self.preview_title = text_label(tr("preview"), "section")
        self.preview_output = QPlainTextEdit()
        self.preview_output.setReadOnly(True)
        self.preview_output.setMinimumHeight(135)
        self.browser_note = text_label(tr("browser_note"), "muted")
        for widget in (
            self.storage_title, self.storage_hint, self.disk_text,
            self.disk_progress, self.storage_scan, self.storage_output,
            self.storage_note, self.preview_title, self.preview_output, self.browser_note,
        ):
            col.addWidget(widget)
        col.addStretch()

    def build_system(self) -> None:
        scroll, col = scrolled_page()
        self.stack.addWidget(scroll)
        self.system_title = text_label(tr("system_details"), "heading")
        col.addWidget(self.system_title)
        frame, info = card_layout()
        self.system_fields = {}
        for key in ("os", "kernel", "uptime", "nvidia", "battery_charge"):
            row = QHBoxLayout()
            title = text_label(tr(key), "muted")
            value = text_label("—")
            title.setMinimumWidth(128)
            row.addWidget(title)
            row.addWidget(value, 1)
            info.addLayout(row)
            self.system_fields[key] = (title, value)
        col.addWidget(frame)
        self.update_button = QPushButton(tr("check_release"))
        self.update_button.clicked.connect(lambda: self.start_worker("release"))
        self.update_text = text_label(f"MintGuard v{VERSION}", "muted")
        col.addWidget(self.update_button)
        col.addWidget(self.update_text)
        self.history_title = text_label(tr("history"), "section")
        self.history_output = QPlainTextEdit()
        self.history_output.setReadOnly(True)
        self.history_output.setMinimumHeight(165)
        col.addWidget(self.history_title)
        col.addWidget(self.history_output)
        self.show_history()
        col.addStretch()

    def show_history(self) -> None:
        rows = []
        for entry in reversed(load_history()[-20:]):
            rows.append(entry.get("time", ""))
            for item in entry.get("results", []):
                rows.append(
                    f"  {'✓' if item.get('ok') else '✗'} "
                    f"{item.get('action', '?')}: {item.get('detail', '')}"
                )
        self.history_output.setPlainText(
            "\n".join(rows) if rows else tr("history_empty", self.language)
        )

    def navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if i == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 2 and not self.storage_output.toPlainText():
            self.start_worker("storage")

    def reflow_cards(self, columns: int) -> None:
        for i, card in enumerate(self.cards.values()):
            self.grid.addWidget(card, i // columns, i % columns)
        self.columns = columns

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            columns = 1 if self.width() < 910 else 2
            if self.columns != columns:
                self.reflow_cards(columns)

    def toggle_language(self) -> None:
        self.language = "en" if self.language == "tr" else "tr"
        self.language_button.setText("Türkçe" if self.language == "en" else "English")
        for name, button in zip(("overview", "cleanup", "storage", "system"), self.nav_buttons):
            button.setText(tr(name, self.language))
        for name, (title, _value, _bar) in self.health_tiles.items():
            title.setText(tr(name, self.language))
        for name, card in self.cards.items():
            card.check.setText(tr(name, self.language))
            if name not in ("cache", "flatpak"):
                card.detail.setText(tr(name + "_desc", self.language))
        for key, (title, _value) in self.system_fields.items():
            title.setText(tr(key, self.language))
        bindings = (
            (self.overview_title, "health"), (self.overview_subtitle, "subtitle"),
            (self.graph_title, "cpu"), (self.cleanup_title, "cleanup"),
            (self.age_label, "age"), (self.refresh_button, "refresh"),
            (self.overview_refresh, "refresh"), (self.clean_button, "run"),
            (self.cache_warning, "cache_warn"), (self.folders_title, "folders"),
            (self.apt_preview_button, "apt_preview"), (self.report_title, "report"),
            (self.storage_title, "space"), (self.storage_hint, "disk_hint"),
            (self.storage_scan, "scan"), (self.storage_note, "personal_note"),
            (self.preview_title, "preview"), (self.browser_note, "browser_note"),
            (self.system_title, "system_details"), (self.history_title, "history"),
            (self.update_button, "check_release"), (self.releases_button, "release"),
        )
        for widget, name in bindings:
            widget.setText(tr(name, self.language))
        self.days.setSuffix(tr("days", self.language))
        self.show_history()

    def set_busy(self, busy: bool, message: str = "") -> None:
        for button in (
            self.refresh_button, self.overview_refresh, self.clean_button,
            self.storage_scan, self.apt_preview_button, self.update_button,
        ):
            button.setDisabled(busy)
        self.days.setDisabled(busy)
        for name, card in self.cards.items():
            card.check.setDisabled(busy or (name == "flatpak" and not self.flatpak_available))
        self.activity.setVisible(busy)
        self.activity.setRange(0, 0 if busy else 100)
        if message:
            self.status.setText(message)

    def start_worker(self, action: str, selected: tuple[str, ...] = ()) -> None:
        if self.worker is not None:
            return
        self.set_busy(True, tr("busy", self.language))
        worker = Work(action, self.days.value(), selected)
        self.worker = worker
        self.worker_action = action
        worker.result.connect(self.handle_result)
        worker.failed.connect(self.handle_error)
        worker.progress.connect(lambda progress: self.status.setText(str(progress)))
        worker.finished.connect(self.worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def refresh(self, _value: int = 0) -> None:
        self.start_worker("scan")

    def poll_health(self) -> None:
        if self.worker is None and self.isVisible():
            self.start_worker("health")

    def handle_result(self, action: str, payload: object) -> None:
        if action == "scan":
            self.show_scan(payload)
        elif action == "health":
            self.show_health(payload)
        elif action == "storage":
            report, previews = payload
            self.storage_output.setPlainText(storage_lines(report))
            self.preview_output.setPlainText(
                "\n".join(
                    f"{row.path}: {format_size(row.size)}" for row in previews
                ) or "—"
            )
        elif action == "apt-preview":
            self.apt_output.setPlainText(str(payload))
        elif action == "release":
            newer, tag, url = payload
            key = "new_version" if newer else "latest_version"
            self.update_text.setText(f"{tr(key, self.language)} {tag}\n{url}")
        elif action == "clean":
            results: list[TaskResult] = payload
            rows = [
                line for result in results for line in (
                    f"{'✓' if result.ok else '✗'} {tr(result.name, self.language)}",
                    "    " + result.detail, "",
                )
            ]
            self.log.setPlainText("\n".join(rows))
            try:
                save_history(results)
                self.show_history()
            except OSError as error:
                self.log.appendPlainText(f"History: {error}")
            self.pending_scan = True
            good = sum(result.ok for result in results)
            self.status.setText(f"{good}/{len(results)} · {tr('done', self.language)}")
            return
        self.status.setText(tr("scan_done", self.language))

    def show_scan(self, data: Snapshot) -> None:
        self.flatpak_available = data.flatpak_available
        self.cards["apt"].metric.setText(format_size(data.apt_bytes))
        self.cards["cache"].metric.setText(format_size(data.cache.total_bytes))
        self.cards["cache"].detail.setText(
            f"{self.days.value()} {tr('days', self.language).strip()}: "
            f"{format_size(data.cache.eligible_bytes)} · "
            f"{data.cache.eligible_count} files"
        )
        self.cards["journal"].metric.setText(format_size(data.journal_bytes))
        self.cards["flatpak"].metric.setText(
            tr("available" if data.flatpak_available else "missing", self.language)
        )
        self.cards["thumbs"].metric.setText("—")
        self.cards["trash"].metric.setText("—")
        self.cards["flatpak"].check.setEnabled(data.flatpak_available)
        if not data.flatpak_available:
            self.cards["flatpak"].check.setChecked(False)
        self.cache_folders.setText("\n".join(
            f"• {name}: {format_size(size)}" for name, size in data.cache.largest
        ) or "—")
        self.set_disk(data.disk_used, data.disk_total, data.disk_free)
        if data.warnings:
            self.status.setText(" · ".join(data.warnings[:3]))

    def set_disk(self, used: int, total: int, free: int) -> None:
        self.disk_text.setText(
            f"{format_size(used)} {tr('used', self.language)}  ·  "
            f"{format_size(free)} {tr('free', self.language)}  ·  "
            f"{format_size(total)} {tr('total', self.language)}"
        )
        self.disk_progress.setValue(round(100 * used / total) if total else 0)

    def show_health(self, data: SystemSnapshot) -> None:
        values = {
            "cpu": (f"{data.cpu_percent:.1f}%", data.cpu_percent),
            "memory": (storage_display(data.memory_used, data.memory_total),
                       data.memory_used / data.memory_total * 100 if data.memory_total else 0),
            "swap": (storage_display(data.swap_used, data.swap_total),
                     data.swap_used / data.swap_total * 100 if data.swap_total else 0),
            "zram": (storage_display(data.zram_used, data.zram_total),
                     data.zram_used / data.zram_total * 100 if data.zram_total else 0),
            "disk": (storage_display(data.root_used, data.root_total),
                     data.root_used / data.root_total * 100 if data.root_total else 0),
            "battery": (f"{data.battery_health}%" if data.battery_health is not None
                        else tr("no_battery", self.language),
                        data.battery_percent or 0),
        }
        for key, (label, value) in values.items():
            self.health_tiles[key][1].setText(label)
            self.health_tiles[key][2].setValue(round(value))
        self.graph.add(data.cpu_percent)
        self.system_fields["os"][1].setText(data.distro)
        self.system_fields["kernel"][1].setText(data.kernel)
        self.system_fields["uptime"][1].setText(uptime_display(data.uptime_seconds))
        self.system_fields["nvidia"][1].setText(data.nvidia)
        self.system_fields["battery_charge"][1].setText(
            f"{data.battery_percent}% · {data.battery_charging}"
            if data.battery_percent is not None else tr("no_battery", self.language)
        )

    def clean(self) -> None:
        selected = tuple(name for name, card in self.cards.items() if card.check.isChecked())
        if not selected:
            QMessageBox.information(self, tr("cleanup", self.language),
                                    tr("no_select", self.language))
            return
        task_names = "\n".join("• " + tr(name, self.language) for name in selected)
        response = QMessageBox.question(
            self, tr("cleanup", self.language),
            tr("confirm", self.language) + "\n\n" + task_names,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        if "trash" in selected:
            response = QMessageBox.warning(
                self, tr("trash", self.language), tr("trash_warn", self.language),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        self.start_worker("clean", selected)

    def handle_error(self, reason: str) -> None:
        self.status.setText(f"{tr('scan_error', self.language)}: {reason}")
        self.log.appendPlainText("✗ " + reason)

    def worker_finished(self) -> None:
        self.worker = None
        self.set_busy(False)
        if self.pending_scan:
            self.pending_scan = False
            self.refresh()

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            self.status.setText(tr("closed_busy", self.language))
        else:
            self.timer.stop()
            event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MintGuard")
    app.setFont(QFont("Sans Serif", 10))
    window = MintGuard()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
