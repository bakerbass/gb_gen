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

def sort_files(input_directory):
    """
    Returns a list of MIDI filenames in the input directory,
    sorted by file size in ascending order.
    """
    midi_files = [
        filename for filename in os.listdir(input_directory)
        if filename.lower().endswith((".mid", ".midi"))
    ]
    return sorted(
        midi_files,
        key=lambda f: os.path.getsize(os.path.join(input_directory, f))
    )

def preprocess_file(filename, input_dir):
    """
    Processes a MIDI file to extract track names.
    """
    file_path = os.path.join(input_dir, filename)
    track_names = extract_track_names(file_path)
    return filename, track_names

def extract_track_names(midi_file_path):
    """
    Extracts track names from a MIDI file and annotates them with a classification label.
    """
    try:
        midi = MidiFile(midi_file_path)
    except Exception as e:
        print(f"Error reading {midi_file_path}: {e}")
        return []
    
    track_names = []
    for idx, track in enumerate(midi.tracks):
        base_name = None
        for msg in track:
            if msg.is_meta and msg.type == 'track_name':
                base_name = msg.name
                break
        if base_name is None:
            base_name = f"Track {idx + 1}"
        
        active_notes = 0
        max_active = 0
        note_found = False
        sum_notes = 0
        count_notes = 0
        
        for msg in track:
            if msg.type == "note_on":
                if msg.velocity > 0:
                    note_found = True
                    active_notes += 1
                    max_active = max(max_active, active_notes)
                    sum_notes += msg.note
                    count_notes += 1
                else:
                    if active_notes > 0:
                        active_notes -= 1
            elif msg.type == "note_off":
                if active_notes > 0:
                    active_notes -= 1
        
        if not note_found:
            continue
        
        avg_note = sum_notes / count_notes if count_notes > 0 else None
        
        if "solo" in base_name.lower():
            classification = "[melody]"
        elif avg_note is not None and avg_note < 50:
            classification = "[bass]"
        else:
            if max_active == 1:
                classification = "[melody]"
            elif max_active == 2:
                classification = "[duophonic]"
            elif max_active > 2:
                classification = "[chords]"
            else:
                classification = "[melody]"
        
        track_label = f"{base_name} {classification}"
        track_names.append(track_label)
    
    return track_names

def compute_absolute_times(msg_list):
    """
    Computes absolute times for all messages in a list, including meta events.
    If the messages are already (message, abs_time) tuples, they are returned as-is.
    Returns a list of tuples: (message, abs_time)
    """
    if msg_list and isinstance(msg_list[0], tuple):
        return msg_list

    abs_time = 0
    timed_msgs = []
    for msg in msg_list:
        msg_copy = msg.copy()
        abs_time += msg_copy.time
        timed_msgs.append((msg_copy, abs_time))
    return timed_msgs

def sort_and_delta_convert(timed_msgs):
    """
    Sorts (message, abs_time) tuples and converts them back to delta times.
    """
    sorted_msgs = sorted(timed_msgs, key=lambda t: t[1])
    if not sorted_msgs:
        return []
    
    first_msg, first_abs = sorted_msgs[0]
    first_msg.time = first_abs
    prev_abs = first_abs
    final_msgs = [first_msg]
    
    for msg, abs_time in sorted_msgs[1:]:
        msg.time = abs_time - prev_abs
        prev_abs = abs_time
        final_msgs.append(msg)
    
    return final_msgs

def messages_overlap(existing_msgs, new_msgs):
    """
    Checks if the new message block overlaps with existing messages.
    """
    if not existing_msgs:
        return False

    existing_abs = compute_absolute_times(existing_msgs)
    new_abs = compute_absolute_times(new_msgs)
    
    if not new_abs:
        return False

    last_existing = max(t[1] for t in existing_abs)
    new_start = new_abs[0][1]
    
    return new_start < last_existing

def merge_messages(existing_msgs, new_msgs):
    """
    Merges new messages into the existing ones by shifting new messages so they come after.
    """
    existing_abs = compute_absolute_times(existing_msgs)
    last_existing = max(t[1] for t in existing_abs)
    
    new_abs = compute_absolute_times(new_msgs)
    shift = last_existing - new_abs[0][1] + 1

    shifted_new = [(msg, abs_time + shift) for (msg, abs_time) in new_abs]
    
    return existing_abs + shifted_new


