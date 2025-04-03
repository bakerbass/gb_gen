import pretty_midi as pm
import numpy as np
import os

def quantize_time(time, grid=0.25):
    return round(time / grid) * grid

def safe_load_midi(path):
    try:
        return pm.PrettyMIDI(path)
    except Exception as e:
        print(f"Could not load {path}: {e}")
        return None

def get_num_steps(midi, grid=0.25):
    if not midi.instruments or not midi.instruments[0].notes:
        return 0
    max_time = max(note.end for note in midi.instruments[0].notes)
    return int(np.ceil(max_time / grid))

def merge_instruments_to_single_track(midi_path, midi_path2=None):
    midi = safe_load_midi(midi_path)
    if midi is None:
        return None

    if midi_path2 is not None:
        midi2 = safe_load_midi(midi_path2)
        if midi2 is None:
            return None
        for instrument in midi2.instruments:
            if instrument.is_drum:
                # print(f"Skipping drum track: {instrument.name}")
                continue
            midi.instruments.append(instrument)

    merged_instrument = pm.Instrument(program=0, is_drum=False, name="MergedTrack")
    for instrument in midi.instruments:
        if instrument.is_drum:
            # print(f"Skipping drum track: {instrument.name}")
            continue
        merged_instrument.notes.extend(instrument.notes)

    merged_instrument.notes.sort(key=lambda n: n.start)
    merged_midi = pm.PrettyMIDI()
    merged_midi.instruments.append(merged_instrument)
    return merged_midi

def midi_to_prmat(midi_path):
    midi = safe_load_midi(midi_path)
    if midi is None:
        return None

    grid = 0.25
    num_steps = get_num_steps(midi, grid)
    pr_mat = np.zeros((num_steps, 128))

    for note in midi.instruments[0].notes:
        idx = int(quantize_time(note.start, grid) / grid)
        if 0 <= idx < num_steps:
            pr_mat[idx, note.pitch] = note.end - note.start

    return pr_mat

def midi_to_pianotree(midi_path):
    midi = safe_load_midi(midi_path)
    if midi is None:
        return None

    grid = 0.25
    num_steps = get_num_steps(midi, grid)
    ptree = [[] for _ in range(num_steps)]

    for note in midi.instruments[0].notes:
        idx = int(quantize_time(note.start, grid) / grid)
        if 0 <= idx < num_steps:
            pitch = note.pitch
            dur = note.end - note.start
            dur_steps = max(1, min(int(dur / grid), 31))
            dur_binary = [int(x) for x in bin(dur_steps)[2:].zfill(5)]
            vector = [pitch] + dur_binary
            if len(vector) == 6:
                ptree[idx].append(vector)

    fixed_ptree = []
    for frame in ptree:
        padded = frame[:16] + [[0] * 6] * (16 - len(frame))
        fixed_ptree.append(padded)

    return np.array(fixed_ptree)

def midi_to_chordvec(midi_path):
    midi = safe_load_midi(midi_path)
    if midi is None:
        return None

    grid = 0.25
    num_steps = get_num_steps(midi, grid)
    num_measures = int(np.ceil(num_steps / 16))
    chord_matrix = np.zeros((num_measures, 36))

    for m in range(num_measures):
        start = m * 16 * grid
        end = (m + 1) * 16 * grid
        pitches = [note.pitch for note in midi.instruments[0].notes if note.start < end and note.end > start]

        if pitches:
            pitch_classes = [p % 12 for p in pitches]
            chroma = np.zeros(12)
            for pc in pitch_classes:
                chroma[pc] = 1
            bass = min(pitches) % 12
            root = pitch_classes[0]

            chord_vector = np.concatenate([
                np.eye(12)[root],
                chroma,
                np.eye(12)[bass]
            ])
        else:
            chord_vector = np.zeros(36)

        chord_matrix[m] = chord_vector

    return chord_matrix