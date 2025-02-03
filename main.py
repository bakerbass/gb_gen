import time
import subprocess
import os
import threading
from watcher import watch_directory
from model_loader import load_model
from midi_util import validate_midi_file, get_total_bars
from inpaint import process_midi_file
import synth

def open_neuralnote(app_path):
    try:
        subprocess.Popen(["open", app_path])
        print(f"Opened NeuralNote at : {app_path}")
    except Exception as e:
        print(f"Failed to open NeuralNote: {e}")

def load_midi(file_path):
    global midi_file_path
    if validate_midi_file(file_path):
        midi_file_path = file_path
        print(f"MIDI file path updated: {midi_file_path}")
    else:
        print(f"Failed to load MIDI file: {file_path}")
    return midi_file_path

def start_watching_directory(input_directory):
    watch_directory(input_directory, load_midi)

midi_file_path = None
model = None
neuralnote_path = "../NeuralNote/build/NeuralNote_artefacts/Release/Standalone/NeuralNote.app/"  # Path to NeuralNote
model_size = 'large'

if __name__ == "__main__":
    print("Hello!")
    print("Starting NeuralNote...")
    open_neuralnote(neuralnote_path)
    synth.initialize_fluidsynth()

    input_directory = "/Users/ryanbaker/Library/Caches/NeuralNote"  # Directory to watch for new MIDI files

    # Load the model
    print("Loading model...")
    model = load_model(model_size)
    print(f"Model loaded: {model_size}")

    # Start watching the directory for new or modified MIDI files in a separate thread
    watcher_thread = threading.Thread(target=start_watching_directory, args=(input_directory,))
    watcher_thread.daemon = True
    watcher_thread.start()

    # Wait for a MIDI file to be detected
    while midi_file_path is None:
        time.sleep(1)

    # Process the detected MIDI file
    synth.synthesize_midi(midi_file_path)

    inpainted, combined = process_midi_file(midi_file_path, start_time= 2, end_time = 6, model=model, time_unit='seconds')
    synth.synthesize_tokens(combined, name='combined')
    synth.synthesize_tokens(inpainted, name='inpainted')
    print("Done!")