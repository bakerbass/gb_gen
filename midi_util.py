from mido import MidiFile, tempo2bpm

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