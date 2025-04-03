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
        quarter_length = 60 / self.bpm
        sixteenth = quarter_length/4
        notes = self.get_notes()
        chord_list = []
        curr_chord = []
        curr_max_interval_length = quarter_length - sixteenth
        i = 0
        for interval in range(beats_total):
            while i < len(notes) and (notes[i]["onset"] <= curr_max_interval_length):
                curr_chord.append(notes[i]["pitch"])
                i += 1
            m21chord = chord.Chord(curr_chord)
            try:
                root = m21chord.root()
            except:
                root = None
            chord_symbol = harmony.chordSymbolFigureFromChord(m21chord)
            if "/" in chord_symbol:
                chord_symbol = chord_symbol.split("/")[0]
            if "power" in chord_symbol.lower():
                chord_symbol = chord_symbol.split("power")[0] + "5"
            chord_symbol = chord_symbol.replace("-", "b")
            # Append the tuple (chord_symbol, m21chord) for simple processing.
            chord_list.append((chord_symbol, m21chord))
            curr_max_interval_length += quarter_length
            if i < len(notes) and curr_max_interval_length >= notes[i]["onset"]:
                curr_chord = []
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
            self.bpm = self.get_tempo()
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
                chord_list.append((chord[0], time_in_seconds))
                strum_list.append((chord[4], time_in_seconds))
        return chord_list, strum_list, pluck_list, full_chords