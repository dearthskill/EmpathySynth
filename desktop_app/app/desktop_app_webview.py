"""
desktop_app_consented.py

Simple, good-looking PyQt6 desktop app with:
- Consent prompt to turn camera ON
- Camera preview (uses OpenCV) after consent
- Single Start/Stop monitoring button
- When music plays: Skip and Like buttons appear
- Local logging (prefs + events)

Expectations:
- Your local API (Flask) running at http://127.0.0.1:5000/api/process
  which returns JSON:
    { "emotion": {...}, "prompt": "...", "seed": 123, "audio_b64": "<base64 wav>" }

How to run:
1) Activate venv (same one you used before)
   cd C:\path\to\project
   .\.venv\Scripts\Activate.ps1

2) Install dependencies (one-line):
   python -m pip install PyQt6 opencv-python requests pydub numpy sounddevice soundfile

   Also ensure ffmpeg is installed & on PATH (pydub needs it).
   On Windows: winget install ffmpeg  (or download static build and add to PATH)

3) Run:
   cd app
   python desktop_app_consented.py

Notes:
- If you don't want camera capability, you may skip installing opencv-python;
  the app will still run but won't show camera preview.
- Audio playback uses sounddevice (no simpleaudio required).
"""

import sys, base64, io, json, time, threading, traceback
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from PyQt6 import QtWidgets, QtGui, QtCore

# Try imports that are optional or heavy
try:
    import cv2
    OPENCV_AVAILABLE = True
except Exception:
    OPENCV_AVAILABLE = False

try:
    from pydub import AudioSegment
    PDUB_AVAILABLE = True
except Exception:
    PDUB_AVAILABLE = False

try:
    import numpy as np
    import sounddevice as sd
    SD_AVAILABLE = True
except Exception:
    SD_AVAILABLE = False

# ---------------- Paths & defaults ----------------
APP_NAME = "PersonD"
DATA_DIR = Path.home() / f".{APP_NAME.lower()}"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "events_log.json"
PREFS_FILE = DATA_DIR / "prefs.json"

DEFAULT_PREFS = {
    "api_base": "http://127.0.0.1:5000",
    "poll_interval": 20,
    "use_camera": False
}

# ---------------- Utilities ----------------
def load_prefs() -> Dict[str, Any]:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text())
        except:
            pass
    return DEFAULT_PREFS.copy()

def save_prefs(p):
    PREFS_FILE.write_text(json.dumps(p, indent=2))

def append_log(event: Dict[str, Any]):
    logs = []
    if LOG_FILE.exists():
        try:
            logs = json.loads(LOG_FILE.read_text())
        except:
            logs = []
    logs.append(event)
    LOG_FILE.write_text(json.dumps(logs, indent=2))

