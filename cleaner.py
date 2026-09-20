"""MintGuard — Linux Mint maintenance dashboard (PySide6)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from modules.maintenance import (
    TASK_LABELS, Snapshot, TaskResult, format_size, run_maintenance, scan_system,
)

DARK = {
    "window": "#121821", "card": "#1b2531", "field": "#243242",
    "border": "#344459", "text": "#ecf2f8", "muted": "#a9b8ca",
    "accent": "#70d6b1", "accent_text": "#10251d", "hover": "#344657",
}
LIGHT = {
    "window": "#f2f5f7", "card": "#ffffff", "field": "#e9eef2",
    "border": "#d6e0e7", "text": "#172a35", "muted": "#526a79",
    "accent": "#137b58", "accent_text": "#ffffff", "hover": "#e1e9ee",
}


def stylesheet(palette: dict[str, str]) -> str:
    p = palette
    return f"""
        QWidget {{ background: {p["window"]}; color: {p["text"]}; }}
        QLabel#muted, QLabel#hint {{ color: {p["muted"]}; }}
        QLabel#headline {{ font-size: 28px; font-weight: 750; }}
        QLabel#section {{ font-size: 17px; font-weight: 700; }}
        QLabel#metric {{ font-size: 25px; font-weight: 750; color: {p["accent"]}; }}
        QFrame#card {{
            background: {p["card"]}; border: 1px solid {p["border"]};
            border-radius: 15px;
        }}
        QFrame#card QLabel, QFrame#card QCheckBox {{
            background: transparent; border: none;
        }}
        QCheckBox {{ spacing: 10px; font-size: 14px; }}
        QPushButton {{
            background: {p["field"]}; border: 1px solid {p["border"]};
            border-radius: 10px; padding: 11px 18px; font-weight: 650;
        }}
        QPushButton:hover {{ background: {p["hover"]}; }}
        QPushButton#primary {{
            background: {p["accent"]}; color: {p["accent_text"]};
            border-color: {p["accent"]};
        }}
        QPushButton:disabled, QCheckBox:disabled {{ opacity: 0.5; color: {p["muted"]}; }}
        QProgressBar {{
            background: {p["field"]}; border: none; border-radius: 5px;
            text-align: center; height: 10px;
        }}
        QProgressBar::chunk {{ background: {p["accent"]}; border-radius: 5px; }}
        QSpinBox {{
            background: {p["field"]}; border: 1px solid {p["border"]};
            border-radius: 8px; padding: 7px 10px;
        }}
        QPlainTextEdit {{
            background: {p["card"]}; color: {p["text"]};
            border: 1px solid {p["border"]}; border-radius: 12px;
            padding: 10px;
        }}
        QScrollArea {{ border: none; }}
    """


class MaintenanceWorker(QThread):
    scan_ready = Signal(object)
    clean_ready = Signal(object)
    progress = Signal(str)
    failed = Signal(str)

    def __init__(self, operation: str, days: int, selected: tuple[str, ...] = ()):
        super().__init__()
        self.operation = operation
        self.days = days
        self.selected = selected

    def run(self) -> None:
        try:
            if self.operation == "scan":
                self.scan_ready.emit(scan_system(self.days))
            else:
                results = run_maintenance(
                    self.selected, self.days, on_progress=self.progress.emit,
                )
                self.clean_ready.emit(results)
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class TaskCard(QFrame):
    def __init__(self, title: str, description: str, checked: bool = False):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(155)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(19, 18, 19, 18)
        layout.setSpacing(7)

        self.check = QCheckBox(title)
        self.check.setChecked(checked)
        self.metric = QLabel("Taranıyor…")
        self.metric.setObjectName("metric")
        self.detail = QLabel(description)
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        self.detail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(self.check)
        layout.addWidget(self.metric)
        layout.addWidget(self.detail)
        layout.addStretch()


class MintGuard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MintGuard — Sistem Bakımı")
        self.resize(920, 810)
        self.setMinimumSize(540, 540)
        self.worker: MaintenanceWorker | None = None
        self.pending_refresh = False
        self.columns = 2

        screen = QScrollArea()
        screen.setWidgetResizable(True)
        body = QWidget()
        screen.setWidget(body)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(screen)
        page = QVBoxLayout(body)
        page.setContentsMargins(29, 27, 29, 27)
        page.setSpacing(19)

        heading = QLabel("MintGuard")
        heading.setObjectName("headline")
        subtitle = QLabel("Linux Mint için güvenli bakım ve disk görünümü")
        subtitle.setObjectName("muted")
        page.addWidget(heading)
        page.addWidget(subtitle)

        disk = QFrame()
        disk.setObjectName("card")
        disk_layout = QVBoxLayout(disk)
        disk_layout.setContentsMargins(20, 18, 20, 18)
        disk_layout.setSpacing(9)
        disk_heading = QLabel("Disk kullanımı")
        disk_heading.setObjectName("section")
        self.disk_text = QLabel("Hesaplanıyor…")
        self.disk_text.setObjectName("muted")
        self.disk_progress = QProgressBar()
        self.disk_progress.setTextVisible(False)
        self.disk_progress.setRange(0, 100)
        self.disk_progress.setValue(0)
        disk_layout.addWidget(disk_heading)
        disk_layout.addWidget(self.disk_text)
        disk_layout.addWidget(self.disk_progress)
        page.addWidget(disk)

        controls = QHBoxLayout()
        section = QLabel("Bakım işlemleri")
        section.setObjectName("section")
        controls.addWidget(section)
        controls.addStretch()
        controls.addWidget(QLabel("Önbellek yaşı:"))
        self.days = QSpinBox()
        self.days.setRange(1, 90)
        self.days.setSuffix(" gün")
        self.days.setValue(7)
        self.days.setToolTip("Yalnızca bu süreden daha eski düzenli önbellek dosyaları silinir.")
        self.days.valueChanged.connect(self.on_days_changed)
        controls.addWidget(self.days)
        page.addLayout(controls)

        self.cards = {
            "apt": TaskCard("APT paket önbelleği", "İndirilen .deb paketleri silinir.", True),
            "cache": TaskCard(
                "Kullanıcı önbelleği",
                "Yalnızca eski normal dosyalar silinir. Uygulamalar yeniden önbellek oluşturabilir.",
            ),
            "journal": TaskCard(
                "Sistem günlükleri", "7 günden eski arşiv günlükleri kaldırılır.", True,
            ),
            "flatpak": TaskCard(
                "Kullanılmayan Flatpak",
                "Gereksiz bağımlılıklar temizlenir; uygulama verileri korunur.",
            ),
        }
        self.grid = QGridLayout()
        self.grid.setSpacing(13)
        self.reflow_cards(2)
        page.addLayout(self.grid)

        cache_heading = QLabel("En büyük önbellek klasörleri")
        cache_heading.setObjectName("section")
        self.cache_folders = QLabel("Taranıyor…")
        self.cache_folders.setObjectName("muted")
        self.cache_folders.setWordWrap(True)
        page.addWidget(cache_heading)
        page.addWidget(self.cache_folders)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Yeniden tara")
        self.clean_button = QPushButton("Seçilenleri temizle")
        self.clean_button.setObjectName("primary")
        self.refresh_button.clicked.connect(self.refresh)
        self.clean_button.clicked.connect(self.clean)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.clean_button)
        page.addLayout(buttons)

        self.status = QLabel("Hazırlanıyor…")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        page.addWidget(self.status)
        self.activity = QProgressBar()
        self.activity.setTextVisible(False)
        self.activity.hide()
        page.addWidget(self.activity)

        log_heading = QLabel("İşlem raporu")
        log_heading.setObjectName("section")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(112)
        self.log.setPlaceholderText("Bakım sonucu burada görünecek.")
        page.addWidget(log_heading)
        page.addWidget(self.log)
        page.addStretch()

        palette = DARK if QApplication.palette().window().color().lightness() < 128 else LIGHT
        self.setStyleSheet(stylesheet(palette))
        self.refresh()

    def reflow_cards(self, columns: int) -> None:
        for index, card in enumerate(self.cards.values()):
            self.grid.addWidget(card, index // columns, index % columns)
        self.columns = columns

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            columns = 1 if self.width() < 740 else 2
            if columns != self.columns:
                self.reflow_cards(columns)

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.refresh_button.setDisabled(busy)
        self.clean_button.setDisabled(busy)
        self.days.setDisabled(busy)
        for card in self.cards.values():
            card.check.setDisabled(busy)
        self.activity.setVisible(busy)
        if busy:
            self.activity.setRange(0, 0)
        else:
            self.activity.setRange(0, 100)
            self.activity.setValue(0)
        if message:
            self.status.setText(message)

    def start_worker(self, operation: str, selected: tuple[str, ...] = ()) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.set_busy(True, "Disk ve önbellek taranıyor…" if operation == "scan"
                      else "Temizlik başlatıldı…")
        worker = MaintenanceWorker(operation, self.days.value(), selected)
        self.worker = worker
        worker.scan_ready.connect(self.show_snapshot)
        worker.clean_ready.connect(self.show_results)
        worker.progress.connect(lambda title: self.status.setText(f"İşleniyor: {title}"))
        worker.failed.connect(self.show_error)
        worker.finished.connect(self.worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def refresh(self) -> None:
        self.start_worker("scan")

    def on_days_changed(self, _value: int) -> None:
        self.refresh()

    def show_snapshot(self, data: Snapshot) -> None:
        self.disk_text.setText(
            f"{format_size(data.disk_used)} kullanılıyor  ·  "
            f"{format_size(data.disk_free)} boş  ·  "
            f"{format_size(data.disk_total)} toplam"
        )
        self.disk_progress.setValue(
            round(data.disk_used / data.disk_total * 100) if data.disk_total else 0
        )
        self.cards["apt"].metric.setText(format_size(data.apt_bytes))
        self.cards["cache"].metric.setText(format_size(data.cache.total_bytes))
        self.cards["cache"].detail.setText(
            f"{self.days.value()} günden eski: {format_size(data.cache.eligible_bytes)} "
            f"({data.cache.eligible_count} dosya). Önbellek temizliği isteğe bağlıdır."
        )
        self.cards["journal"].metric.setText(format_size(data.journal_bytes))
        self.cards["flatpak"].metric.setText(
            "Kullanılabilir" if data.flatpak_available else "Kurulu değil"
        )
        self.cards["flatpak"].detail.setText(
            "Kullanılmayan kullanıcı ve sistem bağımlılıkları işlem sırasında belirlenir."
            if data.flatpak_available else "Flatpak komutu sistemde bulunamadı."
        )
        self.cards["flatpak"].check.setEnabled(data.flatpak_available)
        if not data.flatpak_available:
            self.cards["flatpak"].check.setChecked(False)

        self.cache_folders.setText(
            "\n".join(
                f"• {name}: {format_size(size)}"
                for name, size in data.cache.largest
            ) or "Önbellek klasörü boş."
        )
        self.status.setText(
            "Tarama tamamlandı."
            if not data.warnings
            else "Tarama tamamlandı; not: " + " | ".join(data.warnings)
        )

    def clean(self) -> None:
        selected = tuple(
            name for name, card in self.cards.items() if card.check.isChecked()
        )
        if not selected:
            QMessageBox.information(self, "Seçim yok", "Önce bir bakım işlemi seç.")
            return
        names = "\n".join(f"• {TASK_LABELS[name]}" for name in selected)
        note = (
            f"\n\nKullanıcı önbelleğinde yalnızca {self.days.value()} günden eski "
            "dosyalar silinir. Bu dosyalar uygulamalar tarafından yeniden üretilebilir."
            if "cache" in selected else ""
        )
        answer = QMessageBox.question(
            self, "Temizliği onayla",
            f"Şu işlemler gerçekleştirilecek:\n\n{names}{note}\n\nDevam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.start_worker("clean", selected)

    def show_results(self, results: list[TaskResult]) -> None:
        successes = sum(result.ok for result in results)
        # Pair each result and its own explanation in chronological order.
        lines = [
            line
            for result in results
            for line in (
                f"{'✓' if result.ok else '✗'} {TASK_LABELS.get(result.name, result.name)}",
                f"   {result.detail}",
                "",
            )
        ]
        self.log.setPlainText("\n".join(lines).strip())
        failed = len(results) - successes
        self.status.setText(
            f"{successes} işlem başarılı, {failed} işlem başarısız. "
            "Disk bilgileri yeniden taranacak."
        )
        self.pending_refresh = True

    def show_error(self, error: str) -> None:
        self.status.setText(f"İşlem sırasında hata: {error}")
        self.log.appendPlainText(f"✗ {error}")

    def worker_finished(self) -> None:
        self.worker = None
        self.set_busy(False)
        if self.pending_refresh:
            self.pending_refresh = False
            self.refresh()

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            event.ignore()
            self.status.setText("İşlem sürüyor; bitince pencereyi kapatabilirsin.")
        else:
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
