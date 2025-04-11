import time
import subprocess
import os
import threading
from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server, udp_client
from watcher import watch_directory
from model_loader import load_model
from midi_utils import validate_midi_file, get_total_bars, save_midi_file
from anti import inpaint, continuation
import synth
from send_midi_osc import send_midi
from chords import MIDI_Stream, split_chord_message
import chords
from melody import rule_based_melody
from pprint import pprint
import torch

from ec2_gen import EC2Generator 
from utils import *
from liveosc_utils import *

playing_position = -1.0

def midi_to_GB_UDP(midi_file_path):
    print("/" + "="*50 + "/")
    print("midi_to_GB_UDP()")
    print("/" + "="*50 + "/\n")

    global scene
    print(f"Scene: {scene}")
    # ableton_client.send_message("/live/clip/get/playing_position", [2, 2]) # Click track, current scene
    global ec2_generator  # Add global declaration here too
    midi_stream = MIDI_Stream(midi_file_path)
    song_key, melody_array, chord_array, song_data = ec2_generator.song_select('Grateful Dead - Uncle Johns Band.mid')
    
    chords, strum, pluck, full_chords = midi_stream.get_UDP_lists()
    full_chords = midi_stream.get_full_chord_list()
    start = time.time()
    prediction, pluck_message = ec2_generator.generate_prediction_for_one_song(song_key, song_data, window_size=32, window_overlap=0, test_midi=midi_file_path)
    end = time.time()
    print("Time taken for prediction generation: ", end-start)
    # pprint(prediction)
    # pluck_message = ec2_generator.prediction_to_guitarbot(prediction, bpm=120, default_speed=7, rbm=None)
    chords_list = [list(item) for item in chords]
    strum_list = [list(item) for item in strum]
    pluck_list = [list(item) for item in pluck_message]
    # print(chords_list)
    # print(strum_list)

    # pluck_message = [[note (midi value), duration, speed, timestamp]]

    empty_chord = chords_list[-1]
    empty_chord[0] = 'On'
    empty_strum = ['UP', 0.0]
    empty_chord = [empty_chord]
    empty_strum = [empty_strum]
    pprint(empty_chord)
    pprint(empty_strum)
    pprint(pluck_message)

    bpm_secs = 60 / 100 # default bpm for now but we can easily query this from osc
    global playing_position
    while(playing_position < 0.0):
        ableton_client.send_message("/live/song/get/current_song_time", [])
    print(f"Playing position: {playing_position}")
    t_record = time.time()


    overall_wait = bpm_secs - (playing_position % bpm_secs) # time until next beat
    send_t = t_record + overall_wait - 0.35 # 0.35 is set latency
    telapse = time.time()
    while(telapse - send_t <  0.01):
        # print(telapse - send_t)
        time.sleep(0.005)
        telapse = time.time()
    client.send_message("/Chords", empty_chord)
    client.send_message("/Strum", empty_strum)
    client.send_message("/Pluck", pluck_list)
    print("Sent")
    # .35 seconds of delay between sent message and it being played

    
def watch_NN_dir(input_directory):
    # watch_directory(input_directory, midi_to_liveosc) for ableton live testing
    watch_directory(input_directory, midi_to_GB_UDP)

def watch_Anti_dir(input_directory):
    watch_directory(input_directory, anti_to_liveosc)

def start_server(ip, port):
    dispatcher = Dispatcher()
    dispatcher.map("/live/song/get/current_song_time", playing_position_handler)
    dispatcher.map("/live/error", print_error)
    dispatcher.map("/live/clip/get/playing_position", playing_position_handler)
    server = osc_server.ThreadingOSCUDPServer((ip, port), dispatcher)
    print("Serving on {}".format(server.server_address))
    server.serve_forever()

def print_error(address, args):
    print("Received error from Live: %s" % args)

def playing_position_handler(address, *args):
    global playing_position
    playing_position = args[0]  # assumes a single float value is sent

midi_file_path = None
model = None
model_size = 'small'

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

if __name__ == "__main__":
    print("Hello!")
    global user, ec2_generator
    user = "LabMac"
    if user == "LabMac":
        neuralnote_path = "../NeuralNote/build/NeuralNote_artefacts/Release/Standalone/NeuralNote.app/"  # Path to NeuralNote
        NN_dir = "/Users/music/Library/Caches/NeuralNote/neuralnote"  # Directory to watch for new MIDI files from neuralnote (or a test directory)
    elif  user == "RyanWindows":
        neuralnote_path = "C:/Program Files (x86)/NeuralNote/NeuralNote.exe"  # Path to NeuralNote
        NN_dir = './watcherNN'
    elif user == "RyanMac":
        neuralnote_path = "../NeuralNote/build/NeuralNote_artefacts/Release/Standalone/NeuralNote.app/"  # Path to NeuralNote
        NN_dir = '/Users/ryanbaker/Library/Caches/NeuralNote/neuralnote'
    else:
        NN_dir = './watcherNN'
    if not os.path.exists(NN_dir):
        os.makedirs(NN_dir)
    Anti_dir = "./watcherAnti"  # Directory to watch for new MIDI files from Anticipation 
    if not os.path.exists(Anti_dir):
        os.makedirs(Anti_dir)
        
    ec2_generator = EC2Generator(
        model_path='./icm-deep-music-generation/ec2vae/model_param/ec2vae-v1.pt',
        pickle_path="./GP_Melody_Chords/ec2_with_UJB.pkl"
    )
    directory = "./GP_Melody_Chords"
    pickle_filename = "vae_data.pkl"
    pickle_path = os.path.join(directory, pickle_filename)
    

    # print("Starting NeuralNote...")
    # open_neuralnote(neuralnote_path) # commented for vst use

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
    client_ip = "192.168.1.1"
    # client_ip = "127.0.0.1"
    client_port = 12000
    client = udp_client.SimpleUDPClient(client_ip, client_port)

    ableton_client_ip = "127.0.0.1"
    ableton_client_port = 11000
    ableton_client = udp_client.SimpleUDPClient(ableton_client_ip, ableton_client_port)

    # Start watching the directory for new MIDI files in a separate thread
    NNWatcher_thread = threading.Thread(target=watch_NN_dir, args=(NN_dir,))
    NNWatcher_thread.daemon = True
    NNWatcher_thread.start()

    # AntiWatcher_thread = threading.Thread(target=watch_Anti_dir, args=(Anti_dir,))
    # AntiWatcher_thread.daemon = True
    # AntiWatcher_thread.start()

    # Wait for a MIDI file to be detected
    while True:
        time.sleep(1)

