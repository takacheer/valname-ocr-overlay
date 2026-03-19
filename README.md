# VALORANT Name OCR Overlay

This tool uses OCR to read player names from the VALORANT game screen in real-time and displays a profile UI on your stream overlay (supposed to use it on OBS). 

It features a dedicated Web Control Panel that allows you to intuitively manage player registrations, edit profiles, and configure OCR settings directly from your browser.

> ⚠️ **Disclaimer:** This application is intended for users who have some knowledge of Python (or general programming).
> ⚠️ **Language Support:** By default, the OCR engine is configured to read only English and Japanese. Please edit the code as needed if you wish to add support for other languages.

## ✨ Features

- **Real-time OCR Detection**: Rapidly captures the name display area in-game and detects player names using EasyOCR. (WORKS FASTEST WITH CUDA)
- **Fuzzy Matching**: Automatically compensates for minor typos or blurry text during detection to match registered players accurately.
- **Rich Overlay**:
  - Stylish design inspired by official VALORANT tournaments
  - Smooth slide-in and bounce animations
  - Auto-scaling for exceptionally long names
  - Supports player icons, rank images, and custom subtexts
- **Web Control Panel**:
  - Accessible via `http://127.0.0.1:5000/control`
  - Toggle monitoring status (by marking chechbox) for up to 10 players simultaneously
  - Edit player information (display name, icon path, rank image, etc.) with a real-time preview
- **Debug Mode**: Test your OBS overlay UI and animations using dummy data without needing to launch the game
- **Global Hotkeys**: Instantly toggle the system ON/OFF or switch settings using keyboard shortcuts, even while playing

## 🚀 Installation

1. **Install Python**
   Ensure that you have Python 3.x installed on your system.
2. **Install Required Libraries**
   Open your command prompt or terminal, navigate to the project folder, and run the following command:
   ```bash
   pip install -r requirements.txt
   ```

## 🎮 Usage

1. **Launch the Program**
   Run the following command in your terminal to start the tool:
   ```bash
   python app.py
   ```

2. **Access the Control Panel**
   Open your web browser and go to the following URL to configure your settings:
   `http://127.0.0.1:5000/control`
   - Here, you can register players, specify image paths, and toggle your active OCR targets.

3. **Setup in OBS Studio (or corresponding streaming app)**
   1. Add a New **Browser Source** to your OBS scene
   2. Enter the following settings:
      - URL: `http://127.0.0.1:5000/`
      - Width: ``1920``
      - Width: ``1080``
   3. The UI will appear at the bottom center when a player is detected. Prefably use debug mode to adjust position!
   4. Global Hotkeys
      You can control the application using the following shortcuts at any time:
| Key | Function |
| :--- | :--- |
| `Shift + F7` | Start / Stop OCR Capturing |
| `Shift + F8` | Cycle Capture Interval (Speed) |
| `Shift + F9` | Switch Target Monitor |
| `Shift + F10` | Switch Capture Region Mode (OBS Mode / Non-OBS Mode) |
| `Shift + F11` | Enable / Disable Debug Mode (Displays Dummy UI) |
| `Shift + F12` | Cycle Dummy Player (Only works in Debug Mode) |
| `Ctrl + C` | Exit the program entirely (Use in terminal) |

## ⚠️ Important Notes
- **Resolution**: The default capture coordinates are intended to work on a 1920x1080 resolution.
- **Display Mode**: Set VALORANT graphic setting to "**Windowed Fullscreen (Borderless)**
- **Third-party Tool Usage**: This tool does not violate any rules of VALORANT. However, the use of any third-party tools is always at your own risk.

## 📜 License
This project is licensed under the MIT License.