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
    song_key = input("Pick a song, or press Enter to pick Uncle Johns Band: ") # a random song: ")
    if not song_key:
        song_key = 'Grateful Dead - Uncle Johns Band.mid'
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
        melody_array = np.concatenate((melody_array, np.zeros(np.abs(total_length - melody_array.shape[0]), dtype=melody_array.dtype)))
        chord_array = np.concatenate((chord_array, np.zeros((np.abs(total_length - chord_array.shape[0]), chord_array.shape[1]), dtype=chord_array.dtype)))
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
    gb = prediction_to_guitarbot(final_prediction, bpm = 100, default_speed=7, rbm=rbm)
    return final_prediction, gb

def split_pluck_message(pluck_message, speed_offset, bpm):
    pluck_message = np.array(pluck_message)
    if len(pluck_message) < 40:
        return pluck_message
    
    # Create a list to hold our chunked pluck messages
    chunked_messages = []
    chunk_size = 39
    last_note = [0, 0, 0, 0]
    pen_note = last_note
    qnd = 60 / bpm # quarter note duration in seconds
    print("qnd: " + str(qnd))
    # Split the array into chunks of 39 elements
    last_ot = 0
    for i in range(0, len(pluck_message), chunk_size):
        chunk = pluck_message[i:i+chunk_size]
        ot_offset = chunk[0, 3] - last_ot
        last_ot = chunk[-1][3] # save last on time before offsetting
        chunk[:, 3] = chunk[:, 3] - chunk[0, 3] + ot_offset
        # Normalize the ontime to start from 0 + last note duration
        chunk[:, 2] = chunk[:, 2] + speed_offset
        result = []
        for row in chunk:
            result.append([int(row[0]), round(float(row[1]), 5), int(row[2]), round(float(row[3]), 5)])
        chunk = result
        chunked_messages.append(chunk)
    
    # Return the list of chunked arrays
    return chunked_messages

def insert_metronome_pulses(gb_array, bpm = 120, met_MNN=40, countin=True, interleave=False):
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
    if interleave:
        gb_array = gb_array[np.argsort(gb_array[:, 3])]
    gb_array[:, 0] = gb_array[:, 0].astype(int)
    gb_array[:, 2] = gb_array[:, 2].astype(int)
    return gb_array

def prediction_to_guitarbot(ec2_array, bpm=120, rbm=None, default_speed=7):
    tick_duration = 60 / bpm / 4 # sixteenth notes
    pluck_message = []
    current_time = 0.0
    i = 0
    highest_speed = 0
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
            # Create the new event: note, duration, speed, and ontime.\
            if rbm is not None:
                # Instead of rbm[i][2], find the most recent rbm row where rbm_row[3] <= current_time.
                # Iterate in reverse so we get the latest matching ontime.
                for row in reversed(rbm):
                    if row[3] <= current_time:
                        speed = row[2]
                        break
                if speed > highest_speed:
                    print(f"New highest speed: {speed}")
                    highest_speed = speed
            else:
                speed = default_speed
            pluck_message.append([pitch, duration, speed, current_time])
            # Advance the current time by the duration of this note.
            current_time += duration
    result = []
    speed_add = 9 - highest_speed
    print(f"Speed add: {speed_add}")
    print(f"Highest speed: {highest_speed}")

    pluck_message = insert_metronome_pulses(pluck_message, bpm=bpm, countin=True, interleave=True)
    print("Before split: \n")
    pprint(pluck_message)
    print("\n")
    pluck_message = split_pluck_message(pluck_message, speed_add, bpm)
    # for row in pluck_message:
    #     if(int(row[2]) + speed_add > 9):
    #         print("wtf!")
    #     result.append([int(row[0]), round(float(row[1]), 5), int(row[2]) + speed_add, round(float(row[3]),5)])
    #     # Force columns 0 and 2 to be int, columns 1 and 3 to be floats.
    # pluck_message = result
    return pluck_message
 
 
def save_prediction_to_midi(prediction, file_path, bpm=120, start=0.):
    midi_output_path = os.path.join("generated_midis", file_path)
    os.makedirs("generated_midis", exist_ok=True)
    generate_midi(prediction, midi_output_path, bpm=120, start=0.)
    print(f"Saved generated MIDI to {midi_output_path}")

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
    from pprint import pprint
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    ec2vae_model = EC2VAE.init_model()
    ec2vae_param_path = './icm-deep-music-generation/ec2vae/model_param/ec2vae-v1.pt'
    ec2vae_model.load_model(ec2vae_param_path)
    
    directory = "./GP_Melody_Chords"
    pickle_filename = "ec2_with_UJB.pkl"
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
    
    print("Available songs:\n")
    pprint(list(data_dict.keys()))
    song_key, melody_array, chord_array = song_select()
    song_data = data_dict[song_key]

    output_filename = "testing_output.mid"

    print("Processing the following songs for the solo:")
    # pprint(list(filtered_data.keys()))
    
  
    print(f"Generating for song: {song_key}")
    prediction, gb = generate_prediction_for_one_song(song_key, song_data, window_size=32, window_overlap=0, test_midi=input_melody)
    # Instead of saving each song individually, we append to combined_prediction.
    pprint(gb)
    save_prediction_to_midi(prediction, output_filename, bpm=100, start=0.)
    # Note: guitarbot can only receive 30 second messages at a time.