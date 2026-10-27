"""PySide6 front-end: a compact holographic HUD.

The window is optional. It is imported lazily by the assistant only when
PySide6 is installed; otherwise ``run_window`` raises a clear error and the
assistant falls back to the CLI.
"""

from __future__ import annotations

try:
    from PySide6.QtGui import QFont, QTextCursor
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE_AVAILABLE = True
except ImportError:  # pragma: no cover - only hit without PySide6
    PYSIDE_AVAILABLE = False


_STYLESHEET = """
QMainWindow, QWidget { background-color: #05080d; color: #cfeffd; }
QTextEdit { background-color: #08121b; border: 1px solid #14f0c8; border-radius: 8px; padding: 8px; }
QLineEdit { background-color: #08121b; border: 1px solid #1c6f7d; border-radius: 8px; padding: 8px; color: #eafcff; }
QPushButton { background-color: #0d2a30; border: 1px solid #14f0c8; border-radius: 8px; padding: 8px 16px; color: #7ffbe6; }
QPushButton:hover { background-color: #12414a; }
QPushButton:disabled { border-color: #223344; color: #445566; }
QLabel#title { font-size: 20px; font-weight: 600; color: #7ffbe6; letter-spacing: 3px; }
QLabel#status { color: #6ba9b8; }
"""


def run_window(assistant) -> None:
    if not PYSIDE_AVAILABLE:
        raise RuntimeError("PySide6 is not installed.")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(assistant)
    window.show()
    app.exec()


if PYSIDE_AVAILABLE:

    class MainWindow(QMainWindow):
        def __init__(self, assistant):
            super().__init__()
            self._assistant = assistant
            self._assistant.permissions.set_confirmer(self._confirm)
            self.setWindowTitle(f"{assistant.name} - HUD")
            self.resize(760, 560)
            self.setStyleSheet(_STYLESHEET)

            root = QWidget()
            layout = QVBoxLayout(root)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(12)

            title = QLabel(assistant.name)
            title.setObjectName("title")
            layout.addWidget(title)

            self.transcript = QTextEdit()
            self.transcript.setReadOnly(True)
            self.transcript.setFont(QFont("Consolas", 10))
            layout.addWidget(self.transcript, stretch=1)

            controls = QHBoxLayout()
            self.input = QLineEdit()
            self.input.setPlaceholderText("Speak or type a command...")
            self.input.returnPressed.connect(self._on_send)
            controls.addWidget(self.input, stretch=1)

            self.send_button = QPushButton("Send")
            self.send_button.clicked.connect(self._on_send)
            controls.addWidget(self.send_button)

            self.mic_button = QPushButton("Push to Talk")
            self.mic_button.clicked.connect(self._on_push_to_talk)
            self.mic_button.setEnabled(bool(getattr(assistant.stt, "available", False)))
            controls.addWidget(self.mic_button)
            layout.addLayout(controls)

            footer = QHBoxLayout()
            self.speak_toggle = QCheckBox("Voice output")
            self.speak_toggle.setChecked(bool(getattr(assistant.tts, "available", False)))
            self.speak_toggle.toggled.connect(self._on_toggle_voice)
            footer.addWidget(self.speak_toggle)
            self.status = QLabel("Ready.")
            self.status.setObjectName("status")
            footer.addWidget(self.status, stretch=1)
            layout.addLayout(footer)

            self.setCentralWidget(root)
            self._append("assistant", f"{assistant.name} online.")
            self._on_toggle_voice(self.speak_toggle.isChecked())

        # -------------------------------------------------------------- #
        def _on_send(self) -> None:
            text = self.input.text().strip()
            if not text:
                return
            self.input.clear()
            self._append("user", text)
            self.status.setText("Working...")
            answer = self._assistant.handle(text, speak=True)
            self._append("assistant", answer)
            self.status.setText("Ready.")

        def _on_push_to_talk(self) -> None:
            self.status.setText("Listening...")
            result = self._assistant.stt.listen()
            if result.status == "ok" and result.text:
                self.input.setText(result.text)
                self._on_send()
            elif result.status == "unclear":
                self._append("assistant", "I didn't quite catch that.")
            self.status.setText("Ready.")

        def _on_toggle_voice(self, enabled: bool) -> None:
            self._assistant._voice_output = bool(enabled)

        def _confirm(self, prompt: str) -> bool:
            reply = QMessageBox.question(
                self,
                "Confirm action",
                prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes

        def _append(self, role: str, text: str) -> None:
            label = {"user": "You", "assistant": self._assistant.name}.get(role, role)
            cursor = self.transcript.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(f"{label}: {text}\n")
            self.transcript.setTextCursor(cursor)
