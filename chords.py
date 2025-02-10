from music21 import converter, chord
import time
import pretty_midi
import pprint
import re
# def get_notes(midi_file_pm):
#     notes = []
#     for instrument in midi_file_pm.instruments:
#         for note in instrument.notes:
#             notes.append({"pitch": note.pitch, "onset": note.start, "offset": note.end})
#     return notes
# def get_key_signature(midi_stream):
#     # Load the MIDI file into a music21 stream
#     # Analyze the key signature of the stream
#     key_signature = midi_stream.analyze('key')

#     return key_signature

# def get_chords(midi_stream):
#     chords = []
#     for element in midi_stream.recurse().notes:
#         if isinstance(element, chord.Chord):
#             chords.append(element)

#     for c in chords:
#         print(str(c)+" ~~ "+str(c.pitchedCommonName))

# # def get_chord()
# def get_etimated_tempo(midi_file_pm):
#     tempo_changes = midi_file_pm.get_tempo_changes()
#     if len(tempo_changes[0]) > 0:
#         tempo = tempo_changes[1][0]
#         print(f"Tempo: {tempo} BPM")
#         return tempo
#     else:
#         print("No tempo found")
#         return
# def get_full_chord_output(notes, duration, tempo):
#     beats_total = int((tempo/60)*duration)
#     quarter_length = duration/beats_total
#     sixteenth = quarter_length/4
#     # print(beats_total)
#     chord_list = [beats_total]
#     # curr_note = notes[0]
#     curr_highest_pitch = 0
#     curr_lowest_pitch = 10000
#     curr_chord = []
#     curr_highest = 0
#     curr_lowest = 100000
#     curr_max_interval_length = quarter_length - sixteenth
#     i = 0
#     for interval in range(beats_total):
#         while i < len(notes) and (notes[i]["onset"] <= curr_max_interval_length):
#             curr_chord.append(notes[i]["pitch"])
#             if notes[i]["pitch"] > curr_highest_pitch:
#                 curr_highest = notes[i]["onset"]
#                 curr_highest_pitch = notes[i]["pitch"]
#             if notes[i]["pitch"] < curr_lowest_pitch:
#                 curr_lowest = notes[i]["onset"]
#                 curr_lowest_pitch = notes[i]["pitch"]
#             print(curr_highest, curr_lowest)
#             i += 1
#         chord_list.append((chord.Chord(curr_chord).pitchedCommonName, "quarter note "+str(interval + 1), str(get_strum(curr_lowest, curr_highest))))
#         # prev_chord = chord.Chord(curr_chord).pitchedCommonName
#         curr_max_interval_length += quarter_length
#         curr_lowest = 0
#         curr_highest = 0
#         if i < len(notes) and curr_max_interval_length > notes[i]["onset"]:
#             curr_chord = []
#             curr_highest = 0
#             curr_lowest = 100000
#             curr_highest_pitch = 0
#             curr_lowest_pitch = 10000
#     return chord_list
# def get_strum(lowest, highest):
#     if highest > lowest:
#         return "DOWN"
#     elif lowest > highest:
#         return "UP"
#     else:
#         return "HOLD"

