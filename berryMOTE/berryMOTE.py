'''
berryMOTE
v2.0.0
Version Name: Goose Berry (V2)
By Tyson Shannon

A server to host a remote control for your computer
(Linux, Windows and macOS)
'''
import argparse
import os
import socket
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Remote import Remote


VERSION = "2.0.0"


#environment detection to determine if os uses wayland or not
def is_wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) and not os.environ.get("DISPLAY")


def resource_path(relative_path):
    #when bundled with PyInstaller
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        #when running from source, look next to this file
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def remote_port():
    try:
        port = int(os.environ.get("BERRYMOTE_PORT", "5000"))
    except ValueError:
        return 5000
    return port if 1 <= port <= 65535 else 5000


def _say(message):
    """Print when a console is attached (PyInstaller --windowed has none)."""
    stream = sys.stdout
    if stream is None:
        return
    try:
        print(message, flush=True)
    except Exception:
        pass


def _ensure_std_streams():
    """Give argparse and logging something to write to in windowed builds."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def _qt_check():
    """Load Qt and a platform plugin without opening a window."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.quit()


def self_test():
    """Start the remote headlessly and verify the packaged data files."""
    import json
    import urllib.request

    _say("berryMOTE " + VERSION)
    try:
        _qt_check()
    except Exception as exc:
        _say("FAIL: Qt platform plugin: " + str(exc))
        return 1
    _say("ok: Qt platform plugin")

    remote = Remote(host="127.0.0.1", port=0)
    try:
        remote.start()
    except Exception as exc:
        _say("FAIL: could not start the remote server: " + str(exc))
        remote.shutdown()
        return 1

    base = "http://127.0.0.1:" + str(remote.port)
    _say("remote: " + base)
    _say(
        "input backend: "
        + (remote.backend.name if remote.backend else "unavailable")
    )
    if remote.backend_error:
        _say("input detail: " + remote.backend_error.splitlines()[0])
    _say("audio backend: " + (remote.audio.backend or "unavailable"))

    checks = [("application icon", not QIcon(resource_path("berryLogo.png")).isNull())]
    try:
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            checks.append(
                ("health endpoint", response.status == 200 and bool(health.get("ok")))
            )
        except Exception as exc:
            _say("FAIL: health endpoint: " + str(exc))
            return 1

        try:
            with urllib.request.urlopen(base + "/", timeout=5) as response:
                page = response.read()
            checks.append(
                (
                    "remote page and templates",
                    response.status == 200 and b"berryMOTE" in page,
                )
            )
        except Exception as exc:
            _say("FAIL: remote page: " + str(exc))
            return 1

        try:
            with urllib.request.urlopen(
                base + "/static/berryLogo.png", timeout=5
            ) as response:
                logo = response.read()
            checks.append(
                ("static files", response.status == 200 and bool(logo))
            )
        except Exception as exc:
            _say("FAIL: static files: " + str(exc))
            return 1

        try:
            with urllib.request.urlopen(base + "/login", timeout=5) as response:
                login_page = response.read()
            checks.append(
                (
                    "login template",
                    response.status == 200 and b"berryMOTE" in login_page,
                )
            )
        except Exception as exc:
            _say("FAIL: login template: " + str(exc))
            return 1

        checks.append(
            ("window image", os.path.isfile(resource_path("berryTV.png")))
        )

        failed = False
        for name, ok in checks:
            _say(("ok: " if ok else "FAIL: ") + name)
            failed = failed or not ok
        return 1 if failed else 0
    finally:
        remote.shutdown()


#interface
class gui(QWidget):
   def __init__(self, parent = None):
      super(gui, self).__init__(parent)

      #start remote
      self.remote_error = ""
      self.remote = Remote(
          port=remote_port(),
          pin=os.environ.get("BERRYMOTE_PIN", "").strip(),
      )
      try:
          self.remote.start()
      except OSError as exc:
          self.remote_error = str(exc)
          _say("berryMOTE: could not start remote: " + str(exc))

      #intro screen
      width = 1200
      height = 400
      self.setFixedSize(width, height)
      self.setWindowFlag(Qt.FramelessWindowHint)
      self.setStyleSheet("background-color: #5E17EB;")
      layout = QHBoxLayout(self)
      layout.setContentsMargins(50, 50, 50, 50)
      layout.setSpacing(20)
      #left side
      self.label = QLabel(self)
      self.OG_pixmap = QPixmap(resource_path("berryTV.png"))
      pixmap = self.OG_pixmap.scaledToWidth(width // 2, Qt.SmoothTransformation)
      self.label.setPixmap(pixmap)
      self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
      layout.addWidget(self.label)
      #right side
      self.ip_label = QLabel(self)
      ip_font = QFont("Arial", 20)
      self.ip_label.setFont(ip_font)
      self.ip_label.setStyleSheet("color: #FFFFFF;")
      self.ip_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
      if self.remote_error:
          self.ip_label.setText("Remote could not start:\n" + self.remote_error)
      else:
          self.ip_label.setText(
              "Remote: http://" + self.get_local_ip() + ":" + str(self.remote.port)
          )
      #right side vertical wrap
      right_layout = QVBoxLayout()
      right_layout.addStretch()
      right_layout.addWidget(self.ip_label)
      right_layout.addStretch()
      right_container = QWidget()
      right_container.setLayout(right_layout)
      layout.addWidget(right_container)
      #shutdown button
      self.shutdown_button = QPushButton("Shutdown")
      self.shutdown_button.setFixedSize(200, 40)
      self.shutdown_button.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #5E17EB;
                border-radius: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ddd;
            }
      """)
      self.shutdown_button.clicked.connect(self.shutdown_app)
      right_layout.addWidget(self.shutdown_button)

      self.setLayout(layout)

   def get_local_ip(self):
       #get ip for the remote control webserver
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      try:
         s.connect(("8.8.8.8", 80))  # Connects to Google's DNS to get local IP
         ip = s.getsockname()[0]
      except Exception:
         ip = "Unable to get IP"
      finally:
         s.close()
      return ip

   def shutdown_app(self):
       self.remote.shutdown()
       self.close()

def main():
   _ensure_std_streams()
   parser = argparse.ArgumentParser(
       prog="berryMOTE",
       description="A local network remote control for your computer.",
   )
   parser.add_argument(
       "--self-test",
       "--doctor",
       dest="self_test",
       action="store_true",
       help="start the remote headlessly, verify the install, then exit",
   )
   parser.add_argument(
       "--version",
       action="version",
       version="%(prog)s " + VERSION,
   )
   args = parser.parse_args()

   if args.self_test:
       return self_test()

   if is_wayland():
       #force Qt to use X11 for the GUI window if os uses wayland
       os.environ["QT_QPA_PLATFORM"] = "xcb"

   app = QApplication([sys.argv[0]])
   app.setApplicationName("berryMOTE")
   app.setApplicationDisplayName("berryMOTE")
   app.setDesktopFileName("berryMOTE")
   app.setWindowIcon(QIcon(resource_path("berryLogo.png")))
   introWindow = gui()
   introWindow.show()
   return app.exec()

# Run the app
if __name__ == "__main__":
    raise SystemExit(main())
