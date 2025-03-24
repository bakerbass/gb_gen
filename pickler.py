# pickler.py

import os
import pickle
import numpy as np
import math
from music21 import stream, note, midi, harmony, converter
import chords

def chord_to_one_hot(chord_obj):
    """
    Convert a music21 chord object to a 12-dimensional one-hot vector.
    
    Parameters:
    chord_obj: a music21.chord.Chord instance
    
    Returns:
    A list of 12 integers, where a 1 indicates that the pitch class is present.
    """
    one_hot = [0] * 12
    # Get a list of unique pitch classes (0-11) in the chord.
    for note in chord_obj.orderedPitchClasses:
        one_hot[note] = 1
    return one_hot

def m21_to_one_hot(full_chords):
    one_hot_chords = np.zeros((len(full_chords) * 4, 12), dtype=int)
    idx = 0
    for chord in full_chords:
        oh = chord_to_one_hot(chord[1])
        one_hot_chords[idx:idx + 3] = oh
        idx += 4
    return one_hot_chords


def midi_to_melody_array(midi_file, bpm=120, 
                              sustain_value=128, rest_value=129):
    """
    Converts a monophonic MIDI file into a quantized melody array.
    
    Parameters:
      midi_file: path to the monophonic MIDI file.
      bpm: beats per minute to interpret the note durations.
      sustain_value: marker for sustained note values (default 128).
      rest_value: marker for rests (default 129).
    
    Returns:
      A NumPy array where each element represents a 16th note:
        - 0-127: MIDI pitch value
        - sustain_value (128): sustain marker
        - rest_value (129): rest marker
      
      The grid is computed assuming one 16th note = 60/(bpm*4) seconds.
    """
    # Parse the MIDI file using music21.
    midi_stream = converter.parse(midi_file).flat.notes
    
    # If bpm is not provided by the file metadata, we assume the given bpm.
    quarter_sec = 60 / bpm          # Duration of a quarter note in seconds.
    step = quarter_sec / 4          # 16th note step in seconds.

    # Create a list of note events: each entry is [pitch, duration_sec, onset_sec]
    events = []
    for n in midi_stream:
        # Only consider actual Note objects (ignoring rests).
        if isinstance(n, note.Note):
            onset_sec = n.offset * quarter_sec  # n.offset is in quarter lengths.
            duration_sec = n.duration.quarterLength * quarter_sec
            events.append([n.pitch.midi, duration_sec, onset_sec])
    
    # Determine total duration in seconds.
    if events:
        end_time = max(onset + dur for _, dur, onset in events)
    else:
        end_time = 0

    num_steps = max(1, int(math.ceil(end_time / step)))
    melody_array = np.full(num_steps, rest_value, dtype=int)

    # For each note event, quantize its onset and duration:
    for pitch, duration_sec, onset_sec in events:
        start_idx = int(round(onset_sec / step))
        note_steps = max(1, int(round(duration_sec / step)))
        if start_idx < num_steps:
            melody_array[start_idx] = pitch
        # Mark sustained steps.
        for i in range(start_idx + 1, min(start_idx + note_steps, num_steps)):
            melody_array[i] = sustain_value

    return melody_array

def process_directory_to_pickle(directory, pickle_filename="song_data.pkl"):
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

if __name__ == "__main__":
    from pprint import pprint
    import random
    directory = "./GP_Melody_Chords"  # Replace with your actual directory path
    pickle_filename = "song_data.pkl"
    pickle_path = os.path.join(directory, pickle_filename)

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
    
""" Old main from melody.py
if __name__ == "__main__":
    import os
    import chords
    from pprint import pprint
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