import os
import json
import glob
import shutil
import concurrent.futures
from mido import MidiFile, MidiTrack, Message
from chords import MIDI_Stream
from midi_utils import validate_midi_file

# ----------------- Existing Function Definitions -----------------

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
    midi_files_sorted = sorted(
        midi_files,
        key=lambda f: os.path.getsize(os.path.join(input_directory, f))
    )
    return midi_files_sorted

def process_file(filename, input_dir):
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
    If the messages are already in (message, abs_time) tuple format, they are returned as-is.
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
    Checks if new message block overlaps with existing messages.
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
    Merges new messages into existing ones by shifting new messages so that they come after.
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
    """
    combined_midi = MidiFile()
    melody_track = MidiTrack()
    chord_track = MidiTrack()
    combined_midi.tracks.append(melody_track)
    combined_midi.tracks.append(chord_track)

    melody_track.append(Message('program_change', program=12, time=0))
    chord_track.append(Message('program_change', program=1, time=0))

    print("\nCombining the following selections:")

    all_melody_messages = []
    all_chord_messages = []

    for fname, (melody_sel, chord_sel) in selected_data.items():
        print(f"  {fname} -> Melody: {melody_sel}, Chords: {chord_sel}")
        file_path = os.path.join(input_directory, fname)

        for candidate in melody_sel:
            idx = parse_track_index(candidate)
            if idx is not None:
                msgs = extract_track_messages(file_path, idx)
                if not msgs:
                    continue
                candidate_abs = compute_absolute_times(msgs)
                if not all_melody_messages:
                    all_melody_messages = candidate_abs
                else:
                    if messages_overlap(all_melody_messages, msgs):
                        all_melody_messages = merge_messages(all_melody_messages, msgs)
                    else:
                        all_melody_messages.extend(compute_absolute_times(msgs))

        for candidate in chord_sel:
            idx = parse_track_index(candidate)
            if idx is not None:
                msgs = extract_track_messages(file_path, idx)
                if not msgs:
                    continue
                candidate_abs = compute_absolute_times(msgs)
                if not all_chord_messages:
                    all_chord_messages = candidate_abs
                else:
                    if messages_overlap(all_chord_messages, msgs):
                        all_chord_messages = merge_messages(all_chord_messages, msgs)
                    else:
                        all_chord_messages.extend(compute_absolute_times(msgs))

    sorted_melody = sort_and_delta_convert(all_melody_messages)
    sorted_chords = sort_and_delta_convert(all_chord_messages)

    for msg in sorted_melody:
        melody_track.append(msg)
    for msg in sorted_chords:
        chord_track.append(msg)

    combined_midi.save(output_file)
    print(f"Combined MIDI saved as '{output_file}'")

def parse_track_index(track_label):
    """
    Parses a track label and returns the integer index.
    """
    try:
        if track_label.lower().startswith("track"):
            parts = track_label.split()
            return int(parts[1])
    except Exception:
        return None
    return None

def extract_track_messages(file_path, track_index):
    """
    Loads the MIDI file and returns all messages (including meta events) from the specified track.
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
    Extracts note information from note_on events and computes average, median, and total note count.
    """
    msgs = extract_track_messages(file_path, track_index)
    notes = [msg.note for msg in msgs if msg.type == "note_on" and msg.velocity > 0]
    total_notes = len(notes)
    if not notes:
        return {"average": 0, "median": 0, "total_notes": 0}
    average = sum(notes) / total_notes
    sorted_notes = sorted(notes)
    n = total_notes
    if n % 2 == 1:
        median = sorted_notes[n // 2]
    else:
        median = (sorted_notes[n // 2 - 1] + sorted_notes[n // 2]) / 2
    return {"average": average, "median": median, "total_notes": total_notes}

def compute_chord_stats(file_path, track_index):
    """
    Computes chord stats (max, min active notes and polyphonic blocks) for a track.
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
    Combines selected melody and chord tracks from a single MIDI file into a new MIDI file.
    """
    all_melody_msgs = []
    all_chord_msgs = []
    
    for candidate in melody_candidates:
        idx = parse_track_index(candidate)
        if idx is not None:
            msgs = extract_track_messages(file_path, idx)
            if not msgs:
                continue
            abs_msgs = compute_absolute_times(msgs)
            if not all_melody_msgs:
                all_melody_msgs = abs_msgs
            else:
                if messages_overlap(all_melody_msgs, msgs):
                    all_melody_msgs = merge_messages(all_melody_msgs, msgs)
                else:
                    all_melody_msgs.extend(compute_absolute_times(msgs))
    
    for candidate in chord_candidates:
        idx = parse_track_index(candidate)
        if idx is not None:
            msgs = extract_track_messages(file_path, idx)
            if not msgs:
                continue
            abs_msgs = compute_absolute_times(msgs)
            if not all_chord_msgs:
                all_chord_msgs = abs_msgs
            else:
                if messages_overlap(all_chord_msgs, msgs):
                    all_chord_msgs = merge_messages(all_chord_msgs, msgs)
                else:
                    all_chord_msgs.extend(compute_absolute_times(msgs))
    
    sorted_melody = sort_and_delta_convert(all_melody_msgs)
    sorted_chords  = sort_and_delta_convert(all_chord_msgs)
    
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
    print(f"Saved processed MIDI as: {output_file}")

def prompt_user_for_selection(filename, track_list):
    """
    Prompts the user for selecting melody and chord tracks from a given list.
    """
    file_path = os.path.join("./midi", filename)
    
    # Partition melody and chord tracks.
    melody_tracks = [track for track in track_list 
                     if (("[melody]" in track.lower() or "[duophonic]" in track.lower())
                         and not any(kw in track.lower() for kw in ["percussion", "drums"]))]
    converted_tracks = [track for track in track_list 
                        if (("[melody]" in track.lower() or "[duophonic]" in track.lower())
                            and any(kw in track.lower() for kw in ["percussion", "drums"]))]
    chord_tracks = [track for track in track_list if "[chords]" in track.lower()]
    chord_tracks.extend(converted_tracks)
    
    print("\nFile:", filename)
    print("Melody Tracks:")
    for i, track in enumerate(melody_tracks):
        idx = parse_track_index(track)
        if idx is not None:
            stats = compute_melody_stats(file_path, idx)
            print(f"  {i+1}: {track} (Avg: {stats['average']:.2f}, Median: {stats['median']}, Total Notes: {stats['total_notes']})")
        else:
            print(f"  {i+1}: {track}")
    print("Chord Tracks:")
    for i, track in enumerate(chord_tracks):
        idx = parse_track_index(track)
        if idx is not None:
            stats = compute_chord_stats(file_path, idx)
            print(f"  {i+1}: {track} (Max: {stats['max_active']}, Min: {stats['min_active']}, Poly Blocks: {stats['polyphonic_blocks']})")
        else:
            print(f"  {i+1}: {track}")
    
    if len(melody_tracks) == 1:
        selected_melody = melody_tracks
        print("Automatically selecting the only eligible melody track.")
    else:
        selection = input("Enter comma-separated indices for melody tracks to keep ('all' to keep all, 'discard' to remove): ").strip()
        if selection.lower() == "all":
            selected_melody = melody_tracks
        elif selection.lower() == "discard":
            selected_melody = []
            print("Melody tracks discarded by user.")
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_melody = [melody_tracks[i] for i in indices if 0 <= i < len(melody_tracks)]
            except Exception as e:
                print("Invalid input. No melody tracks selected.")
                selected_melody = []
    
    discarded_melody = [track for track in melody_tracks if track not in selected_melody]
    
    if len(chord_tracks) == 1:
        selected_chords = chord_tracks
        print("Automatically selecting the only chords track.")
    else:
        selection = input("Enter comma-separated indices for chord tracks to keep ('all' to keep all, 'discard' to remove): ").strip()
        if selection.lower() == "all":
            selected_chords = chord_tracks
        elif selection.lower() == "discard":
            selected_chords = []
            print("Chord tracks discarded.")
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_chords = [chord_tracks[i] for i in indices if 0 <= i < len(chord_tracks)]
            except Exception as e:
                print("Invalid input. No chord tracks selected.")
                selected_chords = []
    
    selected_chords.extend(discarded_melody)
    
    return selected_melody, selected_chords

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

# ----------------- Main Processing Functions -----------------

def prepare_json_annotations(input_dir="./midi", output_dir="./json_data"):
    """
    Processes all MIDI files in the input directory and saves JSON annotations.
    """
    sorted_files = sort_files(input_dir)
    annotations = {}
    print("Starting track extraction with parallel processing...")
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_file, filename, input_dir) for filename in sorted_files]
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

def process_user_selections():
    """
    Loads the track annotations and processes user selections (or auto-selects).
    """
    with open("track_annotations.json", "r") as f:
        annotations = json.load(f)
    
    filtered_annotations = {
        filename: tracks
        for filename, tracks in annotations.items()
        if (any(("[melody]" in track.lower() or "[duophonic]" in track.lower()) for track in tracks) and
            any("[chords]" in track.lower() for track in tracks))
    }
    
    user_selections = {}
    print("\nProcessing files for auto-selection or prompting...")
    for filename, tracks in filtered_annotations.items():
        file_path = os.path.join("./midi", filename)
        melody_candidates = [track for track in tracks if "[melody]" in track.lower() or "[duophonic]" in track.lower()]
        chord_candidates  = [track for track in tracks if "[chords]" in track.lower()]
        
        auto_melody = auto_select_non_overlapping(file_path, melody_candidates)
        auto_chords  = auto_select_non_overlapping(file_path, chord_candidates)
        
        if auto_melody is not None and auto_chords is not None:
            user_selections[filename] = (auto_melody, auto_chords)
            print(f"\nFile {filename} auto-selected with melody: {auto_melody} and chords: {auto_chords}")
        else:
            selected_melody, selected_chords = prompt_user_for_selection(filename, tracks)
            user_selections[filename] = (selected_melody, selected_chords)
    
    with open("user_selections.json", "w") as f:
        json.dump(user_selections, f, indent=2)
    print("\nUser selections saved to 'user_selections.json'")

def combine_user_selected_files():
    """
    Loads user selections and combines the corresponding MIDI files.
    """
    with open("user_selections.json", "r") as f:
        user_selections = json.load(f)
    
    processed_dir = "./processed_midi"
    if not os.path.exists(processed_dir):
        os.makedirs(processed_dir)
    
    for filename, (melody_list, chord_list) in user_selections.items():
        file_path = os.path.join("./midi", filename)
        output_file = os.path.join(processed_dir, filename)
        print(f"Processing file: {filename} ...")
        combine_single_file(file_path, melody_list, chord_list, output_file)

# ----------------- Main Entry Point -----------------

def main():
    """
    Main entry point for processing MIDI files.
    Steps:
      1. Prepare JSON annotations.
      2. Process user selections.
      3. Combine selected tracks into new MIDI files.
      4. Organize the processed MIDI files into folders.
    """
    #prepare_json_annotations(input_dir="./midi", output_dir="./json_data")
    # process_user_selections()
    combine_user_selected_files()
    organize_midi_files("./processed_midi")

if __name__ == "__main__":
    main()
