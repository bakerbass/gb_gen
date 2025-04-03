# ec2vae_encode.py
import os
import numpy as np
import math
from music21 import note, converter

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
