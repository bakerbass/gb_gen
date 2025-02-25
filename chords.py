from music21 import converter, chord, harmony
import time
import pretty_midi
import pprint
import re

class MIDI_Stream:
    def __init__(self, midi_file, bpm=None, timesig=[4, 4]):
        self.midi_file = midi_file
        self.midi_stream = pretty_midi.PrettyMIDI(midi_file)
        self.duration = self.midi_stream.get_end_time()
        self.bpm = bpm
        self.timesig = timesig
    def get_tempo(self):
        tempo_changes = self.midi_stream.get_tempo_changes()
        if len(tempo_changes[0]) > 0:
            tempo = tempo_changes[1][0]
            #print(f"Tempo: {tempo} BPM")
            return tempo
        else:
            #print("No tempo found")
            return

    def get_notes(self):
        notes = []
        for instrument in self.midi_stream.instruments:
            for note in instrument.notes:
                notes.append({"pitch": note.pitch, "onset": note.start, "offset": note.end})
        # pprint.pp(notes)
        return notes

    def get_full_chord_list(self):

        # #print(self.duration)
        # beats_total = int((self.get_tempo()/60)*self.duration)
        #print(self.duration)
        beats_total = int((self.bpm/60)*self.duration)
        # print("Beats total: ", beats_total)
        # quarter_length = self.duration/beats_total
        quarter_length = 60 / self.bpm
        # print("Quarter length: ", quarter_length)
        sixteenth = quarter_length/4
        notes = self.get_notes()
        # #print(beats_total)
        chord_list = []
        # curr_note = notes[0]
        curr_highest_pitch = 0
        curr_lowest_pitch = 255
        curr_chord = []
        curr_highest = 0
        curr_lowest = 255
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
            m21chord = chord.Chord(curr_chord)
            try:
                root = m21chord.root()
            except:
                root = None
            if root is not None:
                chord_third = m21chord.third
                chord_fifth = m21chord.fifth
                chord_seventh = m21chord.seventh
                chord_9 = m21chord.getChordStep(9)
                chord_11 = m21chord.getChordStep(11)
                chord_13 = m21chord.getChordStep(13)
            else:
                chord_9 = None
                chord_11 = None
                chord_13 = None
                chord_third = None
                chord_fifth = None
                chord_seventh = None
            chord_symbol = harmony.chordSymbolFigureFromChord(m21chord)
            # Remove slash chord's bass note.
            if "/" in chord_symbol:
                chord_symbol = chord_symbol.split("/")[0]
            # Convert power chords (e.g., "Gpower" or "Gpower/D") to a proper power chord format.
            if "power" in chord_symbol.lower():
                chord_symbol = chord_symbol.split("power")[0] + "5"
            chord_symbol = chord_symbol.replace("-", "b")
            chord_list.append((
                chord_symbol,
                root,
                m21chord.quality,
                "quarter note " + str(interval + 1),
                str(self.get_strum(curr_lowest, curr_highest)),
                "3rd: " + str(chord_third),
                "5th: " + str(chord_fifth),
                "7th: " + str(chord_seventh),
                "9th: " + str(chord_9),
                "11th: " + str(chord_11),
                "13th: " + str(chord_13)
            ))
            # prev_chord = m21chord.pitchedCommonName
            curr_max_interval_length += quarter_length
            curr_lowest = 0
            curr_highest = 0
            if i < len(notes) and curr_max_interval_length >= notes[i]["onset"]:
                curr_chord = []
                curr_highest = 0
                curr_lowest = 100000
                curr_highest_pitch = 0
                curr_lowest_pitch = 10000
        #pprint.pp(chord_list) #remove for latency
        return chord_list

    def get_strum(self, lowest, highest):
        if highest > lowest:
            return "DOWN"
        elif lowest > highest:
            return "UP"
        else:
            return "HOLD"

    def get_UDP_lists(self):
        """
        Iterates over the full chord list and returns two lists:
        
        chord_list: list of tuples (chord_symbol, time_in_seconds)
        strum_list: list of tuples (strum_direction, time_in_seconds)
        
        The time is calculated as:
            (float(chord[3].split(" ")[-1]) - 1) / self.bpm * 60
        """
        if self.bpm is None:
            self.bpm = self.get_tempo()
        print("BPM: ", self.bpm)
        full_chords = self.get_full_chord_list()
        chord_list = []
        strum_list = []
        pluck_list = []
        for chord in full_chords:
            # Converting from quarter note to seconds here (this is quantizing the time, may need to rework this)
            beat_str = chord[3].split(" ")[-1]
            try:
                beat = float(beat_str)
            except ValueError:
                beat = 0.0
            time_in_seconds = (beat - 1) / self.bpm * 60
            if "pedal" in chord[0]:
                pluck_list.append((chord[0], time_in_seconds))
            elif chord[4] != "HOLD" and chord[0] != "Chord Symbol Cannot Be Identified":
                chord_list.append((chord[0], time_in_seconds))
                strum_list.append((chord[4], time_in_seconds))

        return chord_list, strum_list, pluck_list
if __name__ == "__main__":
    start = time.time()
    midi_path = "sharptest.mid"
    midi_stream = MIDI_Stream(midi_path)
    chords = midi_stream.get_full_chord_list()
    end = time.time()
    #print(end - start)
    pprint.pp(midi_stream.get_UDP_lists(midi_stream))
