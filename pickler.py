# pickler.py

import os
import pickle
import numpy as np
import math
from music21 import stream, note, midi, harmony, converter
import chords
from ec2vae_encode import m21_to_one_hot, midi_to_melody_array
from polydis_encode import midi_to_prmat, midi_to_pianotree, midi_to_chordvec, merge_instruments_to_single_track

def process_directory_to_ec2vae_pickle(directory, pickle_filename="vae_data.pkl"):
    """
    Iterates over the directory, processes each melody and chord file pair,
    and stores the resulting melody and chord arrays in a dictionary.
    
    Keys are derived from the filename suffix (the common part after the prefix).
    Values are dictionaries with keys 'melody' and 'chords'.
    
    The dictionary is saved to a pickle file.
    """
    # Get list of all files
    all_files = os.listdir(directory)
    
    # Filter files based on prefixes
    melody_files = [f for f in all_files if f.startswith("MELODY_")]
    chord_files = [f for f in all_files if f.startswith("CHORDS_")]
    
    # Build a lookup for chord files: key = file suffix, value = full filename
    chord_dict = {}
    for chord_file in chord_files:
        suffix = chord_file[len("CHORDS_"):]
        chord_dict[suffix] = chord_file
    
    # Dictionary to hold the processed arrays for each song.
    data_dict = {}
    
    # Process each melody file.
    for melody_file in melody_files:
        suffix = melody_file[len("MELODY_"):]
        if suffix in chord_dict:
            matching_chord_file = chord_dict[suffix]
            print(f"Processing pair: {melody_file}  <-->  {matching_chord_file}")
            
            # Construct full file paths.
            melody_path = os.path.join(directory, melody_file)
            chord_path  = os.path.join(directory, matching_chord_file)
            
            # Process the melody file to get its one-hot array.
            try:
                melody_array = midi_to_melody_array(melody_path)
            except Exception as e:
                print(f"Error processing melody {melody_file}: {e}")
                continue
            
            # Process the chord file to get its one-hot chord array.
            try:
                chord_stream = chords.MIDI_Stream(chord_path)
                full_chords = chord_stream.get_full_chord_list()
                chord_array = m21_to_one_hot(full_chords)
            except Exception as e:
                print(f"Error processing chords {matching_chord_file}: {e}")
                continue
            
            # Use the suffix (or any other identifier) as the key.
            data_dict[suffix] = {
                "melody": melody_array,
                "chords": chord_array
            }
        else:
            print(f"No matching chord file for {melody_file}")
    
    # Save the dictionary to a pickle file.
    with open(os.path.join(directory, pickle_filename), "wb") as f:
        pickle.dump(data_dict, f)
    
    print(f"Data saved to {pickle_filename}. Total songs processed: {len(data_dict)}")
    return data_dict


def process_directory_to_polydis_pickle(directory, pickle_filename="polydis_data.pkl", ec2_compatible_input=True):
    """
    Iterates over a directory, processes each MIDI file into PolyDis-compatible
    representations, and saves the results to a pickle file.
    
    Each entry in the dictionary has keys:
    - 'pr_mat' : (32, 128) piano-roll matrix
    - 'ptree'  : (32, 16, 6) PianoTree representation
    - 'c'      : (8, 36) chord matrix
    
    Parameters:
        directory (str): Path to the folder containing MIDI files.
        pickle_filename (str): Filename to save the resulting pickle dictionary.
        ec2_compatible_input (bool): If True, processes files with specific chord/melody prefixes.
    """
    midi_files = [f for f in os.listdir(directory) if f.lower().endswith(".mid") or f.lower().endswith(".midi")]
    
    # Filter files based on prefixes
    data_dict = {}
    if not ec2_compatible_input:
        for midi_file in midi_files:
            midi_path = os.path.join(directory, midi_file)
            try:
                print(f"Processing: {midi_file}")
                merged_midi = merge_instruments_to_single_track(midi_path)
                temp_path = os.path.join(directory, "__temp_merged__.mid")
                merged_midi.write(temp_path)
                prmat = midi_to_prmat(temp_path)
                ptree = midi_to_pianotree(temp_path)
                chordvec = midi_to_chordvec(temp_path)

                data_dict[midi_file] = {
                    "pr_mat": prmat,
                    "ptree": ptree,
                    "c": chordvec
                }

                os.remove(temp_path)
                
            except Exception as e:
                print(f"Error processing {midi_file}: {e}")
                continue
    else:
        melody_files = [f for f in midi_files if f.startswith("MELODY_")]
        chord_files = [f for f in midi_files if f.startswith("CHORDS_")]
        for melody_file in melody_files:
            suffix = melody_file[len("MELODY_"):]
            if suffix in chord_files:
                print(f"Processing pair: {melody_file}  <-->  CHORDS_{suffix}")
                melody_path = os.path.join(directory, melody_file)
                chord_path = os.path.join(directory, "CHORDS_" + suffix)
                
                try:
                    combined = merge_instruments_to_single_track(melody_path, chord_path)
                    combined_path = os.path.join(directory, "__temp_combined__.mid")
                    combined.write(combined_path)
                    prmat = midi_to_prmat(combined_path)
                    ptree = midi_to_pianotree(combined_path)
                    chordvec = midi_to_chordvec(combined_path)

                    data_dict[suffix] = {
                        "pr_mat": prmat,
                        "ptree": ptree,
                        "c": chordvec
                    }

                    os.remove(os.path.join(directory, "__temp_combined__.mid"))

                except Exception as e:
                    print(f"Error processing {melody_file} or {chord_path}: {e}")
                    continue

    # Save to pickle
    with open(os.path.join(directory, pickle_filename), "wb") as f:
        pickle.dump(data_dict, f)

    print(f"PolyDis-compatible data saved to {pickle_filename}. Total files processed: {len(data_dict)}")
    return data_dict

