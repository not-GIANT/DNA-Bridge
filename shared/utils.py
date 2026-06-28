import os
import sys

def get_app_dir() -> str:
    """Always returns the directory the exe (or script) lives in."""
    if getattr(sys, 'frozen', False):
        # Use sys._MEIPASS for bundled resources (points to _internal in PyInstaller 6+)
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    
    # If we are in a subdirectory (like client/ or server/), go up to the project root
    curr_file = os.path.abspath(__file__)
    # This file is in shared/, so root is one level up
    return os.path.dirname(os.path.dirname(curr_file))

def get_config_dir() -> str:
    """Returns a persistent, writeable directory for storing user configuration."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = os.path.join(appdata, "DNABridge")
            os.makedirs(path, exist_ok=True)
            return path
    path = os.path.join(os.path.expanduser("~"), ".dnabridge")
    os.makedirs(path, exist_ok=True)
    return path

