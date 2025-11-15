# Quick Start Guide

## Run in 2 Steps

### Terminal 1 - Start API Server
```powershell
cd C:\Users\llath\OneDrive\Desktop\empathysynth\bandi_kodikon
.\.venv\Scripts\Activate.ps1
cd app
python api_server.py
```

### Terminal 2 - Start Desktop App
```powershell
cd C:\Users\llath\OneDrive\Desktop\empathysynth\bandi_kodikon
.\.venv\Scripts\Activate.ps1
cd app
python desktop_app_webview.py
```

## Quick Test

1. **Click "Give Consent to Turn Camera On"** → Camera should start
2. **Click "Start Monitoring"** → Monitoring begins
3. **Wait for audio** → You should hear audio playing
4. **Click "Skip"** while audio plays → Audio stops
5. **Click "Like"** while audio plays → Shows "✓ Liked!"

## If Something Doesn't Work

- **No audio?** Check system volume and console output
- **Camera not working?** Check if another app is using it
- **Connection error?** Make sure API server is running in Terminal 1

