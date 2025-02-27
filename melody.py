from music21 import stream, note, midi
import random
def rule_based_melody(full_chords):
    number_of_chords = len(full_chords)
    # print("Number of chords: ", number_of_chords)
    melody = stream.Stream()
    for chord in full_chords:
        if chord[0] == "Chord Symbol Cannot Be Identified":
            melody.append(note.Rest(type="quarter"))
            continue
        m21chord = chord[-1].pitches
        random_mel_pitch = random.randint(0, len(m21chord) - 1)
        random_mel_pitch = m21chord[random_mel_pitch]
        n = note.Note(random_mel_pitch, type="quarter")
        # pprint(n.pitch)
        if n.pitch.implicitOctave < 5:
            print("shifting " + str(n.pitch) + " to ")
            n.pitch.octave += 5 - n.pitch.implicitOctave
            print(n.pitch)
        melody.append(n)
    file_path = "rule_based_melody.mid"
    melody.write("midi", file_path)
    return file_path
