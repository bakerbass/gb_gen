from music21 import stream, note, midi, harmony, converter
import random
import math
import numpy as np
import re
from pprint import pprint

def map_speed(midi_value, min_midi=50, max_midi=68, speed_mode="direct", default_speed=7):
    """
    Map a MIDI note value to a speed based on the given speed mode.
    
    Parameters:
        midi_value (int): The MIDI value of the note.
        min_midi (int): Minimum MIDI value for the intended range.
        max_midi (int): Maximum MIDI value for the intended range.
        speed_mode (str): Mode to determine speed. Options include:
            - "random": Assign a random speed between 1 and 10.
            - "direct" or "proportional": Map linearly based on the MIDI range.
            - "inverse" or "inversely": Inverse mapping.
            - Any other value returns the default speed.
        default_speed (int): The fallback speed value when no other mapping applies.
    
    Returns:
        int: The computed speed value.
    """
    if speed_mode == "random":
        return random.randint(1, 10)
    elif speed_mode in ("direct", "proportional"):
        return int((midi_value - min_midi) / (max_midi - min_midi) * 9) + 1
    elif speed_mode in ("inverse", "inversely"):
        return int(9 / (midi_value - min_midi + 1)) + 1
    else:
        return default_speed

def rule_based_melody(full_chords, bpm=100, debug=True, speed_mode="direct"):
    number_of_chords = len(full_chords)
    print("Number of chords:", number_of_chords)
    melody = stream.Stream()
    pluck_message = []  # Each entry: [midi value, duration (seconds), speed, timestamp]
    time_cursor = 0     # Running timestamp (in seconds)
    default_speed = 7   # Fallback speed value
    quarter_note_duration = 60 / bpm

    prev_n = None         # Previous note (music21 note)
    prev_pluck_idx = None # Index of last pluck_message entry

    # Define minimum and maximum MIDI values used for speed mapping.
    min_midi = 50
    max_midi = 68

    for chord in full_chords:
        # Handle unknown chords: instead of a rest, extend the previous note.
        m21chord = chord[1].pitches
        if len(m21chord) == 0:
            continue
        if chord[0] == "Chord Symbol Cannot Be Identified":
            if prev_n is not None:
                extend_amt = quarter_note_duration
                prev_n.quarterLength += 1
                pluck_message[prev_pluck_idx][1] += extend_amt
                if debug:
                    print("Extended previous note to duration", prev_n.quarterLength)
            else:
                if debug:
                    print("Unknown chord with no previous note; skipping extension.")
            time_cursor += quarter_note_duration
            continue

        # Get a random pitch from the chord.
        if len(m21chord) > 1:
            if debug:
                print("Multiple pitches available; choosing one at random.")
            random_index = random.randint(0, len(m21chord) - 1)
        else:
            random_index = 0
        random_mel_pitch = m21chord[random_index]
        n = note.Note(random_mel_pitch, type="quarter")

        # Adjust note so that its MIDI value is within [min_midi, max_midi].
        if n.pitch.midi < min_midi:
            if debug:
                print("Note", n.pitch, "is below", min_midi, "— adjusting upward...")
            while n.pitch.midi < min_midi:
                n.pitch.octave += 1
            if debug:
                print("Adjusted to", n.pitch)
        elif n.pitch.midi > max_midi:
            if debug:
                print("Note", n.pitch, "is above", max_midi, "— adjusting downward...")
            while n.pitch.midi > max_midi:
                n.pitch.octave -= 1
            if debug:
                print("Adjusted to", n.pitch)

        # Get the speed value using the helper function.
        speed_value = map_speed(n.pitch.midi, min_midi, max_midi, speed_mode, default_speed)
        
        # Average with the previous note's speed, if any.
        speed_value = int(0.5 * (speed_value + (pluck_message[prev_pluck_idx][2] if prev_pluck_idx is not None else speed_value + 1)))
        
        # Merge notes if the same as the previous note.
        if prev_n is not None and n.pitch.midi == prev_n.pitch.midi:
            if debug:
                print("Merging note", n.pitch, "with previous note.")
            prev_n.quarterLength += n.quarterLength
            pluck_message[prev_pluck_idx][1] += n.quarterLength * quarter_note_duration
        else:
            melody.append(n)
            pluck_message.append([
                n.pitch.midi,
                n.quarterLength * quarter_note_duration,
                speed_value,
                time_cursor
            ])
            prev_n = n
            prev_pluck_idx = len(pluck_message) - 1

        time_cursor += n.quarterLength * quarter_note_duration

    file_path = "rule_based_melody.mid"
    melody.write("midi", file_path)
    return pluck_message, file_path

