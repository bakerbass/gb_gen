from mido import MidiFile, tempo2bpm, MidiTrack, Message

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
def extract_melody(midi_file_path, output_file_path):
    """
    Extracts the melody (highest note) from a polyphonic MIDI file.

    :param midi_file_path: Path to the input MIDI file.
    :param output_file_path: Path to the output MIDI file containing only the melody.
    """
    midi = MidiFile(midi_file_path)
    output_midi = MidiFile()
    output_track = MidiTrack()
    output_midi.tracks.append(output_track)

    current_notes = []

    for msg in midi.play():
        if msg.type == 'note_on' and msg.velocity > 0:
            current_notes.append(msg)
            highest_note = max(current_notes, key=lambda x: x.note)
            output_track.append(highest_note)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            current_notes = [note for note in current_notes if note.note != msg.note]
            if current_notes:
                highest_note = max(current_notes, key=lambda x: x.note)
                output_track.append(highest_note)
    
    print(current_notes)

    output_midi.save(output_file_path)

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

def strip_melody(midi_file_path, output_file_path):
    """
    Strips the melody from the entire MIDI file except the first second.

    :param midi_file_path: Path to the input MIDI file.
    :param output_file_path: Path to the output MIDI file.
    """
    midi = MidiFile(midi_file_path)
    output_midi = MidiFile()
    output_track = MidiTrack()
    output_midi.tracks.append(output_track)

    current_notes = []
    time_elapsed = 0
    first_second_passed = False

    for msg in midi.play():
        time_elapsed += msg.time
        if time_elapsed > midi.ticks_per_beat:  # Assuming 1 second has passed
            first_second_passed = True

        if first_second_passed:
            if msg.type == 'note_on' and msg.velocity > 0:
                current_notes.append(msg)
                highest_note = max(current_notes, key=lambda x: x.note)
                output_track.append(highest_note)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                current_notes = [note for note in current_notes if note.note != msg.note]
                if current_notes:
                    highest_note = max(current_notes, key=lambda x: x.note)
                    output_track.append(highest_note)
        else:
            output_track.append(msg)

    output_midi.save(output_file_path)