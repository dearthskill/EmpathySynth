# PersonD - Desktop Audio Player

A desktop application for monitoring emotions and playing generated audio clips.

## Prerequisites

1. **Python 3.11+** installed
2. **Virtual environment** activated (`.venv`)
3. **Required packages** installed:
   ```bash
   pip install PyQt6 opencv-python requests pydub numpy sounddevice soundfile flask flask-cors
   ```

## How to Run

### Step 1: Start the API Server

Open a **first terminal/command prompt** and run:

```bash
# Navigate to the project directory
cd C:\Users\llath\OneDrive\Desktop\empathysynth\bandi_kodikon

# Activate virtual environment (if not already activated)
.\.venv\Scripts\Activate.ps1

# Start the API server
cd app
python api_server.py
```

You should see output like:
```
 * Running on http://127.0.0.1:5000
 * Debug mode: on
```

**Keep this terminal open** - the server needs to keep running.

### Step 2: Start the Desktop App

Open a **second terminal/command prompt** and run:

```bash
# Navigate to the project directory
cd C:\Users\llath\OneDrive\Desktop\empathysynth\bandi_kodikon

# Activate virtual environment (if not already activated)
.\.venv\Scripts\Activate.ps1

# Run the desktop app
cd app
python desktop_app_webview.py
```

The desktop application window should open.

## Testing Guide

### Test 1: Camera Consent Button

1. In the desktop app, look for the yellow **"Give Consent to Turn Camera On"** button
2. Click it
3. A dialog will appear asking for permission
4. Click **"Yes"**
5. **Expected Result:**
   - Button text changes to "Camera Consent Given ✓"
   - Button turns green and becomes disabled
   - A confirmation message appears
   - Camera preview should appear in the camera widget area (if camera is available)

### Test 2: Start Monitoring

1. Click the **"Start Monitoring"** button (blue gradient button)
2. **Expected Result:**
   - Button becomes disabled
   - "Stop Monitoring" button becomes enabled
   - Status label shows "Monitoring started"
   - The app will start requesting audio clips from the API server

### Test 3: Audio Playback

1. After starting monitoring, wait a few seconds
2. The app will automatically request and play audio
3. **Expected Result:**
   - Status shows "Requesting clip..."
   - Then "Decoded audio (X bytes), preparing to play..."
   - Then "Playing clip..."
   - You should **hear audio** playing
   - Console will show debug messages like:
     ```
     Playing audio: X samples, 44100 Hz, 1 channel(s)
     Audio duration: 2.00 seconds
     ```

### Test 4: Skip Button

1. While audio is playing, click the red **"Skip"** button
2. **Expected Result:**
   - Audio stops immediately
   - Status shows "Skipped current clip"
   - Skip and Like buttons become disabled
   - Info label shows "Clip skipped"
   - Console shows "Audio playback stopped by user"

### Test 5: Like Button

1. While audio is playing, click the green **"Like"** button
2. **Expected Result:**
   - Info label shows "✓ Liked!"
   - Status shows "Liked current clip"
   - After 2 seconds, info label returns to normal
   - Event is logged

### Test 6: Stop Monitoring

1. Click the **"Stop Monitoring"** button
2. **Expected Result:**
   - Monitoring stops
   - "Start Monitoring" button becomes enabled
   - "Stop Monitoring" button becomes disabled
   - Status shows "Monitoring stopped"

## Troubleshooting

### Issue: "Cannot connect to API server"

**Solution:** Make sure the API server is running in a separate terminal. Check that it's running on `http://127.0.0.1:5000`

### Issue: "No audio heard"

**Possible causes:**
1. Check your system volume
2. Check that audio libraries are installed: `pip install pydub numpy sounddevice`
3. Check console output for error messages
4. Verify the API server is returning audio data

### Issue: "Camera not available"

**Possible causes:**
1. Camera might be in use by another application
2. OpenCV might not be installed: `pip install opencv-python`
3. Camera permissions might be needed (Windows may prompt)

### Issue: Buttons not working

**Solution:** 
- Make sure you've started monitoring first
- Skip/Like buttons only work when audio is actively playing
- Check the status label for current state

## Quick Test Checklist

- [ ] API server starts without errors
- [ ] Desktop app opens successfully
- [ ] Camera consent button works and camera turns on
- [ ] Start monitoring button works
- [ ] Audio plays when monitoring starts
- [ ] Skip button stops audio immediately
- [ ] Like button shows feedback
- [ ] Stop monitoring button works
- [ ] Status messages update correctly

## File Locations

- **API Server:** `app/api_server.py`
- **Desktop App:** `app/desktop_app_webview.py`
- **Logs:** Stored in `~/.persond/` directory (in your home folder)
  - `events_log.json` - Event logs
  - `prefs.json` - User preferences

## Notes

- The API server must be running before starting the desktop app
- Audio playback uses `sounddevice` library
- Camera uses OpenCV (`opencv-python`)
- All data is stored locally on your machine