# ---------------- Audio helper ----------------
def play_audio_bytes_wav(audio_bytes: bytes, stop_event: threading.Event, loop_until_stop=False):
    """
    Convert wav bytes to numpy array (via pydub) and play using sounddevice.
    Blocks until playback ends or stop_event is set.
    If loop_until_stop is True, loops the audio continuously until stop_event is set.
    """
    if not PDUB_AVAILABLE or not SD_AVAILABLE:
        # fallback: do nothing but wait duration (approx)
        print("Audio libraries not available. Install pydub, numpy, and sounddevice.")
        return
    
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
        sample_width = seg.sample_width
        channels = seg.channels
        frame_rate = seg.frame_rate
        raw = seg.raw_data

        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sample_width, np.int16)
        arr = np.frombuffer(raw, dtype=dtype)
        if channels > 1:
            arr = arr.reshape((-1, channels))
        else:
            arr = arr.reshape((-1, 1))

        # normalize to float32 in [-1,1]
        max_val = float(2 ** (8*sample_width - 1))
        audio = arr.astype(np.float32) / max_val

        duration = len(audio) / frame_rate
        print(f"Audio: {len(audio)} samples, {frame_rate} Hz, {channels} channel(s), {duration:.2f}s duration")
        
        if loop_until_stop:
            # Loop continuously until stop_event is set
            print("Looping audio until next capture or stop...")
            chunk_time = 0.1  # Check every 100ms
            
            while not stop_event.is_set():
                # Play the audio
                sd.play(audio, samplerate=frame_rate)
                
                # Wait for this iteration to finish, checking stop_event
                elapsed = 0.0
                start_time = time.time()
                
                while elapsed < duration and not stop_event.is_set():
                    time.sleep(chunk_time)
                    elapsed = time.time() - start_time
                
                # Stop if stop_event is set
                if stop_event.is_set():
                    print("Audio looping stopped by user")
                    sd.stop()
                    return
                
                # Wait for playback to finish before looping
                try:
                    sd.wait()
                except:
                    pass
        else:
            # Play once
            print("Playing audio once...")
            sd.play(audio, samplerate=frame_rate)
            
            # Wait for playback to finish, but check stop_event periodically
            chunk_time = 0.1  # Check every 100ms
            elapsed = 0.0
            start_time = time.time()
            
            while elapsed < duration:
                if stop_event.is_set():
                    print("Audio playback stopped by user")
                    sd.stop()
                    return
                # Wait in small chunks so we can check stop_event
                time.sleep(chunk_time)
                elapsed = time.time() - start_time
            
            # Ensure playback is finished (wait for any remaining audio)
            try:
                sd.wait()
                print("Audio playback completed")
            except Exception as e:
                print(f"Error waiting for audio: {e}")
    except Exception as e:
        print(f"Error playing audio: {e}")
        traceback.print_exc()
    finally:
        # Make sure audio is stopped
        try:
            sd.stop()
        except:
            pass

