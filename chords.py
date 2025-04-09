from music21 import converter, chord, harmony, note, stream, midi
import time
import pretty_midi
from pprint import pprint

class MIDI_Stream:
    def __init__(self, midi_file, bpm=None, timesig=[4, 4]):
        self.midi_file = midi_file
        self.midi_stream = pretty_midi.PrettyMIDI(midi_file)
        self.duration = self.midi_stream.get_end_time()
        self.bpm = bpm
        self.timesig = timesig
        self.notes = self.get_notes()

    def get_tempo(self):
        tempo_changes = self.midi_stream.get_tempo_changes()
        if len(tempo_changes[0]) > 0:
            tempo = tempo_changes[1][0]
            return tempo
        else:
            return

    def get_notes(self):
        notes = []
        for instrument in self.midi_stream.instruments:
            for note in instrument.notes:
                notes.append({"pitch": note.pitch, "onset": note.start, "offset": note.end})
        return notes

    def get_full_chord_list(self):
        if self.bpm is None:
            self.bpm = self.get_tempo()
        beats_total = int((self.bpm/60)*self.duration)
        measures = round(beats_total / self.timesig[0])
        strip_first_measure = False
        if(measures % 2 != 0): # Sometimes NN adds a measure at the beginning. Since we are only doing even measures, we can find odd total measures and strip the first if needed.
            strip_first_measure = True
        quarter_length = 60 / self.bpm
        sixteenth = quarter_length/4
        notes = self.notes
        chord_list = []
        curr_chord = []
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
                if self.notes[i]["pitch"] >= curr_highest_pitch:
                    curr_highest = self.notes[i]["onset"]
                    curr_highest_pitch = self.notes[i]["pitch"]
                if self.notes[i]["pitch"] <= curr_lowest_pitch:
                    curr_lowest = self.notes[i]["onset"]
                    curr_lowest_pitch = self.notes[i]["pitch"]
                i += 1
            m21chord = chord.Chord(curr_chord)
            # if len(m21chord) == 0:
                # print(notes[i]["pitch"])
            try:
                root = m21chord.root()
            except:
                root = None
            chord_symbol = harmony.chordSymbolFigureFromChord(m21chord)
            # print(chord_symbol)
            if "/" in chord_symbol:
                chord_symbol = chord_symbol.split("/")[0]
            if "power" in chord_symbol.lower():
                chord_symbol = chord_symbol.split("power")[0] + "5"
            chord_symbol = chord_symbol.replace("-", "b")
            if "add" in chord_symbol:
                chord_symbol = chord_symbol.split("add")[0]
            # Append the tuple (chord_symbol, m21chord) for simple processing.
            if not strip_first_measure:
                chord_list.append((chord_symbol, m21chord, root, "eighth note "+str(interval + 1), str(self.get_strum(curr_lowest, curr_highest))))
            elif interval > 3: # Strip first measure using a conditional append. Also account for ontime offset
                chord_list.append((chord_symbol, m21chord, root, "eighth note "+str(interval - 3), str(self.get_strum(curr_lowest, curr_highest))))
                
            curr_max_interval_length += quarter_length
            curr_highest = 0
            curr_lowest = 100000
            if i < len(notes) and curr_max_interval_length >= notes[i]["onset"]:
                curr_chord = []
                curr_lowest = 0
                curr_highest = 0
                curr_chord = []

                curr_highest_pitch = 0
                curr_lowest_pitch = 10000
        return chord_list

    def get_simple_chords(self):
        """
        Returns a simplified chord list for melody generation.
        Each element is a tuple: (chord_symbol, m21chord)
        where m21chord is a music21 Chord object.
        """
        full_chords = self.get_full_chord_list()
        simple_chords = []
        for item in full_chords:
            # item[0] is the chord symbol, item[-1] is the underlying music21 chord.
            simple_chords.append((item[0], item[-1]))
        return simple_chords

    def get_strum(self, lowest, highest):
        if highest > lowest:
            return "DOWN"
        elif lowest > highest:
            return "UP"
        else:
            return "HOLD"

    def get_UDP_lists(self):
        if self.bpm is None:
            self.bpm = 100 # self.get_tempo()
        print("BPM: ", self.bpm)
        full_chords = self.get_full_chord_list()
        chord_list = []
        strum_list = []
        pluck_list = []
        for chord in full_chords:
            beat_str = chord[3].split(" ")[-1]
            try:
                beat = float(beat_str)
            except ValueError:
                beat = 0.0
            time_in_seconds = (beat - 1) / self.bpm * 60
            if "pedal" in chord[0]:
                pluck_list.append((chord[0], time_in_seconds))
            elif chord[4] != "HOLD" and chord[0] != "Chord Symbol Cannot Be Identified":
                chord_list.append((chord[0], round(time_in_seconds, 5)))
                strum_list.append((chord[4], round(time_in_seconds, 5)))
        return chord_list, strum_list, pluck_list, full_chords