from pickler import process_directory_to_ec2vae_pickle, midi_to_melody_array, m21_to_one_hot
import chords
from melody import rule_based_melody, remix
import os
import pickle
import numpy as np
import torch
import pretty_midi as pm
import matplotlib.pyplot as plt
import sys
import readline
import random
import time
import re

sys.path.append('../icm-deep-music-generation')
from ec2vae.model import EC2VAE

##########################
# Helper Functions
##########################

def note_array_to_onehot(note_array):
    pr = np.zeros((len(note_array), 130))
    pr[np.arange(len(note_array)), note_array.astype(int)] = 1.
    return pr

def encode(melody_array, chord_array, viz=False):
    global device
    m1h = note_array_to_onehot(melody_array)  # Convert melody to one-hot
    if viz:
        plt.imshow(m1h, aspect='auto')
        plt.title('Melody One-Hot')
        plt.show()
    pm1h = torch.from_numpy(m1h).float().to(device).unsqueeze(0)
    pc1h = torch.from_numpy(chord_array).float().to(device).unsqueeze(0)
    zp1, zr1 = ec2vae_model.encoder(pm1h, pc1h)
    return zp1, zr1, pc1h

def decode(latent_pitch, latent_rhythm, chord_condition, viz=False):
    global device
    pred = ec2vae_model.decoder(latent_pitch, latent_rhythm, chord_condition)
    pred = pred.squeeze(0).cpu().numpy()
    if viz:
        plt.imshow(pred, aspect='auto')
        plt.title('Decoded Prediction')
        plt.show()
    return pred

def generate_midi(melody_array, file_path, bpm=120, start=0., chord_array=None):
    midi = pm.PrettyMIDI()
    mel_notes = ec2vae_model.__class__.note_array_to_notes(melody_array, bpm=bpm, start=start)
    ins1 = pm.Instrument(0)
    ins1.notes = mel_notes
    midi.instruments.append(ins1)
    if chord_array is not None:
        c_notes = ec2vae_model.__class__.chord_to_notes(chord_array.numpy(), bpm, start)
        ins2 = pm.Instrument(0)
        ins2.notes = c_notes
        midi.instruments.append(ins2)
    midi.write(file_path)

def song_key_completer(text, state):
    options = [key for key in data_dict.keys() if key.startswith(text)]
    return options[state] if state < len(options) else None

def song_select():
    readline.set_completer(song_key_completer)
    readline.parse_and_bind("tab: complete")
    song_key = input("Pick a song, or press Enter to pick a random song: ")
    if not song_key:
        song_key = random.choice(list(data_dict.keys()))
    elif song_key not in data_dict:
        print(f"Song key '{song_key}' not found, picking randomly.")
        song_key = random.choice(list(data_dict.keys()))
    return song_key, data_dict[song_key]["melody"], data_dict[song_key]["chords"]


