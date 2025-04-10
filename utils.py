import os
import subprocess
import time
import platform
from pynput.keyboard import Controller
if platform.system().lower() == "windows":
    import win32gui
    import win32process
opened_pid = None

def start_recording():
    keyboard = Controller()
    keyboard.press('r')
    keyboard.release('r')

def enum_handler(hwnd, lParam):
    global opened_pid
    try:
        # Retrieve thread and process IDs associated with hwnd.
        thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
        if process_id == opened_pid:
            win32gui.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"Error handling window {hwnd}: {e}")


def open_neuralnote(app_path):
    current_os = platform.system().lower()
   
    if "windows" in current_os:
        try:
            # Open the application.
            proc = subprocess.Popen(app_path)
            opened_pid = proc.pid
            # Wait briefly to allow the window to be created.
            print("Waiting for NeuralNote to open...")
            time.sleep(20)
            print("NeuralNote opened.")
            # Enumerate all windows and set focus on the matching one.
            win32gui.EnumWindows(enum_handler, None)
            print(f"Opened NeuralNote at: {app_path}")
        except Exception as e:
            print(f"Failed to open NeuralNote on Windows: {e}")
            
    elif "darwin" in current_os or "mac" in current_os:
        try:
            subprocess.Popen(["open", app_path])
            print(f"Opened NeuralNote at: {app_path}")
        except Exception as e:
            print(f"Failed to open NeuralNote on macOS: {e}")
            
    else:
        print("OS not recognized. Please run this script on Windows or macOS.")

