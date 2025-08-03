# berryMOTE
A remote controller for you computer hosted on a local server and accessed by any browser on any device on the same network<br/>
Same remote functionality as seen in the [berryTV](https://github.com/Tyson-Shannon/berryTV) project that turns your computer into a smart TV <br/>

| Version  | Version Name | Release Date | Download Link | OS Supported |
| --- | --- | --- | --- | --- |
| v1.0.0 | June Berry | 2025-06-21 | [https://github.com/Tyson-Shannon/berryMOTE/releases/download/v1.0.0/berryMOTE.exe](https://github.com/Tyson-Shannon/berryMOTE/releases/download/v1.0.0/berryMOTE.exe) | Windows |
| v1.1.0 | June Berry | TBD | TBD | Linux |

<br/><br/>
![image](https://github.com/user-attachments/assets/8ad0834a-85b5-48aa-976d-4b03fa165142) <br/><br/>
<img src="https://github.com/user-attachments/assets/4022920a-eab3-4a3e-895a-d09decce7954" alt="remote" style="width:50%; height:auto;">
<br/><br/>
## Common Errors
**App runs but remote doesn't move or change anything on host device?** <br/>
Most modern Linux OS use a communication protocol and a set of libraries called **Wayland** which defines how applications and the display server communicate to render graphics and handle user input. Unlike X11, Wayland has a built in security feature to prevent malware from controlling or logging your keyboard which can also block our remote functionality. berryMOTE v1.1.0 has Wayland support but you may need to run one or both of the following commands in your terminal to get them to work. <br/>
```
sudo apt install ydotool
sudo systemctl enable --now ydotoold
```
<br/>
