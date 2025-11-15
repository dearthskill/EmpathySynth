"""
desktop_app.py — Person D Desktop UI (PyQt6)
Communicates with local API server at: http://127.0.0.1:5000/api/process
"""

import sys
import json
import threading
import time
import tempfile
import traceback
from pathlib import Path
from typing import Dict, Any

import requests
from PyQt6 import QtWidgets, QtGui, QtCore

# audio
try:
    from pydub import AudioSegment
    from pydub.playback import _play_with_simpleaudio as play_audio
    AUDIO_LIB_AVAILABLE = True
except:
    AUDIO_LIB_AVAILABLE = False

APP_NAME = "PersonD"
DATA_DIR = Path.home() / f".{APP_NAME.lower()}"
DATA_DIR.mkdir(exist_ok=True)
PREFS_FILE = DATA_DIR / "prefs.json"
LOG_FILE = DATA_DIR / "emotion_logs.json"

DEFAULT_PREFS = {
    "frequency_seconds": 30,
    "background_mode": True,
    "api_base": "http://127.0.0.1:5000"
}


def load_prefs() -> Dict[str, Any]:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text())
        except:
            return DEFAULT_PREFS.copy()
    return DEFAULT_PREFS.copy()


def save_prefs(prefs: Dict[str, Any]):
    PREFS_FILE.write_text(json.dumps(prefs, indent=2))


def append_log(entry: Dict[str, Any]):
    logs = []
    if LOG_FILE.exists():
        try:
            logs = json.loads(LOG_FILE.read_text())
        except:
            logs = []
    logs.append(entry)
    LOG_FILE.write_text(json.dumps(logs, indent=2))


class MonitorWorker(QtCore.QObject):
    status = QtCore.pyqtSignal(str)
    log_emotion = QtCore.pyqtSignal(dict)

    def __init__(self, prefs):
        super().__init__()
        self._prefs = prefs
        self._stop_event = threading.Event()
        self._thread = None
        self._playing_handle = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._playing_handle and hasattr(self._playing_handle, "stop"):
            try:
                self._playing_handle.stop()
            except:
                pass

    def _run(self):
        self.status.emit("Monitoring started...")
        while not self._stop_event.is_set():
            try:
                base = self._prefs.get("api_base", "http://127.0.0.1:5000")
                resp = requests.get(f"{base}/api/process", timeout=15)
                data = resp.json()

                # log emotion
                self.log_emotion.emit(data.get("emotion", {}))

                audio_b64 = data.get("audio_b64")

                if audio_b64:
                    self.status.emit("Playing calming loop...")

                    import base64, io
                    audio_bytes = base64.b64decode(audio_b64)

                    if AUDIO_LIB_AVAILABLE:
                        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
                        looped = seg.append(seg, crossfade=500)
                        playback = play_audio(looped)
                        self._playing_handle = playback

                        t0 = time.time()
                        while time.time() - t0 < self._prefs["frequency_seconds"]:
                            if self._stop_event.is_set():
                                break
                            time.sleep(0.5)

                        try:
                            playback.stop()
                        except:
                            pass

                else:
                    self.status.emit("No audio returned, waiting...")
                    time.sleep(self._prefs["frequency_seconds"])

            except Exception as e:
                traceback.print_exc()
                self.status.emit(f"Error: {e}")
                time.sleep(5)

        self.status.emit("Monitoring stopped.")


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent, prefs):
        super().__init__(parent)
        self.prefs = prefs
        self.setWindowTitle("Settings")

        layout = QtWidgets.QFormLayout(self)

        self.freq = QtWidgets.QSpinBox()
        self.freq.setRange(5, 3600)
        self.freq.setValue(self.prefs["frequency_seconds"])

        self.api = QtWidgets.QLineEdit(self.prefs["api_base"])

        self.bg = QtWidgets.QCheckBox("Run in background (tray)")
        self.bg.setChecked(self.prefs["background_mode"])

        delete_btn = QtWidgets.QPushButton("Delete Data")
        delete_btn.clicked.connect(self.delete_data)

        layout.addRow("Frequency (sec):", self.freq)
        layout.addRow("API Base URL:", self.api)
        layout.addRow(self.bg)
        layout.addRow(delete_btn)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                          QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def delete_data(self):
        if LOG_FILE.exists():
            LOG_FILE.unlink()
        QtWidgets.QMessageBox.information(self, "Deleted", "Emotion logs cleared.")

    def accept(self):
        self.prefs["frequency_seconds"] = self.freq.value()
        self.prefs["api_base"] = self.api.text()
        self.prefs["background_mode"] = self.bg.isChecked()
        save_prefs(self.prefs)
        super().accept()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Person D Desktop")
        self.resize(400, 250)
        self.prefs = load_prefs()
        self.consent_given = False

        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        self.setCentralWidget(w)

        self.btn_consent = QtWidgets.QPushButton("Give Consent")
        self.btn_start = QtWidgets.QPushButton("Start Monitoring")
        self.btn_stop = QtWidgets.QPushButton("Stop Monitoring")
        self.btn_settings = QtWidgets.QPushButton("Settings")
        self.lbl_status = QtWidgets.QLabel("Idle...")

        self.btn_stop.setEnabled(False)

        layout.addWidget(self.btn_consent)
        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_settings)
        layout.addWidget(self.lbl_status)

        self.btn_consent.clicked.connect(self.give_consent)
        self.btn_start.clicked.connect(self.start_monitoring)
        self.btn_stop.clicked.connect(self.stop_monitoring)
        self.btn_settings.clicked.connect(self.open_settings)

        # tray icon
        self.tray = QtWidgets.QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))
        tray_menu = QtWidgets.QMenu()
        tray_menu.addAction("Open", self.show)
        tray_menu.addAction("Quit", QtWidgets.QApplication.quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        # background worker
        self.worker = MonitorWorker(self.prefs)
        self.worker.status.connect(self.lbl_status.setText)
        self.worker.log_emotion.connect(self.log_emotion)

    def give_consent(self):
        self.consent_given = True
        self.btn_consent.setEnabled(False)
        QtWidgets.QMessageBox.information(self, "Consent", "Consent recorded.")

    def start_monitoring(self):
        if not self.consent_given:
            QtWidgets.QMessageBox.warning(self, "Error", "Please give consent first.")
            return

        self.worker._prefs = self.prefs
        self.worker.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop_monitoring(self):
        self.worker.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def log_emotion(self, emotion):
        append_log({"ts": time.time(), "emotion": emotion})

    def open_settings(self):
        dlg = SettingsDialog(self, self.prefs)
        dlg.exec()
        self.prefs = load_prefs()

    def closeEvent(self, event):
        if self.prefs["background_mode"]:
            event.ignore()
            self.hide()
            self.tray.showMessage("Person D", "Running in background...")
        else:
            self.worker.stop()
            event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
