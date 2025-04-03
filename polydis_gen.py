from pickler import process_directory_to_ec2vae_pickle, midi_to_melody_array, m21_to_one_hot
import chords
import os
import pickle
import numpy as np
import torch
import pretty_midi as pm
import matplotlib.pyplot as plt
import sys
import readline
from polydis_encode import midi_to_prmat, midi_to_pianotree, midi_to_chordvec
sys.path.append('../icm-deep-music-generation')
from poly_dis.model import PolyDisVAE

def note_array_to_onehot(note_array):
    pr = np.zeros((len(note_array), 130))
    pr[np.arange(0, len(note_array)), note_array.astype(int)] = 1.
    return pr

# def encode(melody_array, chord_array, viz=False):
#     global device
#     m1h = note_array_to_onehot(melody_array) # melody one-hot
#     if viz:
#         plt.imshow(m1h, aspect='auto')
#         plt.title('Display pr1')
#         plt.show()
#     # to pytorch tensor, float32, gpu-ify, add batch dimension
#     pm1h = torch.from_numpy(m1h).float().to(device).unsqueeze(0) # pytorch melody 1-hot
#     pc1h = torch.from_numpy(chord_array).float().to(device).unsqueeze(0) # pytorch chord 1-hot

#     zp1, zr1 = ec2vae_model.encoder(pm1h, pc1h) # latent pitch encoding, latent rhythm encoding
#     return zp1, zr1, pc1h

# def decode(latent_pitch, latent_rhythm, chord_condition, viz=False):
#     global device
#     # decode
#     m1h_prediction = ec2vae_model.decoder(latent_pitch, latent_rhythm, chord_condition) # predicted representation
#     m1h_prediction = m1h_prediction.squeeze(0).cpu().numpy() # remove batch dimension
#     if viz:
#         plt.imshow(m1h_prediction, aspect='auto')
#         plt.title('Display m1h_prediction')
#         plt.show()
#     return m1h_prediction

def generate_midi(input_array, file_path, bpm=120, start=0., chord_array=None):
    midi = pm.PrettyMIDI()
    notes = polydis_model.pnotree_to_notes(input_array, bpm=120, start=0.)
    instrument = pm.Instrument(0)
    instrument.notes = notes
    midi.instruments.append(instrument)

    # mel_notes = ec2vae_model.__class__.note_array_to_notes(melody_array, bpm=bpm, start=start)
    # ins1 = pm.Instrument(0)
    # ins1.notes = mel_notes
    # midi.instruments.append(ins1)
    # if chord_array is not None:
    #     c_notes = ec2vae_model.__class__.chord_to_notes(chord_array.numpy(), bpm, start)
    #     ins2 = pm.Instrument(0)
    #     ins2.notes = c_notes
    #     midi.instruments.append(ins2)

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
    if not song_key or song_key not in data_dict:
        print("Picking a random song.")
        song_key = random.choice(list(data_dict.keys()))

    ref_pr = data_dict[song_key]["pr_mat"]
    ref_pt = data_dict[song_key]["ptree"]
    ref_c  = data_dict[song_key]["c"]

    return ref_pr, ref_pt, ref_c

