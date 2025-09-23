#!/usr/bin/env python3
"""
Open two macOS Terminal windows and run backend + frontend globally.
Usage:
    python3 scripts/run_demo.py
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BACKEND_CMD = f"cd {REPO_ROOT} && python3 -m uvicorn src.api.app:app --reload --host 127.0.0.1 --port 8000"
FRONTEND_CMD = f"cd {REPO_ROOT} && python3 -m streamlit run frontend/app.py"

def open_in_terminal(command: str):
    """Run a shell command in a new Terminal.app window via AppleScript."""
    # Escape quotes for AppleScript
    safe_cmd = command.replace('"', '\\"')
    apple_script = f'''
    tell application "Terminal"
        activate
        do script "{safe_cmd}"
    end tell
    '''
    subprocess.run(["osascript", "-e", apple_script])

def run_demo():
    print("Launching backend in new Terminal window...")
    open_in_terminal(BACKEND_CMD)
    print("Launching frontend in new Terminal window...")
    open_in_terminal(FRONTEND_CMD)
    print("✅ Both processes launched. Check Terminal windows for logs.")

if __name__ == "__main__":
    run_demo()