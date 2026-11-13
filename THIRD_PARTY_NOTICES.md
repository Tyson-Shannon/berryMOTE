# Third-party notices

berryMOTE is distributed under the MIT License. Its dependency licenses are
listed below. The full text of the GNU Lesser General Public License v3 is
included in `LICENSES/LGPL-3.0.txt`.

| Component | License | Project |
| --- | --- | --- |
| PySide6 / Qt for Python | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Qt | LGPL-3.0 | https://www.qt.io/licensing/open-source-lgpl-obligations |
| Shiboken6 | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| pynput | LGPL-3.0 | https://github.com/moses-palmer/pynput |
| Flask | BSD-3-Clause | https://github.com/pallets/flask |
| Werkzeug | BSD-3-Clause | https://github.com/pallets/werkzeug |
| Jinja | BSD-3-Clause | https://github.com/pallets/jinja |
| Click | BSD-3-Clause | https://github.com/pallets/click |
| itsdangerous | BSD-3-Clause | https://github.com/pallets/itsdangerous |
| MarkupSafe | BSD-3-Clause | https://github.com/pallets/markupsafe |

PySide6 and Qt are dynamically linked. In the folder build, the Qt shared
libraries can be replaced by the user. The single-file build extracts the same
shared libraries to a temporary directory at runtime.
