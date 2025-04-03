from music21 import stream, note, midi, harmony, converter
import random
import math
import numpy as np
import re

def rule_based_melody(full_chords, bpm=120, debug=False, speed_mode="direct"):
    number_of_chords = len(full_chords)
    melody = stream.Stream()
    pluck_message = []  # Each entry: [midi value, duration (seconds), speed, timestamp]
    time_cursor = 0     # Running timestamp (in seconds)
    default_speed = 7   # Fallback speed value
    quarter_note_duration = 60 / bpm

    prev_n = None         # Previous note (music21 note)
    prev_pluck_idx = None # Index of last pluck_message entry

    for chord in full_chords:
        # Unknown chord: instead of a rest, extend previous note.
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

        # Get random pitch from the chord.
        m21chord = chord[-1].pitches
        random_index = random.randint(0, len(m21chord) - 1)
        random_mel_pitch = m21chord[random_index]
        n = note.Note(random_mel_pitch, type="quarter")

        # Adjust note so that its MIDI value is within [40, 68]
        min_midi = 50
        max_midi = 68
        if n.pitch.midi < min_midi:
            if debug:
                print("Note", n.pitch, "is below 40, adjusting upward...")
            while n.pitch.midi < min_midi:
                n.pitch.octave += 1
            if debug:
                print("Adjusted to", n.pitch)
        elif n.pitch.midi > max_midi:
            if debug:
                print("Note", n.pitch, "is above 68, adjusting downward...")
            while n.pitch.midi > max_midi:
                n.pitch.octave -= 1
            if debug:
                print("Adjusted to", n.pitch)

        # Initial speed assignment (if not merged). We'll later adjust speeds
        if speed_mode == "random":
            speed_value = random.randint(1, 10)
        elif speed_mode in ("direct", "proportional"):
            speed_value = int((n.pitch.midi - min_midi) / (max_midi - min_midi) * 9) + 1
        elif speed_mode in ("inverse", "inversely"):
            int(9 / (n.pitch.midi - min_midi + 1)) + 1
        else:
            speed_value = default_speed
        # Average speed with previous note (if any)
        speed_value = int(0.5 * (speed_value + pluck_message[prev_pluck_idx][2] if prev_pluck_idx is not None else speed_value + 1))
        # Merge if same note as previous.
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

def melody_to_array(pluck_message, bpm, 
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
