from music21 import stream, note, midi
import random
def rule_based_melody(full_chords, bpm=120, debug=False):
    number_of_chords = len(full_chords)
    melody = stream.Stream()
    pluck_message = []  # This will store lists of [midi value, duration, speed, timestamp]
    time_cursor = 0     # Running timestamp (in quarter-length units)
    default_speed = 7 # Change as needed
    quarter_note_duration = 60 / bpm
    for chord in full_chords:
        if chord[0] == "Chord Symbol Cannot Be Identified":
            r = note.Rest(type="quarter")
            melody.append(r)
            time_cursor += r.quarterLength
            continue
        m21chord = chord[-1].pitches
        random_index = random.randint(0, len(m21chord) - 1)
        random_mel_pitch = m21chord[random_index]
        n = note.Note(random_mel_pitch, type="quarter")
        if n.pitch.midi < 40:
            if debug:
                print("Note", n.pitch, "is below 40, adjusting upward...")
            while n.pitch.midi < 40:
                n.pitch.octave += 1
            if debug:
                print("Adjusted to", n.pitch)
        elif n.pitch.midi > 68:
            if debug:
                print("Note", n.pitch, "is above 68, adjusting downward...")
            while n.pitch.midi > 68:
                n.pitch.octave -= 1
            if debug:
                print("Adjusted to", n.pitch)
        melody.append(n)
        # Append pluck message with note's midi, duration, default speed, and timestamp.
        pluck_message.append([n.pitch.midi, n.quarterLength * quarter_note_duration, default_speed, time_cursor])
        time_cursor += n.quarterLength * quarter_note_duration

    file_path = "rule_based_melody.mid"
    melody.write("midi", file_path)
    return pluck_message, file_path,