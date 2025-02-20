import os
import json
from chords import MIDI_Stream
from midi_utils import validate_midi_file

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

def process_directory(input_directory, output_directory="json_data"):
    """
    Iterates over all MIDI files in the input directory, processes them,
    and saves each result to its own JSON file (processing files from smallest
    to biggest file size).
    """
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Get list of MIDI filenames
    midi_files = [
        filename for filename in os.listdir(input_directory)
        if filename.lower().endswith((".mid", ".midi"))
    ]
    
    # Sort the files by file size (ascending)
    midi_files_sorted = sorted(
        midi_files,
        key=lambda f: os.path.getsize(os.path.join(input_directory, f))
    )
    
    for filename in midi_files_sorted:
        file_path = os.path.join(input_directory, filename)
        if validate_midi_file(file_path):
            print(f"Processing {file_path}")
            data = process_midi_file(file_path)
        else:
            print(f"Skipping invalid MIDI file: {file_path}")
            data = None
        if data is not None:
            base_name = os.path.splitext(filename)[0]
            output_file = os.path.join(output_directory, f"{base_name}.json")
            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved processed data to {output_file}")

if __name__ == "__main__":
    # Modify these paths as needed.
    input_dir = "./midi"
    output_dir = "./json_data"
    process_directory(input_dir, output_dir)