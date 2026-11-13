# berryMOTE
A remote controller for your computer hosted on a local server and accessed by any browser on any device on the same network<br/>
Same remote functionality as seen in the [berryTV](https://github.com/Tyson-Shannon/berryTV) project that turns your computer into a smart TV <br/>

The remote includes a trackpad with adjustable sensitivity, tap and long-press clicks, scrolling, a mobile-friendly text field, volume controls, and optional PIN protection.<br/>

berryMOTE uses PySide6 (LGPL) for its desktop window, along with Flask and pynput.<br/>

| Version  | Version Name | Release Date | Download Link | OS Supported |
| --- | --- | --- | --- | --- |
| v1.0.0 | June Berry | 2025-06-21 | [https://github.com/Tyson-Shannon/berryMOTE/releases/download/v1.0.0/berryMOTE.exe](https://github.com/Tyson-Shannon/berryMOTE/releases/download/v1.0.0/berryMOTE.exe) | Windows |
| v1.1.0 | June Berry | 2025-08-03 | [https://github.com/Tyson-Shannon/berryMOTE/releases/download/v1.1.0/berryMOTE.exe](https://github.com/Tyson-Shannon/berryMOTE/releases/download/v1.1.0/berryMOTE.exe) | Windows, Linux* |

*On Linux use the Linux release binary or run from source. The Windows .exe is not supported under Wine.<br/>
*Wayland on Linux can cause some functionality issues that require extra steps (see common errors below)<br/><br/>

![image](https://github.com/user-attachments/assets/8ad0834a-85b5-48aa-976d-4b03fa165142) <br/><br/>
<img src="https://github.com/user-attachments/assets/4022920a-eab3-4a3e-895a-d09decce7954" alt="remote" style="width:50%; height:auto;">
<br/><br/>

## Run from source
```bash
git clone https://github.com/Tyson-Shannon/berryMOTE.git
cd berryMOTE
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python berryMOTE/berryMOTE.py
```

The app window shows the URL to open on your phone or another device on the same network.<br/><br/>

## Build a standalone app
The release build is a single-file executable. Build it on the same operating
system you want to run it on; PyInstaller does not cross-compile.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt

python scripts/build.py             # single-file executable
python scripts/build.py --onedir    # executable plus support folder
python scripts/build.py --console   # debug build with a console window
```

The output is written to `dist/`:

- Windows: `dist/berryMOTE.exe`
- Linux: `dist/berryMOTE`

The single-file build extracts its libraries to a temporary directory at
launch, so it starts a little slower than the `--onedir` build. On minimal
Linux installs, Qt also needs a few system libraries:

```bash
sudo apt install libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0
```

Verify a build with its built-in headless self-test:

```bash
./dist/berryMOTE --self-test
```

On Windows:

```powershell
dist\berryMOTE.exe --self-test
```

The GitHub Actions workflow in `.github/workflows/build.yml` builds and
self-tests both platforms and uploads the executables and checksums. Pushing a
`v*` tag also attaches them to a GitHub release. Linux builds target
Ubuntu 22.04 / glibc 2.35 or newer. Unsigned Windows executables may trigger
SmartScreen warnings.

Third-party license notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).<br/><br/>

## Common Errors
**App runs but remote doesn't move or change anything on host device?** <br/>
Most modern Linux OS use a communication protocol and a set of libraries called **Wayland** which defines how applications and the display server communicate to render graphics and handle user input. Unlike X11, Wayland has a built in security feature to prevent malware from controlling or logging your keyboard which can also block our remote functionality. berryMOTE has Wayland support through uinput, but you may need to install a helper and grant access to `/dev/uinput`. <br/>
```
# Preferred: dotool (no daemon; https://sr.ht/~geb/dotool)
sudo usermod -aG input "$USER"
# then log out and back in

# Or: ydotool
sudo apt install ydotool
sudo usermod -aG input "$USER"
sudo systemctl enable --now ydotoold
# then log out and back in
```
berryMOTE automatically uses dotool or native uinput when available, then falls back to ydotool.<br/>
<br/>

## Configuration
- `BERRYMOTE_PORT` changes the web server port (default `5000`).
- `BERRYMOTE_PIN` enables PIN protection for the remote.
- `BERRYMOTE_INPUT_BACKEND` forces an input backend (`pynput`, `dotool`, `uinput`, or `ydotool`).
<br/>