def remix(data):
    out = np.copy(data)
    note_indices = np.where(data < 128)[0]
    for i in range(len(note_indices)):
        idx = note_indices[i]
        shift = (i % 5) - 2  # create rising and falling echoes
        new_idx = idx + shift
        if 0 <= new_idx < len(data):
            if data[new_idx] >= 128:  # only overwrite if original is rest
                out[new_idx] = data[idx]
    return out

def melody_to_array(pluck_message, bpm=100, 
                    sustain_value=128, rest_value=129, 
                    pitch_min=0, pitch_max=127):
    """
    Converts a melody (given as pluck_message entries) into a quantized array format.
    
    Parameters:
      pluck_message: list of [midi value, duration (seconds), speed, timestamp]
      bpm: beats per minute used during generation.
      sustain_value: integer value to mark sustained notes (default 128).
      rest_value: integer value to mark rests (default 129).
      (Only MIDI values in the range 0-127 are considered actual pitches.)
      
    Returns:
      A NumPy array where each element is an integer representing a note event:
        - 0-127: MIDI pitch
        - sustain_value: sustain marker
        - rest_value: rest marker
      The array is quantized so that each element represents one 16th note.
    """
    # Duration of one 16th note in seconds.
    step = 60 / (bpm * 4)
    
    # Determine the total duration from the pluck_message.
    end_times = [entry[3] + entry[1] for entry in pluck_message]
    total_duration = max(end_times) if end_times else 0
    # Calculate the total number of 16th-note steps (ensure at least 1 step).
    num_steps = max(1, math.ceil(total_duration / step))
    
    # Initialize array with rest markers.
    melody_array = np.full(num_steps, rest_value, dtype=int)
    
    # For each note, fill the corresponding steps.
    for entry in pluck_message:
        pitch, duration_sec, speed, onset_sec = entry
        # Compute start index and note length in time steps:
        start_idx = int(round(onset_sec / step))
        note_steps = max(1, int(round(duration_sec / step)))
        # Set first step to the note's pitch.
        if start_idx < num_steps:
            melody_array[start_idx] = pitch
        # Set subsequent steps (if any) to sustain marker.
        for idx in range(start_idx + 1, min(start_idx + note_steps, num_steps)):
            melody_array[idx] = sustain_value
    return melody_array


# def midi_to_gbarray(midi_file_path, bpm=100, debug=True)
    
def midi_to_gb_array(midi_file, bpm=100, speed_mode="direct", debug=False):
    """
    Convert a monophonic MIDI file into an array of [MIDI note number, duration, speed, ontime].
    
    Parameters:
        midi_file (str): Path to the MIDI file.
        bpm (int): Beats per minute (used to convert quarter note durations to seconds).
        speed_mode (str): Selects which speed mapping to use (currently only "direct" is implemented).
        debug (bool): If True, prints debugging output.
    
    Returns:
        list: A list of lists where each inner list has the form
              [MIDI note number, duration in seconds, speed, onset time in seconds].
    """
    # Parse the MIDI file using music21.
    score = converter.parse(midi_file)
    
    # Get all the Note objects from the score; assuming the melody is monophonic.
    notes = score.flat.getElementsByClass(note.Note)
    
    # Calculate the duration (in seconds) of a quarter note.
    quarter_duration = 60.0 / bpm
    
    melody_array = []
    
    # Iterate through the notes to extract the desired attributes.
    for n in notes:
        midi_val = n.pitch.midi
        # Duration in seconds: note duration in quarter lengths * quarter note duration.
        duration_sec = n.duration.quarterLength * quarter_duration
        # Onset time in seconds: note offset (in quarter lengths) * quarter note duration.
        ontime_sec = n.offset * quarter_duration
        
        # Compute speed using the helper function. Here speed_mode is not used for alternatives,
        # but you could extend this logic if you want multiple modes.
        speed_val = map_speed(midi_val)
        
        if debug:
            print(f"Note: {n.pitch}, MIDI: {midi_val}, Duration: {duration_sec:.2f}s, "
                  f"Ontime: {ontime_sec:.2f}s, Speed: {speed_val}")
        
        melody_array.append([midi_val, round(duration_sec, 5), speed_val, round(ontime_sec, 5)])
    
    return melody_array