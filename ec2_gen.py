
from pickler import process_directory_to_ec2vae_pickle, midi_to_melody_array, m21_to_one_hot
import chords
from melody import rule_based_melody
import os
import pickle
import numpy as np
import torch
import pretty_midi as pm
import matplotlib.pyplot as plt
import sys
import readline
sys.path.append('../icm-deep-music-generation')
from ec2vae.model import EC2VAE

def note_array_to_onehot(note_array):
    pr = np.zeros((len(note_array), 130))
    pr[np.arange(0, len(note_array)), note_array.astype(int)] = 1.
    return pr

def encode(melody_array, chord_array, viz=False):
    global device
    m1h = note_array_to_onehot(melody_array) # melody one-hot
    if viz:
        plt.imshow(m1h, aspect='auto')
        plt.title('Display pr1')
        plt.show()
    # to pytorch tensor, float32, gpu-ify, add batch dimension
    pm1h = torch.from_numpy(m1h).float().to(device).unsqueeze(0) # pytorch melody 1-hot
    pc1h = torch.from_numpy(chord_array).float().to(device).unsqueeze(0) # pytorch chord 1-hot

    zp1, zr1 = ec2vae_model.encoder(pm1h, pc1h) # latent pitch encoding, latent rhythm encoding
    return zp1, zr1, pc1h

def decode(latent_pitch, latent_rhythm, chord_condition, viz=False):
    global device
    # decode
    m1h_prediction = ec2vae_model.decoder(latent_pitch, latent_rhythm, chord_condition) # predicted representation
    m1h_prediction = m1h_prediction.squeeze(0).cpu().numpy() # remove batch dimension
    if viz:
        plt.imshow(m1h_prediction, aspect='auto')
        plt.title('Display m1h_prediction')
        plt.show()
    return m1h_prediction

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
    # Provide song key completion from the data_dict keys.
    options = [key for key in data_dict.keys() if key.startswith(text)]
    if state < len(options):
        return options[state]
    else:
        return None


def song_select():
    readline.set_completer(song_key_completer)
    readline.parse_and_bind("tab: complete")
    song_key = input("Pick a song, or press Enter to pick a random song:")
    if not song_key:
        song_key = random.choice(list(data_dict.keys()))
        melody_array = data_dict[song_key]["melody"]
        chord_array = data_dict[song_key]["chords"]
        # print("Melody array for", song_key, ":", melody_array)
        # print("Chord array for", song_key, ":", chord_array)
    elif song_key in data_dict:
        melody_array = data_dict[song_key]["melody"]
        chord_array = data_dict[song_key]["chords"]
        # print("Melody array for", song_key, ":", melody_array)
        # print("Chord array for", song_key, ":", chord_array)
    else:
        print(f"Song key '{song_key}' not found in the dictionary, picking randomly.")
        song_key = random.choice(list(data_dict.keys()))
        melody_array = data_dict[song_key]["melody"]
        chord_array = data_dict[song_key]["chords"]

    return melody_array, chord_array

