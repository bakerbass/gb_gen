from music21 import stream, note, midi
import random

def rule_based_melody(full_chords, bpm=120, debug=False):
    number_of_chords = len(full_chords)
    melody = stream.Stream()
    pluck_message = []  # Stores lists: [midi value, duration (seconds), speed, timestamp]
    time_cursor = 0     # Running timestamp in seconds
    default_speed = 7   # Change as needed
    quarter_note_duration = 60 / bpm

    prev_n = None         # Keep track of the last note (if any)
    prev_pluck_idx = None # Index of the last pluck entry in pluck_message

    for chord in full_chords:
        # If chord is unknown, extend the previous note instead of inserting a rest.
        if chord[0] == "Chord Symbol Cannot Be Identified":
            if prev_n is not None:
                # Extend previous note's duration by one quarter note.
                extend_amt = quarter_note_duration  # duration in seconds
                prev_n.quarterLength += 1
                # Also update the pluck message's duration.
                pluck_message[prev_pluck_idx][1] += extend_amt
                if debug:
                    print("Extended previous note to duration", prev_n.quarterLength)
            else:
                if debug:
                    print("Unknown chord with no previous note; skipping extension.")
            time_cursor += quarter_note_duration
            continue

        # Get random pitch from the chord.
        m21chord = chord[-1].pitches
        random_index = random.randint(0, len(m21chord) - 1)
        random_mel_pitch = m21chord[random_index]
        n = note.Note(random_mel_pitch, type="quarter")

        # Adjust note so that its MIDI value is within [40, 68]
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

        # If previous note exists and has the same MIDI value then merge (extend) it.
        if prev_n is not None and n.pitch.midi == prev_n.pitch.midi:
            if debug:
                print("Merging note", n.pitch, "with previous note.")
            # Increase previous note's duration by current note's quarter length (1 quarter note)
            prev_n.quarterLength += n.quarterLength
            # Update the corresponding pluck message duration.
            pluck_message[prev_pluck_idx][1] += n.quarterLength * quarter_note_duration
        else:
            # Otherwise, add the note to the stream and record its pluck message.
            melody.append(n)
            pluck_message.append([
                n.pitch.midi,              # MIDI value
                n.quarterLength * quarter_note_duration,  # duration in seconds
                default_speed,             # speed value
                time_cursor                # timestamp (seconds)
            ])
            prev_n = n
            prev_pluck_idx = len(pluck_message) - 1

        # Increase the time cursor by the duration of the note (in seconds)
        time_cursor += n.quarterLength * quarter_note_duration

    file_path = "rule_based_melody.mid"
    melody.write("midi", file_path)
    return pluck_message, file_path