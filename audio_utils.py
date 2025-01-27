import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt

def normalize_wav(file_path):
    sample_rate, data = wavfile.read(file_path)
    data = data / np.max(np.abs(data))
    wavfile.write(file_path, sample_rate, data.astype(np.float32))
    return file_path
def plot_wav(file_path, bpm, start_bar, end_bar):
    sample_rate, data = wavfile.read(file_path)
    time = np.linspace(0, len(data) / sample_rate, num=len(data))
    plt.figure(figsize=(12, 6))
    plt.plot(time, data)
    plt.title("Waveform of " + file_path)
    plt.xlabel("Time [s]")
    plt.ylabel("Amplitude")
    beats_per_bar = 4
    seconds_per_beat = 60 / bpm
    seconds_per_bar = beats_per_bar * seconds_per_beat
    for bar in range(start_bar, end_bar + 1):
        plt.axvline(x=bar * seconds_per_bar, color='r', linestyle='--')
    plt.show()