# ---------------- Worker ----------------
class MonitorWorker(QtCore.QObject):
    status = QtCore.pyqtSignal(str)
    playback_started = QtCore.pyqtSignal()
    playback_finished = QtCore.pyqtSignal()
    new_emotion = QtCore.pyqtSignal(dict)
    new_clip_requested = QtCore.pyqtSignal()  # Signal to request new clip

    def __init__(self, prefs: Dict[str, Any]):
        super().__init__()
        self._prefs = prefs
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_playback = threading.Event()
        self._playback_lock = threading.Lock()
        self._request_new_clip = threading.Event()  # Flag to request new clip
        self._current_audio_data = None  # Store current audio data
        self._current_clip_info = None  # Store current clip info (prompt, seed, etc.)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.status.emit("Monitoring started")

    def stop(self):
        self._running = False
        self._stop_playback.set()
        self.status.emit("Stopping...")

    def skip_current(self):
        # signal to stop playback and request new clip
        print("Worker: skip_current() called - requesting new clip")
        self._stop_playback.set()
        self._request_new_clip.set()  # Request new clip
        # Also try to stop sounddevice directly
        if SD_AVAILABLE:
            try:
                sd.stop()
                print("Worker: Stopped sounddevice")
            except Exception as e:
                print(f"Worker: Error stopping sounddevice: {e}")
    
    def request_new_clip(self):
        """Request a new clip immediately"""
        self._request_new_clip.set()
        self._stop_playback.set()

    def _loop(self):
        api_base = self._prefs.get("api_base", DEFAULT_PREFS["api_base"])
        interval = int(self._prefs.get("poll_interval", 20))
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self._running:
            try:
                self.status.emit("Requesting clip...")
                resp = requests.get(f"{api_base}/api/process", timeout=15)
                if resp.status_code != 200:
                    consecutive_errors += 1
                    self.status.emit(f"API error {resp.status_code}")
                    if consecutive_errors >= max_consecutive_errors:
                        self.status.emit(f"API server unavailable. Please start the server at {api_base}")
                        time.sleep(10)  # Wait longer before retrying
                    else:
                        time.sleep(3)
                    continue
                
                # Reset error counter on success
                consecutive_errors = 0
                data = resp.json()
                self.new_emotion.emit(data.get("emotion", {}))
                
                # Store clip info for display
                self._current_clip_info = {
                    "prompt": data.get("prompt", "Unknown"),
                    "seed": data.get("seed", "N/A"),
                    "emotion": data.get("emotion", {}),
                    "timestamp": time.time()
                }
                self.new_clip_requested.emit()  # Emit signal with clip info
                
                audio_b64 = data.get("audio_b64")
                if audio_b64:
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                        self._current_audio_data = audio_bytes  # Store for potential reuse
                        audio_size = len(audio_bytes)
                        self.status.emit(f"Decoded audio ({audio_size} bytes), preparing to play...")
                        # prepare to play - clear stop event and new clip request
                        self._stop_playback.clear()
                        self._request_new_clip.clear()
                        self.playback_started.emit()
                        self.status.emit("Playing clip (looping)...")
                        
                        # Calculate when next capture should happen
                        next_capture_time = time.time() + interval
                        
                        # Play audio in a loop until next capture time, stop event, or new clip requested
                        while time.time() < next_capture_time and self._running and not self._stop_playback.is_set() and not self._request_new_clip.is_set():
                            # Play one iteration of the audio
                            play_audio_bytes_wav(audio_bytes, self._stop_playback, loop_until_stop=False)
                            
                            # Check if we should continue looping
                            if self._stop_playback.is_set() or self._request_new_clip.is_set():
                                break
                            
                            # Small delay to prevent tight loop
                            if time.time() < next_capture_time and not self._request_new_clip.is_set():
                                time.sleep(0.05)
                        
                        # If new clip requested (skip button), break to get new clip
                        if self._request_new_clip.is_set():
                            self.playback_finished.emit()
                            self.status.emit("Requesting new clip...")
                            continue  # Go back to top of loop to get new clip
                        # If stopped by user, emit finished
                        elif self._stop_playback.is_set():
                            self.playback_finished.emit()
                            self.status.emit("Playback stopped")
                        else:
                            self.playback_finished.emit()
                            self.status.emit("Ready for next capture")
                    except Exception as e:
                        self.status.emit(f"Error playing audio: {str(e)}")
                        traceback.print_exc()
                        self.playback_finished.emit()
                else:
                    self.status.emit("No audio in response")
                    # Still wait the interval
                    t0 = time.time()
                    while time.time() - t0 < interval and self._running:
                        time.sleep(0.2)
            except requests.exceptions.ConnectionError as e:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    self.status.emit(f"Cannot connect to API server at {api_base}. Please start api_server.py first.")
                    time.sleep(10)  # Wait longer before retrying
                else:
                    self.status.emit(f"Connection error (attempt {consecutive_errors}/{max_consecutive_errors}). Retrying...")
                    time.sleep(5)
            except requests.exceptions.Timeout as e:
                self.status.emit("Request timed out. Retrying...")
                time.sleep(3)
            except Exception as e:
                consecutive_errors += 1
                error_msg = str(e)
                if "Connection refused" in error_msg or "actively refused" in error_msg:
                    if consecutive_errors >= max_consecutive_errors:
                        self.status.emit(f"API server not running. Start it with: python api_server.py")
                    else:
                        self.status.emit(f"Server not available (attempt {consecutive_errors}/{max_consecutive_errors})...")
                    time.sleep(5)
                else:
                    traceback.print_exc()
                    self.status.emit(f"Error: {error_msg}")
                    time.sleep(3)
        self.status.emit("Monitoring stopped")

