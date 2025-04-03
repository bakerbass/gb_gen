from melody import rule_based_melody
import os
import numpy as np
import torch
import pretty_midi as pm

"""
Goals:
Convert "full_chords" to a chord array with the following format:
Chord: inner 36-d vecotr:
* 0-11: one-hot root (absolute pitch class)
* 12-23: multi-hot chroma (absolute pitch class)
* 24-35: one-hot bass (relative pitch class)t
"""
def merge_instruments_to_single_track(midi_path, midi_path2=None):
    """
    Loads a MIDI file and merges all instrument notes into a single track.
    
    Returns:
        merged_midi (pretty_midi.PrettyMIDI): MIDI with one merged instrument.
    """
    midi = pm.PrettyMIDI(midi_path)
    if midi_path2 is not None:
        midi2 = pm.PrettyMIDI(midi_path2)
        for instrument in midi2.instruments:
            if instrument.is_drum:  # Skip drum tracks
                print(f"Skipping drum track: {instrument.name}")
                continue
            midi.instruments.append(instrument)
    merged_instrument = pm.Instrument(program=0, is_drum=False, name="MergedTrack")

    for instrument in midi.instruments:
        if instrument.is_drum:  # Skip drum tracks
            print(f"Skipping drum track: {instrument.name}")
            continue
        merged_instrument.notes.extend(instrument.notes)
    
    # Sort notes by start time for proper processing
    merged_instrument.notes.sort(key=lambda n: n.start)
    
    # Create a new PrettyMIDI object with one instrument
    merged_midi = pm.PrettyMIDI()
    merged_midi.instruments.append(merged_instrument)
    return merged_midi

def quantize_time(time, grid=0.25):
    return round(time / grid) * grid

def midi_to_prmat(midi_path, num_steps=32):
    midi = pm.PrettyMIDI(midi_path)
    pr_mat = np.zeros((num_steps, 128))  # (time step, pitch)

    # Quantization reference
    grid = 0.25  # 16th notes

    for note in midi.instruments[0].notes:
        onset = quantize_time(note.start, grid)
        idx = int(onset / grid)
        if 0 <= idx < num_steps:
            pr_mat[idx, note.pitch] = note.end - note.start  # duration in beats
    return pr_mat

def midi_to_pianotree(midi_path, num_steps=32):
    midi = pm.PrettyMIDI(midi_path)
    ptree = [[] for _ in range(num_steps)]
    grid = 0.25  # 16th notes

    for note in midi.instruments[0].notes:
        onset = quantize_time(note.start, grid)
        idx = int(onset / grid)
        if 0 <= idx < num_steps:
            pitch = note.pitch
            dur = note.end - note.start
            dur_steps = int(dur / grid)
            dur_binary = [int(x) for x in bin(dur_steps)[2:].zfill(5)]  # 5-bit duration
            ptree[idx].append([pitch] + dur_binary)

    # Pad each frame to 16 notes
    for frame in ptree:
        while len(frame) < 16:
            frame.append([0] * 6)  # padding
        if len(frame) > 16:
            frame[:] = frame[:16]
    return np.array(ptree)
    

def midi_to_chordvec(midi_path, num_measures=8):
    # Very basic chroma extractor (you may replace this with better chord detection)
    midi = pm.PrettyMIDI(midi_path)
    chord_matrix = np.zeros((num_measures, 36))  # root (12), chroma (12), bass (12)
    grid = 0.25
    steps_per_measure = 4 / grid  # assuming 4/4 time, 1 bar = 4 beats = 16 steps

    for m in range(num_measures):
        start = m * steps_per_measure * grid
        end = (m + 1) * steps_per_measure * grid
        pitches = []

        for note in midi.instruments[0].notes:
            if note.start < end and note.end > start:
                pitches.append(note.pitch)

        if pitches:
            pitch_classes = [p % 12 for p in pitches]
            chroma = np.zeros(12)
            for pc in pitch_classes:
                chroma[pc] = 1

            bass = min(pitches) % 12
            root = pitch_classes[0]  # Simplified: first pitch class as root

            chord_vector = np.concatenate([
                np.eye(12)[root],
                chroma,
                np.eye(12)[bass]
            ])
        else:
            chord_vector = np.zeros(36)

        chord_matrix[m] = chord_vector

    return chord_matrix

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Convert MIDI to PolyDis data structures")
    parser.add_argument("--midi_path", type=str, default="./test_midis/2barmess.mid", help="Path to the MIDI file")
    parser.add_argument("--output_dir", type=str, default="./data/", help="Directory to save the output .npz")
    args = parser.parse_args()

    prmat = midi_to_prmat(args.midi_path)
    ptree = midi_to_pianotree(args.midi_path)
    chordvec = midi_to_chordvec(args.midi_path)

    output_path = os.path.join(args.output_dir, os.path.splitext(os.path.basename(args.midi_path))[0] + ".npz")
    np.savez(output_path, pr_mat=prmat, ptree=ptree, c=chordvec)

    print(f"Saved converted data to {output_path}")