def prepare_windows(in_pt, in_pr, in_c, ref_pr, ref_pt, ref_c, window_size=32):

    # Make sure arrays are padded to be divisible by window_size
    total_length = in_pr.shape[1]
    if total_length % window_size != 0:
        total_length = ((total_length // window_size) + 1) * window_size

    # Pad both input and reference arrays to the same length
    if in_pt.shape[0] < total_length:
        in_pt = np.concatenate((in_pt, np.zeros((total_length - in_pt.shape[0], in_pt.shape[1]), dtype=in_pt.dtype)))
        in_c = np.concatenate((in_c, np.zeros((total_length - in_c.shape[0], in_c.shape[1]), dtype=in_c.dtype)))
        
    if ref_pr.shape[0] < total_length:
        ref_pr = np.concatenate((ref_pr, np.zeros((total_length - ref_pr.shape[0], ref_pr.shape[1]), dtype=ref_pr.dtype)))
        ref_c = np.concatenate((ref_c, np.zeros((total_length - ref_c.shape[0], ref_c.shape[1]), dtype=ref_c.dtype)))

    return in_pt, in_pr, in_c, ref_pt, ref_pr, ref_c, total_length

if __name__ == "__main__":
    # Setup torch
    global device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # initialize the model
    polydis_model = PolyDisVAE.init_model()

    # load model parameter
    polydis_param_path = '../icm-deep-music-generation/poly_dis/model_param/polydis-v1.pt'
    # ec2vae_param_path = '../EC2-VAE/params_128.pt'
    polydis_model.load_model(polydis_param_path)

    from pprint import pprint
    import random
    import time
    directory = "./"  # Replace with your actual directory path
    pickle_filename = "polydis_data.pkl"
    pickle_path = os.path.join(directory, pickle_filename)

    input_midi = input("Pick an input test, or press Enter to pick the default test:")
    if not input_midi:
        input_midi = "test_midis/messtest.mid"

    # Load the data dictionary from the pickle file
    if os.path.exists(pickle_path):
        with open(pickle_path, "rb") as f:
            data_dict = pickle.load(f)
    else:
        print("Pickle not found.")
        pass
    
    # print("Available songs:\n")
    # pprint(list(data_dict.keys()))
    ref_pr, ref_pt, ref_c = song_select()

    start = time.time()

    in_pr = midi_to_prmat(input_midi)
    in_pt = midi_to_pianotree(input_midi)
    in_c  = midi_to_chordvec(input_midi)
    
    # print("Size of reference melody array:", melody_array.shape[0])
    # print("Size of reference chord array:", chord_array.shape[0])

    # print("Size of input melody array:", in_pt.shape[0])
    # print("Size of input chord array:", in_c.shape[0])
    
    final_prediction = None
    window_size = 32

    in_pr, in_pt, in_c, ref_pt, ref_pr, ref_c, total_length = prepare_windows(in_pr, in_pt, in_c, ref_pr, ref_pt, ref_c, window_size=window_size)
    # print(f"Processing {total_length//window_size} windows of size {window_size}")

    # Process each window
    print("total length:" , total_length)
    for i in range(0, total_length, window_size):
        window_index = i//window_size + 1
        # print(f"Processing window {window_index}/{total_length//window_size}")
        
        # Get the current window
        in_pr_window = in_pr[i:i+window_size]
        in_c_window = in_c[i:i+window_size:4]
        ref_pr_window = ref_pr[i:i+window_size]
        ref_c_window = ref_c[i:i+window_size:4]
        
        in_pr_window  = torch.from_numpy(in_pr_window).float().to(device).unsqueeze(0)
        in_c_window = torch.from_numpy(in_c_window).float().to(device).unsqueeze(0)

        ref_pr_window  = torch.from_numpy(ref_pr_window).float().to(device).unsqueeze(0)
        ref_c_window = torch.from_numpy(ref_c_window).float().to(device).unsqueeze(0)
        # print(in_pr_window.shape)
        # Encode both input and reference
        zchd_i = polydis_model.chd_encode(in_c_window)
        ztxt_i = polydis_model.txt_encode(in_pr_window)
        
        zchd_r = polydis_model.chd_encode(ref_c_window)
        ztxt_r = polydis_model.txt_encode(ref_pr_window)
        
        # print("Encoded size:", zp1.shape, zr1.shape, zp2.shape, zr2.shape)
        # Create prediction using input's latent pitch and reference's latent rhythm
        prediction_window = polydis_model.pnotree_decode(zchd_i, ztxt_r).squeeze(0)
            
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
    generate_midi(final_prediction, "pdis_test.mid", bpm=120, start=0.)
    end = time.time()
    print("MIDI gen time taken:", end-start)