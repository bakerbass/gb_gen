import time
import subprocess
import os
import threading
from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server, udp_client
from watcher import watch_directory
from model_loader import load_model
from midi_utils import validate_midi_file, get_total_bars
from inpaint import process_midi_file
import synth
from send_midi_osc import send_midi
from chords import MIDI_Stream
import chords
def open_neuralnote(app_path):
    try:
        subprocess.Popen(["open", app_path])
        print(f"Opened NeuralNote at : {app_path}")
    except Exception as e:
        print(f"Failed to open NeuralNote: {e}")

midi_file_count = -2
midi_file_path = None
def load_midi(file_path):
    global midi_file_count, midi_file_path
    if not validate_midi_file(file_path):
        return
    else:
        midi_file_path = file_path
        if midi_file_count < 0:
            print("Ignoring first files: " + file_path)
            midi_file_count += 1
        if midi_file_count == 0:
            print("First file being sent! File path:" + file_path + " | File no. " + str(midi_file_count))
            # First file: send immediately with fire_immediately False and no offset.
            send_midi(client, file_path, fire_immediately=True, time_offset=8)
            midi_file_path = file_path
            midi_file_count += 1
        elif midi_file_count == 1:
            print("Second file being sent! File path:" + file_path + " | File no. " + str(midi_file_count))
            # Second file: send to same track/clip as first file, but offset by one bar (e.g. 4 beats).
            client.send_message("/live/clip/fire", [0, 0])
            send_midi(client, file_path, fire_immediately=False, time_offset=12, file_idx=1)
            midi_file_count += 1
        else:
            print("Subsequent file being sent! File path:" + file_path + " | File no. " + str(midi_file_count))
            send_midi(client, file_path, fire_immediately=False, clip_index=midi_file_count-1, file_idx=midi_file_count)
    return midi_file_path
def midi_to_GB_UDP(midi_file_path):
    midi_stream = MIDI_Stream(midi_file_path)
    chords, strum, pluck = midi_stream.get_UDP_lists()
    chords_list = [list(item) for item in chords]
    strum_list = [list(item) for item in strum]
    pluck_list = [list(item) for item in pluck]
    
    print(chords_list)
    print(strum_list)
    print(pluck_list)
    
    client.send_message("/Chords", chords_list)
    client.send_message("/Strum", strum_list)
    client.send_message("/Pluck", pluck_list)
    
def start_watching_directory(input_directory):
    watch_directory(input_directory, midi_to_GB_UDP)

def start_server(ip, port):
    dispatcher = Dispatcher()
    dispatcher.map("/live/error", print_error)
    server = osc_server.ThreadingOSCUDPServer((ip, port), dispatcher)
    print("Serving on {}".format(server.server_address))
    # server.serve_forever()

def print_error(address, args):
    print("Received error from Live: %s" % args)

midi_file_path = None
model = None
neuralnote_path = "../NeuralNote/build/NeuralNote_artefacts/Release/Standalone/NeuralNote.app/"  # Path to NeuralNote
model_size = 'large'

if __name__ == "__main__":
    print("Hello!")
    print("Starting NeuralNote...")
    # open_neuralnote(neuralnote_path) # commented for vst use
    synth.initialize_fluidsynth()

    input_directory = "/Users/music/Library/Caches/NeuralNote"  # Directory to watch for new MIDI files

    # Load the model
    # print("Loading model...")
    # model = load_model(model_size)
    # print(f"Model loaded: {model_size}")

    # Start the OSC server in a separate thread
    server_ip = "127.0.0.1"
    server_port = 11001
    server_thread = threading.Thread(target=start_server, args=(server_ip, server_port))
    server_thread.daemon = True
    server_thread.start()

    # Start the OSC client
    client_ip = "127.0.0.1"
    client_port = 11000
    client = udp_client.SimpleUDPClient(client_ip, client_port)

    # Start watching the directory for new or modified MIDI files in a separate thread
    watcher_thread = threading.Thread(target=start_watching_directory, args=(input_directory,))
    watcher_thread.daemon = True
    watcher_thread.start()

    # Wait for a MIDI file to be detected
    while True:
        time.sleep(1)

    # # Process the detected MIDI file
    # synth.synthesize_midi(midi_file_path)

    # inpainted, combined = process_midi_file(midi_file_path, start_time=2, end_time=6, model=model, time_unit='seconds')
    # synth.synthesize_tokens(combined, name='combined')
    # synth.synthesize_tokens(inpainted, name='inpainted')
    # print("Done!")