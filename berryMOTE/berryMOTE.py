'''
berryMOTE
v1.1.0
Version Name: June Berry (V1)
By Tyson Shannon

A server to host a remote control for you're computer 
(Linux compatible)
'''
import sys
import os
import platform
import subprocess
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import socket
from flask import Flask, render_template_string, request
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key
import threading

#environment detection to determine if os uses wayland or not
def is_wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) and not os.environ.get("DISPLAY")

#ydotool wayland functions
def ydotool_cmd(*args):
    #Run ydotool command if available
    try:
        subprocess.run(["ydotool"] + list(args), check=True)
    except Exception as e:
        print("ydotool error:", e)
def ydotool_move(dx, dy):
    #move relative
    ydotool_cmd("mousemove", "--", str(dx), str(dy))
def ydotool_click(button="left"):
    if button == "left":
        ydotool_cmd("click", "0")
    else:
        ydotool_cmd("click", "1")
def ydotool_type(text):
    #type text one character at a time
    for ch in text:
        ydotool_cmd("type", ch)

#get resource path
def resource_path(relative_path):
    try:
        #when bundled with PyInstaller
        base_path = sys._MEIPASS
    except AttributeError:
        #when running in a normal Python environment
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

#remote
class Remote:
    def __init__(self):
        self.app = Flask(__name__)
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.shutdown_event = threading.Event()

        # HTML template with virtual trackpad and live keystroke input
        self.HTML_TEMPLATE = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <link rel="icon" href="/static/berryLogo.png" type="image/png">
            <title>berryMOTE</title>
            <style>
                body {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background-color: #f4f4f4;
                    margin: 0;
                    font-family: Arial, sans-serif;
                }
                .container {
                    text-align: center;
                    width: 90%;
                    max-width: 400px;
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
                }
                button {
                    width: 100%;
                    padding: 15px;
                    font-size: 18px;
                    border: none;
                    background-color: #5E17EB;
                    color: white;
                    border-radius: 5px;
                    cursor: pointer;
                    margin-top: 10px;
                }
                button:hover {
                    background-color: rgb(82, 17, 212);
                }
                .button-row {
                    display: flex;
                    gap: 10px;
                    margin-top: 10px;
                }
                .button-row button {
                    flex: 1;
                }
                .volume-row {
                    display: flex;
                    gap: 10px;
                    margin-top: 10px;
                }
                .volume-row button {
                    flex: 1;
                }
                #trackpad {
                    width: 100%;
                    height: 200px;
                    background: #eee;
                    border: 2px dashed #ccc;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    touch-action: none;
                }
                #keystroke-catcher {
                    border: 1px solid #ccc;
                    padding: 10px;
                    height: 50px;
                    overflow-y: auto;
                    outline: none;
                    margin-top: 10px;
                }
            </style>
            <script>
                function sendAction(action, data = "") {
                    fetch("/action", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ action, data })
                    });
                }

                function handleMove(x, y) {
                    if (!isTouching) return;
                    const dx = x - lastX;
                    const dy = y - lastY;
                    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
                        sendAction("move", { dx: dx, dy: dy });
                        lastX = x;
                        lastY = y;
                    }
                }

                let isTouching = false;
                let lastX = 0;
                let lastY = 0;

                window.onload = () => {
                    const trackpad = document.getElementById("trackpad");
                    const catcher = document.getElementById("keystroke-catcher");
                    catcher.focus();

                    catcher.addEventListener("keydown", (e) => {
                        e.preventDefault(); // Prevent displaying text

                        const key = e.key;
                        if (key === "Enter") {
                            sendAction("type", "\\n");
                        } else if (key === "Backspace") {
                            sendAction("backspace");
                        } else if (key.length === 1) {
                            sendAction("type", key);
                        }
                    });

                    trackpad.addEventListener("mousedown", (e) => {
                        isTouching = true;
                        lastX = e.clientX;
                        lastY = e.clientY;
                    });

                    trackpad.addEventListener("mousemove", (e) => {
                        if (isTouching) handleMove(e.clientX, e.clientY);
                    });

                    trackpad.addEventListener("mouseup", () => {
                        isTouching = false;
                    });

                    trackpad.addEventListener("mouseleave", () => {
                        isTouching = false;
                    });

                    trackpad.addEventListener("touchstart", (e) => {
                        isTouching = true;
                        const touch = e.touches[0];
                        lastX = touch.clientX;
                        lastY = touch.clientY;
                    });

                    trackpad.addEventListener("touchmove", (e) => {
                        const touch = e.touches[0];
                        handleMove(touch.clientX, touch.clientY);
                    });

                    trackpad.addEventListener("touchend", () => {
                        isTouching = false;
                    });
                };
            </script>
        </head>
        <body>
            <div class="container">
                <h2>berryMOTE</h2>
                <h3>Trackpad</h3>
                <div id="trackpad"></div>
                <div class="button-row">
                    <button onclick="sendAction('click')">Left Click</button>
                    <button onclick="sendAction('right_click')">Right Click</button>
                </div>
                <button onclick="sendAction('scroll_up')">Scroll Up</button>
                <button onclick="sendAction('scroll_down')">Scroll Down</button>
                <div class="volume-row">
                    <button onclick="sendAction('volume_down')">🔉</button>
                    <button onclick="sendAction('volume_toggle_mute')">🔇</button>
                    <button onclick="sendAction('volume_up')">🔊</button>
                </div>
                <div id="keystroke-catcher" contenteditable="true">Tap here and start typing...</div>
            </div>
        </body>
        </html>
        """

        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule("/action", "action", self.action, methods=["POST"])

    def index(self):
        return render_template_string(self.HTML_TEMPLATE)

    def action(self):
        data = request.get_json()
        action = data.get("action")
        key_data = data.get("data", "")

        #if wayland detected
        if is_wayland():
            if action == "move":
                dx = key_data.get("dx", 0)
                dy = key_data.get("dy", 0)
                factor = 1.0 #sensitivity boost
                ydotool_move(int(dx * factor), int(dy * factor))
            elif action == "click":
                ydotool_click("left")
            elif action == "right_click":
                ydotool_click("right")
            elif action == "scroll_up":
                ydotool_cmd("mousemove", "0", "-50")
            elif action == "scroll_down":
                ydotool_cmd("mousemove", "0", "50")
            elif action == "type" and key_data:
                ydotool_type(key_data)
            elif action == "backspace":
                ydotool_cmd("key", "14")
            elif action == "volume_up":
                os.system("pactl set-sink-volume @DEFAULT_SINK@ +5%")
            elif action == "volume_down":
                os.system("pactl set-sink-volume @DEFAULT_SINK@ -5%")
            elif action == "volume_toggle_mute":
                os.system("pactl set-sink-mute @DEFAULT_SINK@ toggle")
            return "OK"

        #if NO wayland detected (X11/Windows)
        if action == "move":
            dx = key_data.get("dx", 0)
            dy = key_data.get("dy", 0)
            x, y = self.mouse.position
            self.mouse.position = (x + dx, y + dy)
        elif action == "click":
            self.mouse.click(Button.left, 1)
        elif action == "right_click":
            self.mouse.click(Button.right, 1)
        elif action == "scroll_up":
            self.mouse.scroll(0, 2)
        elif action == "scroll_down":
            self.mouse.scroll(0, -2)
        elif action == "type" and key_data:
            self.keyboard.type(key_data)
        elif action == "backspace":
            self.keyboard.press(Key.backspace)
            self.keyboard.release(Key.backspace)
        elif action == "volume_up":
            if platform.system() == "Linux":
                os.system("pactl set-sink-volume @DEFAULT_SINK@ +5%")
            else:
                self.keyboard.press(Key.media_volume_up)
                self.keyboard.release(Key.media_volume_up)
        elif action == "volume_down":
            if platform.system() == "Linux":
                os.system("pactl set-sink-volume @DEFAULT_SINK@ -5%")
            else:
                self.keyboard.press(Key.media_volume_down)
                self.keyboard.release(Key.media_volume_down)
        elif action == "volume_toggle_mute":
            if platform.system() == "Linux":
                os.system("pactl set-sink-mute @DEFAULT_SINK@ toggle")
            else:
                self.keyboard.press(Key.media_volume_mute)
                self.keyboard.release(Key.media_volume_mute)

        return "OK"

    def shutdown(self):
        self.shutdown_event.set()
        return "Shutting down server..."

    def run(self):
        server_thread = threading.Thread(target=self._run_server)
        server_thread.start()
        self.shutdown_event.wait()
        print("Remote Flask server shut down.")
        
    def _run_server(self):
        self.app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

#interface
class gui(QWidget):
   def __init__(self, parent = None):
      #start remote
      self.remote = Remote()
      threading.Thread(target=self.remote.run, daemon=True).start()
      #intro screen
      super(gui, self).__init__(parent)
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
      self.ip_label.setText("Remote: http://" + self.get_local_ip() + ":5000")
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
   app = QApplication(sys.argv)
   introWindow = gui()
   introWindow.show()
   sys.exit(app.exec_())

# Run the app
if __name__ == "__main__":
    if is_wayland():
        #force PyQt5 to use X11 for the GUI window if os uses wayland
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    main()