# ---------------- Camera helper (OpenCV -> QImage) ----------------
class CameraWidget(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border: 2px solid #e6eefc;
                border-radius: 8px;
                font-size: 16px;
                color: white;
            }
        """)
        self.setText("Camera preview will appear here")
        self.cap = None
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._grab_frame)
        self._is_running = False

    def start(self):
        if not OPENCV_AVAILABLE:
            self.setText("OpenCV not installed\nInstall: pip install opencv-python")
            return
        
        # Stop any existing camera first
        self.stop()
        
        # Try to open camera with multiple methods
        camera_index = 0
        for attempt in range(3):  # Try camera indices 0, 1, 2
            try:
                if attempt == 0:
                    # Try with DirectShow on Windows
                    self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
                else:
                    # Try without DirectShow
                    self.cap = cv2.VideoCapture(camera_index)
                
                if self.cap.isOpened():
                    # Test if we can actually read a frame
                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        print(f"Camera opened successfully at index {camera_index}")
                        self._is_running = True
                        # Start the timer to update frames
                        if not self.timer.isActive():
                            self.timer.start(33)  # Update every 33ms (~30 FPS)
                        return
                    else:
                        self.cap.release()
                        self.cap = None
                
                # Try next camera index
                camera_index += 1
            except Exception as e:
                print(f"Error opening camera {camera_index}: {e}")
                if self.cap:
                    try:
                        self.cap.release()
                    except:
                        pass
                    self.cap = None
                camera_index += 1
        
        # If we get here, no camera worked
        self.setText("Camera not available\n\nPlease check:\n• Camera is connected\n• No other app is using it\n• Camera permissions are granted")
        self.cap = None

    def stop(self):
        self.timer.stop()
        self._is_running = False
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
        # clear image
        self.clear()
        self.setText("Camera off")

    def _grab_frame(self):
        if not self.cap or not self._is_running:
            return
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                # Try to reopen camera
                print("Failed to read frame, attempting to reopen camera...")
                self.start()
                return
            
            # convert BGR->RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            
            # Create QImage from frame data (make a copy to ensure data persists)
            image = QtGui.QImage(frame_rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888).copy()
            
            # Scale to fit widget while maintaining aspect ratio
            pix = QtGui.QPixmap.fromImage(image)
            scaled_pix = pix.scaled(
                self.size(), 
                QtCore.Qt.AspectRatioMode.KeepAspectRatio, 
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled_pix)
        except Exception as e:
            print(f"Error grabbing frame: {e}")
            # Try to restart camera on error
            if self._is_running:
                self.start()

# ---------------- Main UI ----------------
class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PersonD — Simple Player")
        self.setMinimumSize(900, 600)
        # Set a reasonable default size
        self.resize(1000, 700)
        self.prefs = load_prefs()

        # Styling (clean with better scaling - larger text)
        self.setStyleSheet("""
            QWidget { 
                background: #f7fbff; 
                font-family: Inter, Arial, sans-serif; 
                font-size: 16px;
            }
            QPushButton { 
                padding: 14px 24px; 
                border-radius: 8px; 
                font-size: 16px;
                font-weight: 600;
                min-height: 50px;
                min-width: 140px;
            }
            #startBtn { 
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #4f46e5); 
                color: white; 
                font-weight: 600;
                font-size: 18px;
                padding: 16px 28px;
            }
            #stopBtn { 
                background: #e6eefc; 
                color: #0f172a; 
                font-size: 18px;
                padding: 16px 28px;
            }
            #consentBtn { 
                background: #fff3b0; 
                color: #0f172a; 
                font-size: 17px;
                padding: 14px 24px;
                font-weight: 600;
            }
            #skipBtn { 
                background: #ff6b6b; 
                color: white; 
                font-size: 17px;
                padding: 14px 24px;
                font-weight: 600;
            }
            #likeBtn { 
                background: #34d399; 
                color: white; 
                font-size: 17px;
                padding: 14px 24px;
                font-weight: 600;
            }
            QLabel#statusLabel { 
                color: #334155; 
                font-size: 22px; 
                font-weight: 600;
                padding: 15px 0px;
                text-align: center;
            }
            QGroupBox { 
                border: 1px solid #e6eefc; 
                border-radius: 10px; 
                padding: 18px; 
                background: white;
                font-size: 17px;
                font-weight: 600;
                margin-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                font-size: 18px;
                font-weight: 600;
            }
            QListWidget {
                font-size: 15px;
                padding: 10px;
            }
            QListWidget::item {
                padding: 8px;
                min-height: 28px;
            }
            QLabel {
                font-size: 16px;
            }
        """)

        # Layouts
        main = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()
        right = QtWidgets.QVBoxLayout()
        main.addLayout(left, 2)
        main.addLayout(right, 1)

        # LEFT: Controls (camera removed)
        controls_box = QtWidgets.QGroupBox("Controls")
        cb_layout = QtWidgets.QVBoxLayout()
        controls_box.setLayout(cb_layout)

        # Camera consent button removed - no camera preview needed

        # Start/Stop
        hbtn = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start Monitoring")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.on_start)

        self.stop_btn = QtWidgets.QPushButton("Stop Monitoring")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self.on_stop)
        self.stop_btn.setEnabled(False)

        hbtn.addWidget(self.start_btn)
        hbtn.addWidget(self.stop_btn)
        cb_layout.addLayout(hbtn)

        # status
        self.status_label = QtWidgets.QLabel("Idle")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel#statusLabel {
                color: #334155;
                font-size: 22px;
                font-weight: 600;
                padding: 15px 0px;
            }
        """)
        cb_layout.addWidget(self.status_label)
        left.addWidget(controls_box)

        # RIGHT: Playback controls & recent events
        playback_box = QtWidgets.QGroupBox("Playback")
        pb_layout = QtWidgets.QVBoxLayout()
        playback_box.setLayout(pb_layout)

        # info
        self.info_label = QtWidgets.QLabel("No clip playing")
        self.info_label.setWordWrap(True)
        pb_layout.addWidget(self.info_label)

        # skip/like row (hidden until playback)
        sk_layout = QtWidgets.QHBoxLayout()
        self.skip_btn = QtWidgets.QPushButton("Skip")
        self.skip_btn.setObjectName("skipBtn")
        self.skip_btn.clicked.connect(self.on_skip)
        self.skip_btn.setEnabled(False)

        self.like_btn = QtWidgets.QPushButton("Like")
        self.like_btn.setObjectName("likeBtn")
        self.like_btn.clicked.connect(self.on_like)
        self.like_btn.setEnabled(False)

        sk_layout.addWidget(self.skip_btn)
        sk_layout.addWidget(self.like_btn)
        pb_layout.addLayout(sk_layout)
        
        # Song history display below skip/like buttons
        self.song_history_label = QtWidgets.QLabel("Song History")
        self.song_history_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #334155;
                padding: 8px 0px;
            }
        """)
        pb_layout.addWidget(self.song_history_label)
        
        self.song_history_list = QtWidgets.QListWidget()
        self.song_history_list.setStyleSheet("""
            QListWidget {
                font-size: 14px;
                padding: 8px;
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
            }
            QListWidget::item {
                padding: 6px;
                min-height: 32px;
                border-bottom: 1px solid #e2e8f0;
            }
            QListWidget::item:last {
                border-bottom: none;
            }
        """)
        pb_layout.addWidget(self.song_history_list)

        # recent events
        events_box = QtWidgets.QGroupBox("Recent Events")
        events_layout = QtWidgets.QVBoxLayout()
        self.events_list = QtWidgets.QListWidget()
        events_layout.addWidget(self.events_list)
        events_box.setLayout(events_layout)

        right.addWidget(playback_box)
        right.addWidget(events_box)

        # load initial logs
        self._load_events()

        # Worker
        self.worker = MonitorWorker(self.prefs)
        self.worker.status.connect(self._set_status)
        self.worker.playback_started.connect(self._on_playback_started)
        self.worker.playback_finished.connect(self._on_playback_finished)
        self.worker.new_emotion.connect(self._on_new_emotion)
        self.worker.new_clip_requested.connect(self._on_new_clip)

        # keep track of playback state
        self._is_playing = False

    # ---------- UI handlers ----------
    # Camera consent handler removed - no camera needed

    def on_start(self):
        # Check if API server is available before starting
        api_base = self.prefs.get("api_base", DEFAULT_PREFS["api_base"])
        try:
            resp = requests.get(f"{api_base}/api/process", timeout=5)
            # If we get any response (even error), server is running
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            reply = QtWidgets.QMessageBox.question(
                self, 
                "API Server Not Available",
                f"Cannot connect to API server at {api_base}.\n\n"
                f"Please start the API server first by running:\n"
                f"python api_server.py\n\n"
                f"Do you want to start monitoring anyway? (It will retry automatically)",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
        
        self.worker._prefs = self.prefs
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        append_log({"ts": time.time(), "event": "monitor_start"})

    def on_stop(self):
        self.worker.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        append_log({"ts": time.time(), "event": "monitor_stop"})

    def on_skip(self):
        # Request new clip when skip is clicked
        print("Skip button clicked - requesting new clip!")
        if self._is_playing or self.skip_btn.isEnabled():
            # Get current clip info before requesting new one
            current_info = self.worker._current_clip_info
            if current_info:
                # Add to history as skipped
                prompt = current_info.get("prompt", "Unknown")
                seed = current_info.get("seed", "N/A")
                ts = time.strftime("%H:%M:%S", time.localtime())
                self._add_to_history(f"[SKIPPED] {prompt} (Seed: {seed}) - {ts}")
            
            print("Requesting new clip...")
            self.worker.skip_current()
            append_log({"ts": time.time(), "event": "skip", "clip_info": current_info})
            self._set_status("Skipped - Loading new clip...")
            # Keep buttons enabled briefly, they'll be updated when new clip starts
        else:
            print("Skip button clicked but not playing")
            self._set_status("No clip playing to skip")

    def on_like(self):
        # Like keeps playing the same clip
        print("Like button clicked - keeping current clip!")
        if self._is_playing or self.like_btn.isEnabled() or self.info_label.text() != "No clip playing":
            # Get current clip info
            current_info = self.worker._current_clip_info
            if current_info:
                # Add to history as liked
                prompt = current_info.get("prompt", "Unknown")
                seed = current_info.get("seed", "N/A")
                ts = time.strftime("%H:%M:%S", time.localtime())
                self._add_to_history(f"[LIKED] {prompt} (Seed: {seed}) - {ts}")
            
            print("Liking current clip - will continue playing...")
            append_log({"ts": time.time(), "event": "like", "clip_info": current_info})
            self._set_status("Liked - Continuing to play")
            # Show brief feedback without blocking
            self.info_label.setText("✓ Liked! (Continuing to play)")
            QtCore.QTimer.singleShot(2000, lambda: self.info_label.setText("Playing..." if self._is_playing else "No clip playing"))
            # Don't stop playback - keep looping the same clip
        else:
            print("Like button clicked but not playing")
            self._set_status("No clip playing to like")

    # ---------- Worker signals ----------
    @QtCore.pyqtSlot(str)
    def _set_status(self, t: str):
        self.status_label.setText(t)

    @QtCore.pyqtSlot()
    def _on_playback_started(self):
        self._is_playing = True
        self.skip_btn.setEnabled(True)
        self.like_btn.setEnabled(True)
        self.info_label.setText("Playing...")

    @QtCore.pyqtSlot()
    def _on_playback_finished(self):
        # Only disable buttons if we're actually stopping (not requesting new clip)
        if not self.worker._request_new_clip.is_set():
            self._is_playing = False
            self.skip_btn.setEnabled(False)
            self.like_btn.setEnabled(False)
            self.info_label.setText("No clip playing")
        self._load_events()

    @QtCore.pyqtSlot(dict)
    def _on_new_emotion(self, emo: dict):
        # show small preview of emotion
        self.info_label.setText(f"Emotion: {emo}")
        append_log({"ts": time.time(), "event": "emotion", "payload": emo})
        self._load_events()
    
    @QtCore.pyqtSlot()
    def _on_new_clip(self):
        # New clip received - add to history
        clip_info = self.worker._current_clip_info
        if clip_info:
            prompt = clip_info.get("prompt", "Unknown")
            seed = clip_info.get("seed", "N/A")
            ts = time.strftime("%H:%M:%S", time.localtime())
            self._add_to_history(f"[NEW] {prompt} (Seed: {seed}) - {ts}")
    
    def _add_to_history(self, text):
        """Add a song to the history list"""
        self.song_history_list.insertItem(0, text)  # Add to top
        # Keep only last 10 items
        while self.song_history_list.count() > 10:
            self.song_history_list.takeItem(self.song_history_list.count() - 1)

    def _load_events(self):
        self.events_list.clear()
        if LOG_FILE.exists():
            try:
                logs = json.loads(LOG_FILE.read_text())
                for e in list(reversed(logs))[:20]:
                    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("ts", time.time())))
                    ev = e.get("event", "") or e
                    self.events_list.addItem(f"{ts} — {ev}")
            except:
                pass

# ---------------- Entrypoint ----------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