class MIDI_Stream:
    def __init__(self, midi_file):
        self.midi_file = midi_file
        self.midi_stream = pretty_midi.PrettyMIDI(midi_file)
        self.duration = self.midi_stream.get_end_time()

    def get_tempo(self):
        tempo_changes = self.midi_stream.get_tempo_changes()
        if len(tempo_changes[0]) > 0:
            tempo = tempo_changes[1][0]
            print(f"Tempo: {tempo} BPM")
            return tempo
        else:
            print("No tempo found")
            return

    def get_notes(self):
        notes = []
        for instrument in self.midi_stream.instruments:
            for note in instrument.notes:
                notes.append({"pitch": note.pitch, "onset": note.start, "offset": note.end})
        # pprint.pp(notes)
        return notes

    def get_full_chord_list(self):
        # print(self.duration)
        # beats_total = int((self.get_tempo()/60)*self.duration)
        beats_total = int((self.get_tempo()/60)*8)
        # quarter_length = self.duration/beats_total
        quarter_length = 8/beats_total
        sixteenth = quarter_length/4
        notes = self.get_notes()
        # print(beats_total)
        chord_list = []
        # curr_note = notes[0]
        curr_highest_pitch = 0
        curr_lowest_pitch = 10000
        curr_chord = []
        curr_highest = 0
        curr_lowest = 100000
        curr_max_interval_length = quarter_length - sixteenth
        i = 0
        for interval in range(beats_total):
            while i < len(notes) and (notes[i]["onset"] <= curr_max_interval_length):
                curr_chord.append(notes[i]["pitch"])
                if notes[i]["pitch"] > curr_highest_pitch:
                    curr_highest = notes[i]["onset"]
                    curr_highest_pitch = notes[i]["pitch"]
                if notes[i]["pitch"] < curr_lowest_pitch:
                    curr_lowest = notes[i]["onset"]
                    curr_lowest_pitch = notes[i]["pitch"]
                i += 1
            chord_list.append((chord.Chord(curr_chord).pitchedCommonName, chord.Chord(curr_chord).root(), chord.Chord(curr_chord).quality, "quarter note "+str(interval + 1), str(self.get_strum(curr_lowest, curr_highest))))
            # prev_chord = chord.Chord(curr_chord).pitchedCommonName
            curr_max_interval_length += quarter_length
            curr_lowest = 0
            curr_highest = 0
            if i < len(notes) and curr_max_interval_length >= notes[i]["onset"]:
                curr_chord = []
                curr_highest = 0
                curr_lowest = 100000
                curr_highest_pitch = 0
                curr_lowest_pitch = 10000
        pprint.pp(chord_list) #remove for latency
        return chord_list

    def get_strum(self, lowest, highest):
        if highest > lowest:
            return "DOWN"
        elif lowest > highest:
            return "UP"
        else:
            return "HOLD"


    def extract_chord_info(self, chord_desc):
        """
        Given a chord description string (e.g., "F#-minor seventh chord"),
        this function extracts the chord root and then builds a new quality
        string from scratch based on regex searches rather than substituting
        in the original string.

        Mappings:
          - "half diminished" -> "o"
          - "diminished"      -> "dim"
          - "dominant-seventh"-> "7"
          - "minor"           -> "m" (and if "seventh" is also present, "m7")
          - "major"           -> (major chords remain unmarked)
        """
        # --- Extract the root ---
        # Look for a root at the beginning (like "F#-")
        root = str(chord_desc[1])
        root = re.sub(r'\d$', '', root)
        chord_desc = str(chord_desc)
        # --- Build the new quality string from scratch ---
        quality_new = ""

        # Check for "half diminished" first.
        if re.search(r"half[-\s]*diminished", chord_desc, flags=re.IGNORECASE):
            quality_new = "o"
        # If not half diminished, then check for "diminished"
        elif re.search(r"diminished", chord_desc, flags=re.IGNORECASE):
            quality_new = "dim"
        # Check for minor quality.
        elif re.search(r"\bminor\b", chord_desc, flags=re.IGNORECASE):
            quality_new = "m"
            # If "seventh" appears along with "minor", add a 7.
            if re.search(r"seventh", chord_desc, flags=re.IGNORECASE):
                quality_new += "7"
        # Check for dominant seventh.
        elif re.search(r"dominant[-\s]*seventh", chord_desc, flags=re.IGNORECASE):
            quality_new = "7"
        # If "major" is found, we leave quality_new empty (major chords have no symbol).
        elif re.search(r"\bmajor\b", chord_desc, flags=re.IGNORECASE):
            quality_new = ""

        return root, quality_new


# if __name__ == "__main__":
start = time.time()
midi_path = "truckin.mid"
midi_stream = MIDI_Stream(midi_path)
chords = midi_stream.get_full_chord_list()
end = time.time()
print(end - start)
for chord in chords:
    root, quality = midi_stream.extract_chord_info(chord)
    chordname = root + quality
    print(chordname)
# start = time.time()
# midi_file = 'upstrumsdownstrumsohmy.mid'  # Replace with the path to your MIDI file
# midi_file_pm = pretty_midi.PrettyMIDI(midi_file)
# midi_stream = converter.parse(midi_file)
# midi_notes = get_notes(midi_file_pm)
# file_duration = midi_file_pm.get_end_time()
# key_signature = get_key_signature(midi_stream)
# notes = get_notes(midi_file_pm)
# tempo = get_etimated_tempo(midi_file_pm)
# # print("Detected Key Signature:", key_signature)
# # get_chords(midi_stream)
# # print(tempo)
# # print(file_duration)
# # pprint.pp(notes)
# # pprint.pp(get_full_chord_output(notes, file_duration, tempo))
# end = time.time()
# print(str(end - start)+" secs")