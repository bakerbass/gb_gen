from mido import MidiFile, tempo2bpm, MidiTrack, Message
from itertools import groupby
# midi_processing.py
import os
import json
import glob
import shutil
import concurrent.futures
from chords import MIDI_Stream
import argparse
import sys
import re 

def validate_midi_file(file_path):
    """
    Validates a MIDI file.

    :param file_path: Path to the MIDI file to validate.
    :return: True if the file is valid, False otherwise.
    """
    try:
        # Attempt to parse the MIDI file
        midi = MidiFile(file_path)
        print(f"Valid MIDI file: {file_path}")
        return True
    except Exception as e:
        print(f"Invalid MIDI file: {file_path}. Error: {e}")
        return False

def detect_bpm(midi_file_path):
    midi = MidiFile(midi_file_path)
    for track in midi.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo = msg.tempo
                bpm = tempo2bpm(tempo)
                return bpm
    return None

# need to consolidate the two functions below into one
def get_tempo(mid):
    """
    Returns the first encountered tempo (in microseconds per beat) from the MIDI file.
    If no tempo is found, returns the default MIDI tempo of 500000 µs per beat.
    """
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                return msg.tempo
    return 500000  # default tempo (120 BPM)

# def extract_melody(midi_file_path, output_file_path):
#     """
#     Extracts the melody (highest note) from a polyphonic MIDI file.

#     :param midi_file_path: Path to the input MIDI file.
#     :param output_file_path: Path to the output MIDI file containing only the melody.
#     """
#     midi = MidiFile(midi_file_path)
#     output_midi = MidiFile()
#     output_track = MidiTrack()
#     output_midi.tracks.append(output_track)

#     current_notes = []

#     for msg in midi.play():
#         if msg.type == 'note_on' and msg.velocity > 0:
#             current_notes.append(msg)
#             highest_note = max(current_notes, key=lambda x: x.note)
#             output_track.append(highest_note)
#         elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
#             current_notes = [note for note in current_notes if note.note != msg.note]
#             if current_notes:
#                 highest_note = max(current_notes, key=lambda x: x.note)
#                 output_track.append(highest_note)
    
#     print(current_notes)

#     output_midi.save(output_file_path)

def get_total_bars(midi_file_path):
    """
    Returns the total number of bars in a MIDI file.

    :param midi_file_path: Path to the MIDI file.
    :return: Total number of bars.
    """
    midi = MidiFile(midi_file_path)
    bpm = detect_bpm(midi_file_path)
    if bpm is None:
        bpm = 120  # Default BPM

    ticks_per_beat = midi.ticks_per_beat
    beats_per_bar = 4  # Assuming 4/4 time signature
    total_ticks = sum(msg.time for track in midi.tracks for msg in track)
    total_beats = total_ticks / ticks_per_beat
    total_bars = total_beats / beats_per_bar

    return int(total_bars)