def combine_selected_tracks(selected_data, input_directory="./midi", output_file="combined_output.mid"):
    """
    Combines selected melody and chord tracks from multiple files into one MIDI file.
    This version uses candidate ordering (i.e. assumes melody candidates come first and chord candidates later)
    and ensures that any set_tempo messages are carried over into the output.
    
    Debug statements are added throughout.
    """
    ##print("[DEBUG] Starting combine_selected_tracks using candidate ordering without parsing labels")
    
    combined_midi = MidiFile()
    melody_track = MidiTrack()
    chord_track = MidiTrack()
    combined_midi.tracks.append(melody_track)
    combined_midi.tracks.append(chord_track)
    
    # Insert initial program changes.
    melody_track.append(Message('program_change', program=12, time=0))
    chord_track.append(Message('program_change', program=1, time=0))
    
    all_melody_messages = []
    all_chord_messages = []
    
    # Process each file in the selected_data dictionary.
    for fname, (melody_candidates, chord_candidates) in selected_data.items():
        #print(f"[DEBUG] Processing file: {fname}")
        #print(f"[DEBUG] Melody candidates: {melody_candidates}")
        #print(f"[DEBUG] Chord candidates: {chord_candidates}")
        file_path = os.path.join(input_directory, fname)
        midi = MidiFile(file_path)
        
        # Process melody candidates using ordering: assign indices 1, 2, … in order.
        for i, candidate in enumerate(melody_candidates):
            idx = i + 1  # 1-indexed
            #print(f"[DEBUG] Melody candidate '{candidate}' assigned index {idx}")
            if idx > len(midi.tracks):
                #print(f"[DEBUG] Melody candidate index {idx} out of range (file has {len(midi.tracks)} tracks). Skipping.")
                continue
            msgs = list(midi.tracks[idx - 1])
            #print(f"[DEBUG] Extracted {len(msgs)} messages from melody track index {idx}")
            if not msgs:
                #print("[DEBUG] No messages found for this melody candidate; skipping.")
                continue
            candidate_abs = compute_absolute_times(msgs)
            #print(f"[DEBUG] Computed {len(candidate_abs)} absolute messages for melody candidate '{candidate}'")
            if not all_melody_messages:
                all_melody_messages = candidate_abs
                #print("[DEBUG] Setting initial melody messages.")
            else:
                if messages_overlap(all_melody_messages, msgs):
                    #print("[DEBUG] Overlap detected; merging melody messages.")
                    all_melody_messages = merge_messages(all_melody_messages, msgs)
                else:
                    #print("[DEBUG] No overlap; extending melody messages.")
                    all_melody_messages.extend(compute_absolute_times(msgs))
            #print(f"[DEBUG] Total melody messages count: {len(all_melody_messages)}")
        
        # Process chord candidates using ordering:
        # Their assigned index starts after all melody candidates.
        for j, candidate in enumerate(chord_candidates):
            idx = len(melody_candidates) + j + 1
            #print(f"[DEBUG] Chord candidate '{candidate}' assigned index {idx}")
            if idx > len(midi.tracks):
                #print(f"[DEBUG] Chord candidate index {idx} out of range (file has {len(midi.tracks)} tracks). Skipping.")
                continue
            msgs = list(midi.tracks[idx - 1])
            #print(f"[DEBUG] Extracted {len(msgs)} messages from chord track index {idx}")
            if not msgs:
                #print("[DEBUG] No messages found for this chord candidate; skipping.")
                continue
            candidate_abs = compute_absolute_times(msgs)
            #print(f"[DEBUG] Computed {len(candidate_abs)} absolute messages for chord candidate '{candidate}'")
            if not all_chord_messages:
                all_chord_messages = candidate_abs
                #print("[DEBUG] Setting initial chord messages.")
            else:
                if messages_overlap(all_chord_messages, msgs):
                    #print("[DEBUG] Overlap detected; merging chord messages.")
                    all_chord_messages = merge_messages(all_chord_messages, msgs)
                else:
                    #print("[DEBUG] No overlap; extending chord messages.")
                    all_chord_messages.extend(compute_absolute_times(msgs))
            #print(f"[DEBUG] Total chord messages count: {len(all_chord_messages)}")
    
    # Ensure that set_tempo messages are carried over.
    tempo_found = any(msg.is_meta and msg.type == 'set_tempo' for msg, _ in all_melody_messages)
    if not tempo_found and selected_data:
        first_file = next(iter(selected_data))
        #print(f"[DEBUG] No tempo messages found. Extracting set_tempo messages from first file: {first_file}")
        midi_first = MidiFile(os.path.join(input_directory, first_file))
        tempo_msgs = []
        # Loop through all tracks and extract set_tempo meta messages.
        for track in midi_first.tracks:
            for msg in track:
                if msg.is_meta and msg.type == 'set_tempo':
                    # Copy the message with time zero.
                    tempo_msgs.append((msg.copy(time=0), 0))
        if tempo_msgs:
            #print(f"[DEBUG] Extracted {len(tempo_msgs)} tempo messages. Prepending to melody messages.")
            all_melody_messages = tempo_msgs + all_melody_messages
    
    # Convert absolute times back to delta times.
    sorted_melody = sort_and_delta_convert(all_melody_messages)
    sorted_chords = sort_and_delta_convert(all_chord_messages)
    #print(f"[DEBUG] After sorting: {len(sorted_melody)} melody messages, {len(sorted_chords)} chord messages")
    
    # Append the processed messages to their respective tracks.
    for msg in sorted_melody:
        melody_track.append(msg)
    for msg in sorted_chords:
        chord_track.append(msg)
    
    combined_midi.save(output_file)
    #print(f"[DEBUG] Combined MIDI saved as '{output_file}'")



