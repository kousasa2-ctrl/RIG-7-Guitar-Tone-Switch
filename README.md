# RIG-7-Guitar-Tone-Switch

Windows desktop app for controlling Guitar Rig 7 track loading via Wi-Fi (Flask), optional Bluetooth serial commands, and a live FFT visualizer.

## Features
- `customtkinter` UI with startup safety check for `folder_btn.png`.
- Flask endpoints:
  - `GET /list` for allowed audio files (`.mp3`, `.wav`, `.flac`, `.ogg`).
  - `GET /play/<filename>` to trigger automation.
- Optional serial command listener (`1` = next track).
- `PyAutoGUI` automation for Guitar Rig 7 file loading.
- Pygame FFT visualizer driven by microphone / stereo mix input.
- Dual logging to GUI and `app_debug.log`.

## Install
```bash
pip install customtkinter flask pyautogui pyserial pygame numpy sounddevice
```

## Run
```bash
python app.py
```

## First-time setup
1. Place `folder_btn.png` in the same folder as `app.py`.
2. In the app, use **Browse** to choose your music folder.
3. Click **Start Services**.
4. (Optional) Enter a COM port (for example, `COM5`) before starting services.