def extract_melody(input_path, output_path='melody.mid', chord_window_sec=None):
    """
    Extracts the melody (the highest active note at each moment) from the input MIDI file.
    Optionally, if chord_window_sec (in seconds) is provided, any note whose note_on occurs
    within the first chord_window_sec seconds is preserved in full (i.e. its note_on and matching
    note_off events are also included). After that window, only the melody is kept.
    """
    mid = MidiFile(input_path)
    ticks_per_beat = mid.ticks_per_beat
    tempo = get_tempo(mid)
    
    # Convert chord window (seconds) to ticks (if provided)
    if chord_window_sec is not None:
        chord_window_ticks = round(chord_window_sec * ticks_per_beat * 1e6 / tempo)
        print(f"Chord window: preserving all notes that start within {chord_window_sec:.3f} sec "
              f"({chord_window_ticks} ticks)")
    else:
        chord_window_ticks = None

    # ------------------------------
    # 1. Extract the melody events.
    # ------------------------------
    # Gather all note events with their absolute times from all tracks.
    melody_events = []
    events = []
    for track in mid.tracks:
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if msg.type in ['note_on', 'note_off']:
                events.append((abs_time, msg))
                
    # Define a sorting key: when events share the same time, process note_off before note_on.
    def sort_key(item):
        t, msg = item
        order = 0 if (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)) else 1
        return (t, order)
    events.sort(key=sort_key)

    # Group events by absolute time.
    grouped = []
    for t, group in groupby(events, key=lambda x: x[0]):
        grouped.append((t, list(group)))

    active_notes = {}   # Map note -> velocity
    current_melody = None
    last_time = 0
    for t, group in grouped:
        # Update active notes based on events at time t.
        for _, msg in group:
            if msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                active_notes.pop(msg.note, None)
            else:
                active_notes[msg.note] = msg.velocity
        # Determine the highest active note.
        new_highest = max(active_notes.keys()) if active_notes else None
        if new_highest != current_melody:
            if current_melody is not None:
                melody_events.append((t, Message('note_off', note=current_melody, velocity=64)))
            if new_highest is not None:
                velocity = active_notes.get(new_highest, 64)
                melody_events.append((t, Message('note_on', note=new_highest, velocity=velocity)))
            current_melody = new_highest
        last_time = t
    # Turn off the last melody note if still active.
    if current_melody is not None:
        melody_events.append((last_time, Message('note_off', note=current_melody, velocity=64)))

    # ---------------------------------------------------
    # 2. Optionally, preserve full polyphony in a window.
    # ---------------------------------------------------
    additional_events = []
    if chord_window_ticks is not None:
        # For each track, add the full note (note_on and its matching note_off)
        # if the note_on occurs within the chord window.
        for track in mid.tracks:
            abs_time = 0
            active_notes_chords = {}  # Map note -> (start_time, note_on message)
            for msg in track:
                abs_time += msg.time
                if msg.type == 'note_on' and msg.velocity > 0:
                    # Record note_on events that begin in the chord window.
                    active_notes_chords.setdefault(msg.note, []).append((abs_time, msg))
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in active_notes_chords and active_notes_chords[msg.note]:
                        start_time, note_on_msg = active_notes_chords[msg.note].pop(0)
                        # Only include the note if it started within the chord window.
                        if start_time < chord_window_ticks:
                            print("Adding polyphonic info at: " + str(start_time) + ", " + str(abs_time))
                            additional_events.append((start_time, note_on_msg))
                            additional_events.append((abs_time, msg))
    # ---------------------------------------------------
    # 3. Merge events, recalc delta times, and save output.
    # ---------------------------------------------------
    combined_events = melody_events + additional_events
    combined_events.sort(key=sort_key)

    new_track = MidiTrack()
    prev_time = 0
    for t, msg in combined_events:
        delta = t - prev_time
        new_track.append(msg.copy(time=delta))
        prev_time = t

    new_mid = MidiFile()
    new_mid.tracks.append(new_track)
    new_mid.save(output_path)
    print(f"Saved extracted MIDI to {output_path}")
    return(output_path)

def quantize_midi(midi_file_path, output_file_path, subdivision=1/8):
    """
    Hard-quantizes MIDI note on and off events to the nearest subdivision grid.

    :param midi_file_path: Path to the input MIDI file.
    :param output_file_path: Path to the output MIDI file.
    :param subdivision: The subdivision to quantize to (default is 1/8 note).
    """
    midi = MidiFile(midi_file_path)
    quantized_midi = MidiFile()
    
    ticks_per_beat = midi.ticks_per_beat
    quantize_ticks = int(ticks_per_beat * subdivision)

    for track in midi.tracks:
        new_track = MidiTrack()
        abs_time = 0
        prev_quant = 0

        for msg in track:
            abs_time += msg.time

            if msg.type in ['note_on', 'note_off']:
                # Snap the absolute time to the nearest grid tick
                quant_time = round(abs_time / quantize_ticks) * quantize_ticks
            else:
                quant_time = abs_time

            # Calculate delta from previous quantized time
            delta = quant_time - prev_quant
            prev_quant = quant_time

            new_track.append(msg.copy(time=delta))
        quantized_midi.tracks.append(new_track)

    quantized_midi.save(output_file_path)
    print(f"Saved hard quantized MIDI to {output_file_path}")

def process_midi_file(file_path):
    """
    Processes a MIDI file and returns its chords, strum, and pluck lists.
    """
    try:
        midi_stream = MIDI_Stream(file_path)
        chords, strum, pluck = midi_stream.get_UDP_lists()
        chords_list = [list(item) for item in chords]
        strum_list = [list(item) for item in strum]
        pluck_list = [list(item) for item in pluck]
        return {
            "chords": chords_list,
            "strum": strum_list,
            "pluck": pluck_list
        }
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def save_midi_file(mido_obj, file_path):
    """
    Saves a MIDI file to disk.
    """
    mido_obj.save(file_path)
    print(f"Saved MIDI file to {file_path}")