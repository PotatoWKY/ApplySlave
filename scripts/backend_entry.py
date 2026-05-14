"""PyInstaller entry point for the backend binary.

This is a thin wrapper that just calls the backend's CLI entry point.
PyInstaller needs a concrete .py file as the entry; we can't point it
at a console_scripts entry directly.
"""

from applyslave.backend.main import run

if __name__ == "__main__":
    run()