def parse_track_index(track_label, midi_file=None):
    """
    Returns a 1-indexed track number based on the candidate track label.
    
    First, attempts to extract the first integer found in track_label using a regular expression.
    If no digit is found and a midi_file (a mido.MidiFile object) is provided,
    the function cleans the label (removing any bracketed annotations) and searches the midi_file's tracks:
      - It compares the cleaned candidate with any meta track names (converted to lowercase)
      - Returns the track index (1-indexed) if a match is found.
    
    If no index can be determined, returns None.
    
    :param track_label: The candidate track label (e.g., "Track 3 [melody]" or "Bass").
    :param midi_file: (Optional) a mido.MidiFile object used to search for a matching track.
    :return: An integer track index (1-indexed) or None if not found.
    """
    # Try to extract a number from the label.
    match = re.search(r'\d+', track_label)
    if match:
        return int(match.group(0))
    
    # If no number is found and a MidiFile is provided, try to match by name.
    if midi_file is not None:
        # Remove any annotations in brackets and extra whitespace.
        base_label = re.sub(r'\[.*?\]', '', track_label).strip().lower()
        # Loop over each track and check for a match in the track name.
        for idx, track in enumerate(midi_file.tracks, start=1):
            for msg in track:
                if msg.is_meta and msg.type == 'track_name':
                    track_name = msg.name.lower()
                    if base_label in track_name:
                        return idx
    return 0

def extract_track_messages(file_path, track_index):
    """
    Loads the MIDI file and returns all messages (including meta events)
    from the specified track (1-based index).
    """
    try:
        midi = MidiFile(file_path)
        if 0 <= track_index - 1 < len(midi.tracks):
            return list(midi.tracks[track_index - 1])
    except Exception as e:
        print(f"Error extracting messages from {file_path}: {e}")
    return []

