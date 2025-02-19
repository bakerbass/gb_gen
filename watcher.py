import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class MidiFileHandler(FileSystemEventHandler):
    def __init__(self, callback):
        """
        Initializes the handler with a callback function.
        The callback will be called with the path of the MIDI file when it is created or modified.
        """
        self.callback = callback

    def on_created(self, event):
        """
        Triggered when a file or directory is created.
        """
        if not event.is_directory and event.src_path.endswith(".mid"):
            print(f"File created: {event.src_path}")
            self.callback(event.src_path)

    def on_modified(self, event):
        """
        Triggered when a file or directory is modified.
        """
        # if not event.is_directory and event.src_path.endswith(".mid"):
        #     print(f"File modified: {event.src_path}")
        #     self.callback(event.src_path)

def watch_directory(path_to_watch, callback, recursive=True):
    """
    Watches the given directory for new or modified MIDI files, optionally monitoring subdirectories.

    :param path_to_watch: Directory to monitor for new or modified files.
    :param callback: Function to call when a new or modified MIDI file is detected.
    :param recursive: Whether to monitor subdirectories.
    """
    event_handler = MidiFileHandler(callback)
    observer = Observer()
    observer.schedule(event_handler, path_to_watch, recursive=recursive)
    observer.start()
    print(f"Watching directory: {path_to_watch} (recursive={recursive})")

    try:
        while True:
            time.sleep(1)  # Keep the script running
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
