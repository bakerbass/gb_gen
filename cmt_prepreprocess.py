# midi_ui.py
import os
import json
from midi_utils import (
    prepare_json_annotations,
    sort_files,
    parse_track_index,
    extract_track_messages,
    compute_melody_stats,
    compute_chord_stats,
    auto_select_non_overlapping,
    combine_single_file,
    organize_midi_files
)

def prompt_user_for_selection(filename, track_list):
    """
    Given a file's annotated track list, partition them into melody and chord groups,
    prompt the user for selection, and return the selected tracks.
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

def process_user_selections():
    """
    Loads the track annotations and processes user selections (auto-select or via prompt).
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

def main():
    """
    Main interactive entry point.
    Steps:
      1. Prepare JSON annotations.
      2. Process user selections.
      3. Combine selected tracks.
    """
    # prepare_json_annotations(input_dir="./midi", output_dir="./json_data")
    # process_user_selections()
    combine_user_selected_files()
    organize_midi_files("./processed_midi")

if __name__ == "__main__":
    main()