def prepare_windows(in_mar, in_car, melody_array, chord_array, window_size=32):
    if melody_array.shape[0] < chord_array.shape[0]:
        melody_array = np.concatenate((melody_array, np.zeros(chord_array.shape[0] - melody_array.shape[0], dtype=melody_array.dtype)))        
        # print("Reference melody is shorter than chord array, padding the ending of the melody array.")
        # print("New size of reference melody array:", melody_array.shape)
        # print("New size of reference chord array:", chord_array.shape)
    elif melody_array.shape[0] > chord_array.shape[0]:
        chord_array = np.concatenate((chord_array, np.zeros((melody_array.shape[0] - chord_array.shape[0], chord_array.shape[1]), dtype=chord_array.dtype)))        
        # print("Reference chord array is shorter than melody array, padding the ending of the chord array.")
        # print("New size of reference melody array:", melody_array.shape)
        # print("New size of reference chord array:", chord_array.shape)

    # Make sure arrays are padded to be divisible by window_size
    total_length = in_mar.shape[0]
    if total_length % window_size != 0:
        total_length = ((total_length // window_size) + 1) * window_size

    # Pad both input and reference arrays to the same length
    if in_mar.shape[0] < total_length:
        in_mar = np.concatenate((in_mar, np.zeros(total_length - in_mar.shape[0], dtype=in_mar.dtype)))
        in_car = np.concatenate((in_car, np.zeros((total_length - in_car.shape[0], in_car.shape[1]), dtype=in_car.dtype)))
        
    if melody_array.shape[0] < total_length:
        melody_array = np.concatenate((melody_array, np.zeros(total_length - melody_array.shape[0], dtype=melody_array.dtype)))
        chord_array = np.concatenate((chord_array, np.zeros((total_length - chord_array.shape[0], chord_array.shape[1]), dtype=chord_array.dtype)))

    return in_mar, in_car, melody_array, chord_array, total_length

if __name__ == "__main__":
    # Setup torch
    global device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # initialize the model
    ec2vae_model = EC2VAE.init_model()

    # load model parameter
    ec2vae_param_path = '../icm-deep-music-generation/ec2vae/model_param/ec2vae-v1.pt'
    # ec2vae_param_path = '../EC2-VAE/params_128.pt'
    ec2vae_model.load_model(ec2vae_param_path)

    from pprint import pprint
    import random
    import time
    directory = "./GP_Melody_Chords"  # Replace with your actual directory path
    pickle_filename = "song_data.pkl"
    pickle_path = os.path.join(directory, pickle_filename)

    input_melody = input("Pick an input test, or press Enter to pick the default test:")
    if not input_melody:
        input_melody = "test_midis/messtest.mid"

    # Load the data dictionary from the pickle file
    if os.path.exists(pickle_path):
        with open(pickle_path, "rb") as f:
            data_dict = pickle.load(f)
    else:
        # print("Pickle not found. Processing directory...")
        processed_data = process_directory_to_ec2vae_pickle(directory)
        with open(pickle_path, "rb") as f:
            data_dict = pickle.load(f)
    
    print("Available songs:\n")
    pprint(list(data_dict.keys()))
    melody_array, chord_array = song_select()
    ms = chords.MIDI_Stream(input_melody)
    full_chords = ms.get_full_chord_list()
    rbm, rbm_path = rule_based_melody(full_chords, bpm=120, debug=False)
    
    start = time.time()

    in_mar = midi_to_melody_array(rbm_path)
    in_car = m21_to_one_hot(full_chords)
    
    # print("Size of reference melody array:", melody_array.shape[0])
    # print("Size of reference chord array:", chord_array.shape[0])

    # print("Size of input melody array:", in_mar.shape[0])
    # print("Size of input chord array:", in_car.shape[0])
    
    final_prediction = None
    window_size = 32

    in_mar, in_car, melody_array, chord_array, total_length = prepare_windows(in_mar, in_car, melody_array, chord_array, window_size=window_size)
    # print(f"Processing {total_length//window_size} windows of size {window_size}")

    # Process each window
    print("total length:" , total_length)
    for i in range(0, total_length, window_size):
        window_index = i//window_size + 1
        # print(f"Processing window {window_index}/{total_length//window_size}")
        
        # Get the current window
        in_mar_window = in_mar[i:i+window_size]
        in_car_window = in_car[i:i+window_size]
        melody_window = melody_array[i:i+window_size]
        chord_window = chord_array[i:i+window_size]
        
        # Encode both input and reference
        zp1, zr1, c1 = encode(in_mar_window, in_car_window, viz=False)
        zp2, zr2, c2 = encode(melody_window, chord_window, viz=False)
        
        # print("Encoded size:", zp1.shape, zr1.shape, zp2.shape, zr2.shape)
        # Create prediction using input's latent pitch and reference's latent rhythm
        prediction_window = decode(zp2, zr2, c1, viz=False)
        
        # Append the prediction window to our final prediction
        if final_prediction is None:
            final_prediction = prediction_window
        else:
            final_prediction = np.concatenate((final_prediction, prediction_window))
    # print("Size of the final prediction:", final_prediction.shape)
    # Generate MIDI from the final prediction
    end = time.time()
    print("Time taken:", end-start, "\nPrediction Array:")
    pprint(final_prediction)
    start = time.time()
    generate_midi(final_prediction, "vae_test.mid", bpm=120, start=0.)
    end = time.time()
    print("MIDI gen time taken:", end-start)
