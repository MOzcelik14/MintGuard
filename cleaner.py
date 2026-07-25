import sys
import os
import subprocess

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
    QCheckBox
)


def run_command(command):
    try:
        result = subprocess.check_output(
            command,
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL
        )
        return result.strip()

    except:
        return "Yok"


def folder_size(path):
    total = 0

    if not os.path.exists(path):
        return "0 MB"

    for root, dirs, files in os.walk(path):
        for file in files:
            try:
                total += os.path.getsize(
                    os.path.join(root, file)
                )
            except:
                pass

    mb = total / (1024 * 1024)

    if mb > 1024:
        return f"{mb / 1024:.2f} GB"

    return f"{mb:.0f} MB"


def apt_cache():
    return run_command(
        "du -sh /var/cache/apt/archives | awk '{print $1}'"
    )


def journal():

    output = run_command(
        "journalctl --disk-usage"
    )

    parts = output.split()

    try:
        index = parts.index("in")
        return parts[index - 1]

    except:
        return "0"


def flatpak():

    output = run_command(
        "flatpak uninstall --unused --dry-run"
    )

    if "Nothing unused" in output:
        return "Temiz"

    if len(output) > 20:
        return "Var"

    return "Bilinmiyor"



class LinuxCleaner(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "Linux Cleaner"
        )

        self.resize(
            500,
            500
        )


        self.info = QLabel()


        self.apt_check = QCheckBox(
            "🗑 APT Cache temizle"
        )

        self.cache_check = QCheckBox(
            "📁 Kullanıcı Cache temizle"
        )

        self.journal_check = QCheckBox(
            "📜 Journal temizle"
        )

        self.flatpak_check = QCheckBox(
            "📦 Kullanılmayan Flatpak temizle"
        )


        self.apt_check.setChecked(True)
        self.cache_check.setChecked(True)
        self.journal_check.setChecked(True)
        self.flatpak_check.setChecked(True)


        self.refresh_button = QPushButton(
            "🔄 Yenile"
        )


        self.clean_button = QPushButton(
            "🧹 Seçilenleri Temizle"
        )


        self.refresh_button.clicked.connect(
            self.refresh
        )


        self.clean_button.clicked.connect(
            self.clean
        )


        layout = QVBoxLayout()


        layout.addWidget(
            self.info
        )

        layout.addWidget(
            self.apt_check
        )

        layout.addWidget(
            self.cache_check
        )

        layout.addWidget(
            self.journal_check
        )

        layout.addWidget(
            self.flatpak_check
        )


        layout.addWidget(
            self.refresh_button
        )

        layout.addWidget(
            self.clean_button
        )


        self.setLayout(
            layout
        )


        self.refresh()



    def refresh(self):

        text = f"""
🐧 Linux Cleaner


🗑 APT Cache:
{apt_cache()}


📁 Kullanıcı Cache:
{folder_size(os.path.expanduser("~/.cache"))}


📜 Journal:
{journal()}


📦 Flatpak:
{flatpak()}

"""

        self.info.setText(
            text
        )



    def clean(self):

        selected = []


        if self.apt_check.isChecked():
            selected.append(
                "APT Cache"
            )

        if self.cache_check.isChecked():
            selected.append(
                "Kullanıcı Cache"
            )

        if self.journal_check.isChecked():
            selected.append(
                "Journal"
            )

        if self.flatpak_check.isChecked():
            selected.append(
                "Flatpak"
            )


        if not selected:

            QMessageBox.warning(
                self,
                "Uyarı",
                "Hiçbir seçenek seçilmedi!"
            )

            return



        answer = QMessageBox.question(
            self,
            "Onay",
            "Şunlar temizlenecek:\n\n"
            + "\n".join(selected)
            + "\n\nDevam edilsin mi?"
        )


        if answer != QMessageBox.Yes:
            return



        commands = []


        if self.apt_check.isChecked():

            commands.append(
                "pkexec apt clean"
            )


        if self.cache_check.isChecked():

            commands.append(
                "rm -rf ~/.cache/*"
            )


        if self.journal_check.isChecked():

            commands.append(
                "pkexec journalctl --vacuum-time=7d"
            )


        if self.flatpak_check.isChecked():

            commands.append(
                "flatpak uninstall --unused -y"
            )



        for cmd in commands:

            subprocess.run(
                cmd,
                shell=True
            )



        QMessageBox.information(
            self,
            "Tamamlandı",
            "Seçilen temizlikler tamamlandı."
        )


        self.refresh()



app = QApplication(sys.argv)

window = LinuxCleaner()

window.show()


sys.exit(
    app.exec()
)
