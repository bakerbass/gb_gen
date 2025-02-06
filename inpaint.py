import sys
import time
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from transformers import AutoModelForCausalLM
from mido import MidiFile, tempo2bpm

from IPython.display import Audio

from anticipation import ops
from anticipation.sample import generate
from anticipation.tokenize import extract_instruments
from anticipation.convert import events_to_midi, midi_to_events
from anticipation.visuals import visualize
from anticipation.config import *
from anticipation.vocab import *
from model_loader import load_model
from audio_utils import normalize_wav
from midi_utils import detect_bpm

def process_midi_file(midi_file_path, start_time, end_time, model, time_unit='bars'):
    bpm = detect_bpm(midi_file_path)
    if bpm is None:
        print("BPM not detected. Using default values.")
        bpm = 120

    beats_per_bar = 4
    seconds_per_beat = 60 / bpm
    seconds_per_bar = beats_per_bar * seconds_per_beat

    if time_unit == 'bars':
        start_time = start_time * seconds_per_bar
        end_time = end_time * seconds_per_bar

    start = time.time()
    events = midi_to_events(midi_file_path)
    end = time.time()
    print("MIDI converted in ", end-start, " seconds")

    segment = events
    segment = ops.translate(segment, -ops.min_time(segment, seconds=False))
    # further work to be done here regarding the control flow and history...
    history = ops.clip(segment, 0, start_time, clip_duration=False)
    anticipated = [CONTROL_OFFSET + tok for tok in ops.clip(segment, start_time + .01, end_time, clip_duration=False)]

    start = time.time()
    inpainted = generate(model, start_time, end_time, inputs=history, controls=anticipated, top_p=.95)
    end = time.time()
    print("Generated in ", end-start, " seconds")
    visualize(inpainted, 'output.png')
    combined = ops.combine(inpainted, anticipated)
    return inpainted, combined