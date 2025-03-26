
from pickler import process_directory_to_pickle
import chords
import melody
import os
import pickle
import numpy as np
import torch
import pretty_midi as pm
import matplotlib.pyplot as plt
import sys
sys.path.append('../icm-deep-music-generation')
from ec2vae.model import EC2VAE

def note_array_to_onehot(note_array):
    pr = np.zeros((len(note_array), 130))
    pr[np.arange(0, len(note_array)), note_array.astype(int)] = 1.
    return pr

def encode_midi(melody_array, chord_array, viz=False):
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
    return zp1, zr1

def decode_latents(latent_pitch, latent_rhythm, viz=False):
    global device
    # decode
    m1h_prediction = ec2vae_model.decoder(latent_pitch, latent_rhythm) # predicted representation
    m1h_prediction = m1h_prediction.squeeze(0).cpu().numpy() # remove batch dimension
    if viz:
        plt.imshow(m1h_prediction, aspect='auto')
        plt.title('Display m1h_prediction')
        plt.show()
    return m1h_prediction

def generate_midi(melody_array, file_path, bpm=120, start=0., chord_array=None):
    notes_recon = ec2vae_model.__class__.note_array_to_notes(melody_array, bpm=bpm, start=start)
    if chord_array is not None:
        notes_chords = ec2vae_model.__class__.chord_to_notes(chord_array.squeeze(0).cpu().numpy(), bpm, start)


if __name__ == "__main__":
    # Setup torch
    global device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # initialize the model
    ec2vae_model = EC2VAE.init_model()

    # load model parameter
    ec2vae_param_path = '../icm-deep-music-generation/ec2vae/model_param/ec2vae-v1.pt'
    ec2vae_model.load_model(ec2vae_param_path)

    from pprint import pprint
    import random
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
        print("Pickle not found. Processing directory...")
        processed_data = process_directory_to_pickle(directory)
        with open(pickle_path, "rb") as f:
            data_dict = pickle.load(f)
    
    print("Available songs:\n")
    pprint(list(data_dict.keys()))

    song_key = input("Pick a song, or press Enter to pick a random song:")
    if not song_key:
        song_key = random.choice(list(data_dict.keys()))
        melody_array = data_dict[song_key]["melody"]
        chord_array = data_dict[song_key]["chords"]
        print("Melody array for", song_key, ":", melody_array)
        print("Chord array for", song_key, ":", chord_array)
    elif song_key in data_dict:
        melody_array = data_dict[song_key]["melody"]
        chord_array = data_dict[song_key]["chords"]
        print("Melody array for", song_key, ":", melody_array)
        print("Chord array for", song_key, ":", chord_array)
    else:
        print(f"Song key '{song_key}' not found in the dictionary.")
    