if __name__ == "__main__":
    from pprint import pprint
    import random
    directory = "./GP_Melody_Chords"  # Replace with your actual directory path
    pickle_filename = "polydis_data.pkl"
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
        processed_data = process_directory_to_polydis_pickle(directory, pickle_filename=pickle_filename, ec2_compatible_input=True)
        with open(pickle_path, "rb") as f:
            data_dict = pickle.load(f)
    
    print("Available songs:\n")
    pprint(list(data_dict.keys()))

    # song_key = input("Pick a song, or press Enter to pick a random song:")
    # if not song_key:
    #     song_key = random.choice(list(data_dict.keys()))
    #     melody_array = data_dict[song_key]["melody"]
    #     chord_array = data_dict[song_key]["chords"]
    #     print("Melody array for", song_key, ":", melody_array)
    #     print("Chord array for", song_key, ":", chord_array)
    # elif song_key in data_dict:
    #     melody_array = data_dict[song_key]["melody"]
    #     chord_array = data_dict[song_key]["chords"]
    #     print("Melody array for", song_key, ":", melody_array)
    #     print("Chord array for", song_key, ":", chord_array)
    # else:
    #     print(f"Song key '{song_key}' not found in the dictionary.")
    


""" Old main from melody.py
if __name__ == "__main__":
    import os
    import chords
    from pprint import pprints
    # Example pluck_message output (for instance, from rule_based_melody).
    # Each entry: [midi, duration (sec), speed, timestamp]
    chord_stream = chords.MIDI_Stream("test_midis/slashchords.mid")
    full_chords = chord_stream.get_full_chord_list()
    oh_chords = m21_to_one_hot(full_chords)
    oh_mel = midi_to_melody_array("test_midis/slashsolo.mid")
    pprint(oh_chords)
    pprint(oh_mel)
    directory = "./GP_Melody_Chords"  # Replace with your actual directory

    # List all files in the directory
    all_files = os.listdir(directory)

    # Filter files based on their prefixes.
    melody_files = [f for f in all_files if f.startswith("MELODY_")]
    chord_files = [f for f in all_files if f.startswith("CHORDS_")]

    # Build a dictionary for quick lookup: key = file suffix (after the prefix), value = chord file name.
    chord_dict = {}
    for chord_file in chord_files:
        suffix = chord_file[len("CHORDS_"):]
        chord_dict[suffix] = chord_file

    # Iterate over each melody file and find its matching chord file.
    for melody_file in melody_files:
        suffix = melody_file[len("MELODY_"):]
        if suffix in chord_dict:
            matching_chord_file = chord_dict[suffix]
            print(f"Found pair: {melody_file}  <-->  {matching_chord_file}")
            chord_stream = chords.MIDI_Stream(os.path.join(directory,matching_chord_file))
            full_chords = chord_stream.get_full_chord_list()
            try:
                oh_chords = m21_to_one_hot(full_chords)
            except ValueError as e:
                print(f"Error processing {matching_chord_file}: {e}")
            oh_mel = midi_to_melody_array(os.path.join(directory,melody_file))
        else:
            print(f"No matching chord file for {melody_file}")
"""