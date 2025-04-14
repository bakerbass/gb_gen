import numpy as np
import torch
import pretty_midi as pm
import matplotlib.pyplot as plt
import sys
import os
import pickle
import random
from pprint import pprint

sys.path.append('../icm-deep-music-generation')
from ec2vae.model import EC2VAE
from pickler import process_directory_to_ec2vae_pickle, midi_to_melody_array, m21_to_one_hot
import chords
from melody import rule_based_melody, remix

class EC2Generator:
    def __init__(self, model_path=None, pickle_path=None):
        """
        Initialize the EC2Generator with the model and data dictionary.
        
        Args:
            model_path: Path to the EC2VAE model parameters.
            pickle_path: Path to the pickled song data.
        """
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.ec2vae_model = EC2VAE.init_model()
        
        # Load the model
        if model_path:
            self.ec2vae_model.load_model(model_path)
        else:
            default_path = './icm-deep-music-generation/ec2vae/model_param/ec2vae-v1.pt'
            self.ec2vae_model.load_model(default_path)
        
        # Load the data dictionary
        self.pickle_path = pickle_path or "./GP_Melody_Chords/ec2_with_UJB.pkl"
        self.data_dict = self.load_data_pickle()
        
    def load_data_pickle(self):
        """
        Loads and returns the data dictionary from a pickle file.
        """
        if os.path.exists(self.pickle_path):
            with open(self.pickle_path, "rb") as f:
                return pickle.load(f)
        else:
            directory = os.path.dirname(self.pickle_path)
            return process_directory_to_ec2vae_pickle(directory)
    
    def note_array_to_onehot(self, note_array):
        """Convert melody to one-hot encoding"""
        pr = np.zeros((len(note_array), 130))
        pr[np.arange(len(note_array)), note_array.astype(int)] = 1.
        return pr
    
    def encode(self, melody_array, chord_array, viz=False):
        """Encode melody and chord arrays into latent representations."""
        m1h = self.note_array_to_onehot(melody_array)
        if viz:
            plt.imshow(m1h, aspect='auto')
            plt.title('Melody One-Hot')
            plt.show()
        pm1h = torch.from_numpy(m1h).float().to(self.device).unsqueeze(0)
        pc1h = torch.from_numpy(chord_array).float().to(self.device).unsqueeze(0)
        zp1, zr1 = self.ec2vae_model.encoder(pm1h, pc1h)
        return zp1, zr1, pc1h
    
    def decode(self, latent_pitch, latent_rhythm, chord_condition, viz=False):
        """Decode latent representations back to melody."""
        pred = self.ec2vae_model.decoder(latent_pitch, latent_rhythm, chord_condition)
        pred = pred.squeeze(0).cpu().numpy()
        if viz:
            plt.imshow(pred, aspect='auto')
            plt.title('Decoded Prediction')
            plt.show()
        return pred
    
    def generate_midi(self, melody_array, file_path, bpm=100, start=0., chord_array=None):
        """Generate MIDI file from melody array."""
        midi = pm.PrettyMIDI()
        mel_notes = self.ec2vae_model.__class__.note_array_to_notes(melody_array, bpm=bpm, start=start)
        ins1 = pm.Instrument(0)
        ins1.notes = mel_notes
        midi.instruments.append(ins1)
        if chord_array is not None:
            c_notes = self.ec2vae_model.__class__.chord_to_notes(chord_array.numpy(), bpm, start)
            ins2 = pm.Instrument(0)
            ins2.notes = c_notes
            midi.instruments.append(ins2)
        midi.write(file_path)
        
    def song_select(self, song_key=None):
        """Select a song from the data dictionary."""
        if not self.data_dict:
            raise ValueError("No song data available. Please load a valid data pickle.")
        
        if not song_key:
            song_key = input("Pick a song, or press Enter to pick Uncle Johns Band: ")
        if song_key == "":
            song_key = 'Grateful Dead - Uncle Johns Band.mid'
        elif song_key not in self.data_dict:
            print(f"Song key '{song_key}' not found, picking randomly.")
            song_key = random.choice(list(self.data_dict.keys()))
            
        song_data = self.data_dict[song_key]
        return song_key, self.data_dict[song_key]["melody"], self.data_dict[song_key]["chords"], song_data
    
    def prepare_windows(self, in_mar, in_car, melody_array, chord_array, window_size=32):
        """Prepare windows for processing."""
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
            in_mar = np.concatenate((in_mar, np.zeros(np.abs(total_length - in_mar.shape[0]), dtype=in_mar.dtype)))
            in_car = np.concatenate((in_car, np.zeros((np.abs(total_length - in_car.shape[0]), in_car.shape[1]), dtype=in_car.dtype)))
            melody_array = np.concatenate((melody_array, np.zeros(np.abs(total_length - melody_array.shape[0]), dtype=melody_array.dtype)))
            chord_array = np.concatenate((chord_array, np.zeros((np.abs(total_length - chord_array.shape[0]), chord_array.shape[1]), dtype=chord_array.dtype)))
        return in_mar, in_car, melody_array, chord_array, total_length
    
    def iterate_windows(self, in_mar, in_car, melody_array, chord_array, window_size=32, window_overlap=0):
        """Generator that yields windows of the input and reference arrays."""
        step_size = window_size - window_overlap
        total_length = in_mar.shape[0]
        for i in range(0, total_length - window_size + 1, step_size):
            yield (in_mar[i:i+window_size],
                in_car[i:i+window_size],
                melody_array[i:i+window_size],
                chord_array[i:i+window_size])
    
    def generate_prediction_for_one_song(self, song_key, song_data, window_size=32, window_overlap=0, test_midi=None, whatif_melody=False):
        """Generate prediction for one song."""
        print(f"Processing song: {song_key}")
        melody_array = song_data["melody"]
        chord_array = song_data["chords"]
        source = test_midi if test_midi is not None else song_data.get("source_midi", song_key)
        
        ms = chords.MIDI_Stream(source)
        full_chords = ms.get_full_chord_list()
        rbm, rbm_path = rule_based_melody(full_chords, bpm=100, debug=False)
        in_mar = midi_to_melody_array(rbm_path)
        in_car = m21_to_one_hot(full_chords)
        
        in_mar, in_car, melody_array, chord_array, total_length = self.prepare_windows(
            in_mar, in_car, melody_array, chord_array, window_size)
        
        final_prediction = None
        num_windows = 0
        for window in self.iterate_windows(in_mar, in_car, melody_array, chord_array, window_size, window_overlap):
            num_windows += 1
            in_mar_window, in_car_window, mel_window, ch_window = window
            zp1, zr1, c1 = self.encode(in_mar_window, in_car_window, viz=False)
            zp2, zr2, c2 = self.encode(mel_window, ch_window, viz=False)
            prediction_window = self.decode(zp1, zr2, c1, viz=False)
            
            if final_prediction is None:
                final_prediction = prediction_window
            else:
                final_prediction = np.concatenate((final_prediction, prediction_window))
        
        print(f"Processed {num_windows} windows for song: {song_key}")
        gb = self.prediction_to_guitarbot(final_prediction, bpm=100, default_speed=7, rbm=rbm)
        return final_prediction, gb
    
    def split_pluck_message(self, pluck_message, speed_offset, bpm):
        """Split pluck message into chunks."""
        pluck_message = np.array(pluck_message)
        if len(pluck_message) < 40:
            result = []
            for row in pluck_message:
                result.append([int(row[0]), round(float(row[1]), 5), int(row[2]), round(float(row[3]), 5)])
            return result
        
        chunked_messages = []
        chunk_size = 39
        last_note = [0, 0, 0, 0]
        pen_note = last_note
        qnd = 60 / bpm # quarter note duration in seconds
        # print("qnd: " + str(qnd))
        
        last_ot = 0
        split_range = range(0, len(pluck_message), chunk_size)
        for i in split_range:
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
    
        return chunked_messages
    
    def insert_metronome_pulses(self, gb_array, bpm=100, met_MNN=40, countin=True, interleave=False):
        """Insert metronome pulses into the GB array."""
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

    def prediction_to_guitarbot(self, ec2_array, bpm=100, rbm=None, default_speed=7):
        """Convert EC2 array to GuitarBot pluck messages."""
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
                # Create the new event: note, duration, speed, and ontime.
                speed = default_speed
                if rbm is not None:
                    # Find the most recent rbm row where rbm_row[3] <= current_time.
                    for row in reversed(rbm):
                        if row[3] <= current_time:
                            speed = row[2]
                            break
                    if speed > highest_speed:
                        # print(f"New highest speed: {speed}")
                        highest_speed = speed

                pluck_message.append([pitch, duration, speed, current_time])
                # Advance the current time by the duration of this note.
                current_time += duration
        
        speed_add = 9 - highest_speed
        # print(f"Speed add: {speed_add}")
        # print(f"Highest speed: {highest_speed}")

        pluck_message = self.insert_metronome_pulses(pluck_message, bpm=bpm, countin=True, interleave=True)
        # print("Before split: \n")
        # pprint(pluck_message)
        # print("\n")
        pluck_message = self.split_pluck_message(pluck_message, speed_add, bpm)
        # result = []
        # for chunk in pluck_message:
        # for row in pluck_message_chunk:
        #     print(row[2])
        #     if(int(row[2]) + speed_add > 9):
        #         print("wtf!")
        #     result.append([int(row[0]), round(float(row[1]), 5), int(row[2]) + speed_add, round(float(row[3]),5)])
        #     # Force columns 0 and 2 to be int, columns 1 and 3 to be floats.
        # pluck_message = result
        return pluck_message
    
    def save_prediction_to_midi(self, prediction, file_path, bpm=100, start=0.):
        """Save prediction as MIDI file."""
        midi_output_path = os.path.join("generated_midis", file_path)
        os.makedirs("generated_midis", exist_ok=True)
        self.generate_midi(prediction, midi_output_path, bpm=bpm, start=start)
        print(f"Saved generated MIDI to {midi_output_path}")