def compute_melody_stats(file_path, track_index):
    """
    Computes melody statistics (average, median, total note count) for note_on events.
    """
    msgs = extract_track_messages(file_path, track_index)
    notes = [msg.note for msg in msgs if msg.type == "note_on" and msg.velocity > 0]
    total_notes = len(notes)
    if not notes:
        return {"average": 0, "median": 0, "total_notes": 0}
    average = sum(notes) / total_notes
    sorted_notes = sorted(notes)
    n = total_notes
    median = sorted_notes[n // 2] if n % 2 == 1 else (sorted_notes[n // 2 - 1] + sorted_notes[n // 2]) / 2
    return {"average": average, "median": median, "total_notes": total_notes}

def compute_chord_stats(file_path, track_index):
    """
    Computes chord statistics for a track: max/min active notes and polyphonic blocks.
    """
    msgs = extract_track_messages(file_path, track_index)
    active = 0
    active_counts = []
    polyphonic_blocks = 0
    poly_state = False
    for msg in msgs:
        if msg.type == "note_on":
            if msg.velocity > 0:
                active += 1
            else:
                active = max(0, active - 1)
        elif msg.type == "note_off":
            active = max(0, active - 1)
        active_counts.append(active)
        if not poly_state and active > 1:
            polyphonic_blocks += 1
            poly_state = True
        if poly_state and active <= 1:
            poly_state = False
    if active_counts:
        return {
            "max_active": max(active_counts),
            "min_active": min(active_counts),
            "polyphonic_blocks": polyphonic_blocks
        }
    else:
        return {"max_active": 0, "min_active": 0, "polyphonic_blocks": 0}

def auto_select_non_overlapping(file_path, candidate_labels):
    """
    Auto-selects candidate tracks if their message blocks do not overlap.
    """
    candidates = []
    for lab in candidate_labels:
        idx = parse_track_index(lab)
        if idx is not None:
            msgs = extract_track_messages(file_path, idx)
            abs_msgs = compute_absolute_times(msgs)
            candidates.append((lab, abs_msgs))
    if len(candidates) < 2:
        return candidate_labels

    for i in range(len(candidates)):
        for j in range(i+1, len(candidates)):
            _, msgs_a = candidates[i]
            _, msgs_b = candidates[j]
            if messages_overlap(msgs_a, msgs_b):
                return None
    return candidate_labels

def combine_single_file(file_path, melody_candidates, chord_candidates, output_file):
    """
    Combines selected melody and chord tracks from a single MIDI file into a new file.
    Debug statements have been added to trace processing steps.
    """
    from mido import MidiFile, MidiTrack, Message
    #print(f"[DEBUG] Starting combine_single_file on {file_path}")
    
    all_melody_msgs = []
    all_chord_msgs = []
    
    # Process melody candidates.
    for candidate in melody_candidates:
        idx = parse_track_index(candidate)
        #print(f"[DEBUG] Melody candidate '{candidate}' parsed to index: {idx}")
        if idx is not None:
            msgs = extract_track_messages(file_path, idx)
            #print(f"[DEBUG] Extracted {len(msgs)} messages from melody track index {idx}")
            if not msgs:
                #print("[DEBUG] No messages for this melody candidate; skipping.")
                continue
            abs_msgs = compute_absolute_times(msgs)
            #print(f"[DEBUG] Computed {len(abs_msgs)} absolute messages for melody candidate")
            if not all_melody_msgs:
                all_melody_msgs = abs_msgs
                #print("[DEBUG] Setting initial melody messages.")
            else:
                if messages_overlap(all_melody_msgs, msgs):
                    #print("[DEBUG] Overlap detected in melody messages; merging.")
                    all_melody_msgs = merge_messages(all_melody_msgs, msgs)
                else:
                    #print("[DEBUG] No overlap; extending melody messages.")
                    all_melody_msgs.extend(compute_absolute_times(msgs))
            #print(f"[DEBUG] Total melody messages count is now: {len(all_melody_msgs)}")
    
    # Process chord candidates.
    for candidate in chord_candidates:
        idx = parse_track_index(candidate)
        #print(f"[DEBUG] Chord candidate '{candidate}' parsed to index: {idx}")
        if idx is not None:
            msgs = extract_track_messages(file_path, idx)
            #print(f"[DEBUG] Extracted {len(msgs)} messages from chord track index {idx}")
            if not msgs:
                #print("[DEBUG] No messages for this chord candidate; skipping.")
                continue
            abs_msgs = compute_absolute_times(msgs)
            #print(f"[DEBUG] Computed {len(abs_msgs)} absolute messages for chord candidate")
            if not all_chord_msgs:
                all_chord_msgs = abs_msgs
                #print("[DEBUG] Setting initial chord messages.")
            else:
                if messages_overlap(all_chord_msgs, msgs):
                    #print("[DEBUG] Overlap detected in chord messages; merging.")
                    all_chord_msgs = merge_messages(all_chord_msgs, msgs)
                else:
                    #print("[DEBUG] No overlap; extending chord messages.")
                    all_chord_msgs.extend(compute_absolute_times(msgs))
            #print(f"[DEBUG] Total chord messages count is now: {len(all_chord_msgs)}")
    
    sorted_melody = sort_and_delta_convert(all_melody_msgs)
    sorted_chords  = sort_and_delta_convert(all_chord_msgs)
    #print(f"[DEBUG] After sorting, melody messages: {len(sorted_melody)}, chord messages: {len(sorted_chords)}")
    
    new_midi = MidiFile()
    melody_track = MidiTrack()
    chord_track = MidiTrack()
    new_midi.tracks.append(melody_track)
    new_midi.tracks.append(chord_track)
    
    melody_track.append(Message('program_change', program=12, time=0))
    chord_track.append(Message('program_change', program=1, time=0))
    
    for msg in sorted_melody:
        melody_track.append(msg)
    for msg in sorted_chords:
        chord_track.append(msg)
    
    new_midi.save(output_file)
    #print(f"[DEBUG] Saved combined MIDI as: {output_file}")

def organize_midi_files(midi_dir):
    """
    Organizes MIDI files into subdirectories named after each song.
    """
    midi_files = glob.glob(os.path.join(midi_dir, "*.mid"))
    if not midi_files:
        print("No MIDI files found in", midi_dir)
        return

    for midi_file in midi_files:
        basename = os.path.basename(midi_file)
        name, _ = os.path.splitext(basename)
        safe_name = name.rstrip(" .")
        song_folder = os.path.join(midi_dir, safe_name)
        os.makedirs(song_folder, exist_ok=True)
        target_path = os.path.join(song_folder, basename)
        print(f"Moving '{midi_file}' to '{target_path}'")
        shutil.move(midi_file, target_path)

def prepare_json_annotations(input_dir="./midi", output_dir="./json_data"):
    """
    Processes all MIDI files in the input directory and saves JSON annotations.
    """
    sorted_files = sort_files(input_dir)
    annotations = {}
    print("Starting track extraction with parallel processing...")
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = [executor.submit(preprocess_file, filename, input_dir) for filename in sorted_files]
        for future in concurrent.futures.as_completed(futures):
            try:
                filename, track_names = future.result()
                annotations[filename] = track_names
            except Exception as e:
                print(f"Error processing a file: {e}")
    print("Track extraction done.")
    annotations_file = "track_annotations.json"
    with open(annotations_file, "w") as f:
        json.dump(annotations, f, indent=2)
    print(f"Saved track annotations to {annotations_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test midi_utils functions on a single MIDI file."
    )
    parser.add_argument("midi_file", help="Path to a single MIDI file")
    args = parser.parse_args()

    if not os.path.exists(args.midi_file):
        print(f"Error: The file {args.midi_file} does not exist.")
        sys.exit(1)

    print(f"Testing on MIDI file: {args.midi_file}\n")

    # Test 1: Extract and print track names.
    track_names = extract_track_names(args.midi_file)
    print("Extracted Track Names:")
    for idx, name in enumerate(track_names, start=1):
        print(f"  {idx}: {name}")

    # Test 2: Process the MIDI file for chords/strum/pluck lists.
    # result = process_midi_file(args.midi_file)
    # if result:
    #     print("Processed MIDI file output (chords, strum, pluck):")
    #     print(result)
    # else:
    #     print("Error processing MIDI file for chord/strum/pluck data.")
    # print()

    # Test 3: Demonstrate computing absolute times for the first track.
    # (Assuming the MIDI file has at least one track.)
    track_msgs = extract_track_messages(args.midi_file, 2)
    if track_msgs:
        abs_msgs = compute_absolute_times(track_msgs)
        delta_msgs = sort_and_delta_convert(abs_msgs)
        print("First track messages after computing absolute times and converting back to delta times:")
        for msg in delta_msgs:
            print(msg)
    else:
        print("No messages found for the first track.")
    if not track_names:
        print("No tracks available to test combination.")
    else:
        if len(track_names) >= 2:
            melody_candidates = [track_names[0]]
            chord_candidates = [track_names[1]]
        else:
            melody_candidates = [track_names[0]]
            chord_candidates = []
        output_file = "combined_test_output.mid"
        print("Testing track combination...")
        combine_single_file(args.midi_file, melody_candidates, chord_candidates, output_file)
        if os.path.exists(output_file):
            print(f"Combined MIDI file successfully saved as '{output_file}'.")
        else:
            print("Error: Combined MIDI file was not created.")