def prepare_windows(in_mar, in_car, melody_array, chord_array, window_size=32):
    """
    Pads the input and reference arrays so that their length is a multiple of window_size.
    Returns the padded arrays and the total length.
    """
    if melody_array.shape[0] < chord_array.shape[0]:
        melody_array = np.concatenate((melody_array, 
                            np.zeros(chord_array.shape[0] - melody_array.shape[0], dtype=melody_array.dtype)))
    elif melody_array.shape[0] > chord_array.shape[0]:
        chord_array = np.concatenate((chord_array, 
                            np.zeros((melody_array.shape[0] - chord_array.shape[0], chord_array.shape[1]), dtype=chord_array.dtype)))
    
    total_length = in_mar.shape[0]
    print(f"Total length before padding: {total_length}")
    if total_length % window_size != 0:
        total_length = ((total_length // window_size) + 1) * window_size
        in_mar = np.concatenate((in_mar, np.zeros(total_length - in_mar.shape[0], dtype=in_mar.dtype)))
        in_car = np.concatenate((in_car, np.zeros((total_length - in_car.shape[0], in_car.shape[1]), dtype=in_car.dtype)))
        melody_array = np.concatenate((melody_array, np.zeros(total_length - melody_array.shape[0], dtype=melody_array.dtype)))
        chord_array = np.concatenate((chord_array, np.zeros((total_length - chord_array.shape[0], chord_array.shape[1]), dtype=chord_array.dtype)))
    return in_mar, in_car, melody_array, chord_array, total_length

def iterate_windows(in_mar, in_car, melody_array, chord_array, window_size=32, window_overlap=0):
    """
    Generator that yields windows (slices) of the input and reference arrays.
    If window_overlap > 0, windows will overlap by that many steps.
    """
    step_size = window_size - window_overlap
    total_length = in_mar.shape[0]
    for i in range(0, total_length - window_size + 1, step_size):
        yield (in_mar[i:i+window_size],
               in_car[i:i+window_size],
               melody_array[i:i+window_size],
               chord_array[i:i+window_size])

##########################
# Generative Functions
##########################

def generate_song_for_all(data_dict, window_size=32, window_overlap=0):
    """
    Iterates over every song in data_dict, runs the generative process over overlapping windows,
    and saves a MIDI file for each song.
    """
    for song_key, song_data in data_dict.items():
        p = generate_prediction_for_one_song(song_key, song_data, window_size, window_overlap)
        save_prediction_to_midi(p, f"generated_midis/{song_key}_generated.mid", bpm=120, start=0.)

def generate_prediction_for_one_song(song_key, song_data, window_size=32, window_overlap=0, test_midi=None, whatif_melody=False):
    """
    Processes a single song (given by its key and song_data dictionary) over overlapping windows
    and saves a generated MIDI file for testing.
    
    If test_midi is provided, it will be used as the source input for rule-based melody generation.
    Otherwise, the song_data's 'source_midi' (or song_key) is used.
    """
    print(f"Processing song: {song_key}")
    melody_array = song_data["melody"]
    chord_array = song_data["chords"]
    source = test_midi if test_midi is not None else song_data.get("source_midi", song_key)
    ms = chords.MIDI_Stream(source)
    full_chords = ms.get_full_chord_list()
    rbm, rbm_path = rule_based_melody(full_chords, bpm=120, debug=False)
    in_mar = midi_to_melody_array(rbm_path)
    in_car = m21_to_one_hot(full_chords)
    
    in_mar, in_car, melody_array, chord_array, total_length = prepare_windows(
        in_mar, in_car, melody_array, chord_array, window_size)
    final_prediction = None
    num_windows = 0
    for window in iterate_windows(in_mar, in_car, melody_array, chord_array, window_size, window_overlap):
        num_windows += 1
        in_mar_window, in_car_window, mel_window, ch_window = window
        zp1, zr1, c1 = encode(in_mar_window, in_car_window, viz=False)
        zp2, zr2, c2 = encode(mel_window, ch_window, viz=False)
        prediction_window = decode(zp1, zr2, c1, viz=False)
        # pprint(prediction_window)
        if final_prediction is None:
            final_prediction = prediction_window
        else:
            final_prediction = np.concatenate((final_prediction, prediction_window))
    print(f"Processed {num_windows} windows for song: {song_key}")
    # pprint(final_prediction)
    # final_prediction = remix(final_prediction)
    return final_prediction

def save_prediction_to_midi(prediction, file_path, bpm=120, start=0.):
    midi_output_path = os.path.join("generated_midis", file_path)
    os.makedirs("generated_midis", exist_ok=True)
    generate_midi(prediction, midi_output_path, bpm=120, start=0.)
    print(f"Saved generated MIDI to {midi_output_path}")

def insert_metronome_pulses(gb_array, bpm = 120, met_MNN=40, countin=True):
    # [MNN, duration, speed, ontime]
    total_length = gb_array[-1][3] + gb_array[-1][1]
    tick_duration = 60 / bpm # quarter notes
    metronome = []
    current_time = 0.0
    if countin:
        for pluck in gb_array:
            pluck[3] = pluck[3] + 4 * tick_duration # add 4 beats to all ontimes
    for i in range(0, int(total_length / tick_duration)):
        metronome.append([met_MNN, 0.1, 1, current_time])
        current_time += tick_duration

    gb_array = np.concatenate((gb_array, metronome), axis=0)
    gb_array[:, 0] = gb_array[:, 0].astype(int)
    gb_array[:, 2] = gb_array[:, 2].astype(int)
    return gb_array

def prediction_to_guitarbot(ec2_array, bpm=120, default_speed=7):
    tick_duration = 60 / bpm / 4 # sixteenth notes
    pluck_message = []
    current_time = 0.0
    i = 0
    while i < len(ec2_array):
        val = ec2_array[i]
        if val == 129:
            # A rest: simply advance the current time by one tick.
            current_time += tick_duration
            i += 1
        elif val == 128:
            # A sustain tick with no preceding note; skip it.
            i += 1
        else:
            # Found a new note onset (0-127)
            pitch = val
            while pitch < 50:
                pitch += 12
            while pitch > 68:
                pitch -= 12
            duration_ticks = 1  # count the current tick
            i += 1
            # Count any consecutive sustain ticks (128) to extend the duration.
            while i < len(ec2_array) and ec2_array[i] == 128:
                duration_ticks += 1
                i += 1
            duration = duration_ticks * tick_duration
            # Create the new event: note, duration, speed, and ontime.
            pluck_message.append([pitch, duration, default_speed, current_time])
            # Advance the current time by the duration of this note.
            current_time += duration
    pluck_message = insert_metronome_pulses(pluck_message, bpm=bpm, countin=True)
    result = []
    for row in pluck_message:
        result.append([int(row[0]), round(float(row[1]), 5), int(row[2]), round(float(row[3]),5)])
        # Force columns 0 and 2 to be int, columns 1 and 3 to be floats.
    pluck_message = result
    return pluck_message

##########################
# Pickle Loading
##########################

def load_data_pickle(pickle_path):
    """
    Loads and returns the data dictionary from a pickle file.
    """
    with open(pickle_path, "rb") as f:
        data_dict = pickle.load(f)
    return data_dict

##########################
# Main Execution
##########################

if __name__ == "__main__":
    import itertools
    global device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    ec2vae_model = EC2VAE.init_model()
    ec2vae_param_path = '../icm-deep-music-generation/ec2vae/model_param/ec2vae-v1.pt'
    ec2vae_model.load_model(ec2vae_param_path)
    
    directory = "./GP_Melody_Chords"
    pickle_filename = "vae_data.pkl"
    pickle_path = os.path.join(directory, pickle_filename)
    
    # Prompt user for a test MIDI file; default is "test_midis/messtest.mid"
    input_melody = input("Pick an input test MIDI file, or press Enter to use default (test_midis/messtest.mid): ")
    if not input_melody:
        input_melody = "test_midis/EMajorMess.mid"
    
    # Load or create the pickle data
    if os.path.exists(pickle_path):
        with open(pickle_path, "rb") as f:
            data_dict = pickle.load(f)
    else:
        data_dict = process_directory_to_ec2vae_pickle(directory)
    
    print("Available songs:")
    from pprint import pprint
    pprint(list(data_dict.keys()))
    
    # Prompt user for solo type
    print("\nSelect a solo type:")
    print("1. Blues Solo")
    print("2. Rock Solo")
    print("3. Country Solo")
    solo_choice = input("Enter 1, 2, or 3: ").strip()

    def filter_blues(name): 
        return "blues" in name.lower()
    def filter_rock(name): 
        rock_keywords = ["acdc", "deep purple", "guns n' roses"]
        return any(kw in name.lower() for kw in rock_keywords)
    def filter_country(name): 
        return "country" in name.lower()
    
    if solo_choice == "1":
        solo_filter = filter_blues
        output_filename = "combined_blues_solo.mid"
    elif solo_choice == "2":
        solo_filter = filter_rock
        output_filename = "combined_rock_solo.mid"
    elif solo_choice == "3":
        solo_filter = filter_country
        output_filename = "combined_country_solo.mid"
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)
    
    # Filter songs based on solo type.
    filtered_data = {key: val for key, val in data_dict.items() if solo_filter(key)}
    if not filtered_data:
        print("No songs matched the selected criteria.")
        sys.exit(1)
    
    print("\nHow many solos do you want?")
    num_solos = input("Enter a number (default is all): ").strip()
    if num_solos.isdigit():
        num_solos = int(num_solos)
        if num_solos <= len(filtered_data):
            filtered_data = dict(itertools.islice(filtered_data.items(), 0, num_solos))
        else:
            print(f"Requested number exceeds available songs. Using all {len(filtered_data)} songs.")

    print("Processing the following songs for the solo:")
    pprint(list(filtered_data.keys()))
    
    # Combine predictions from all filtered songs
    combined_prediction = None
    for song_key, song_data in filtered_data.items():
        print(f"Generating for song: {song_key}")
        prediction = generate_prediction_for_one_song(song_key, song_data, window_size=32, window_overlap=0, test_midi=input_melody)
        # Instead of saving each song individually, we append to combined_prediction.
        if combined_prediction is None:
            combined_prediction = prediction
        else:
            combined_prediction = np.concatenate((combined_prediction, prediction), axis=0)
        
    save_prediction_to_midi(combined_prediction, output_filename, bpm=100, start=0.)
    pprint(prediction_to_guitarbot(combined_prediction, bpm = 100, default_speed=7))
    # Note: guitarbot can only receive 30 second messages at a time.