import midi2audio
from anticipation.convert import events_to_midi
fsynth = midi2audio.FluidSynth('./8bitsf.sf2')
def initialize_fluidsynth(soundfont_path='./8bitsf.sf2'):
    """
    Initializes FluidSynth with the given soundfont.

    :param soundfont_path: Path to the soundfont file.
    :return: Initialized FluidSynth object.
    """
    fsynth = midi2audio.FluidSynth(soundfont_path)

def synthesize_tokens(tokens, name='token_output'):
    """
    Synthesizes audio from MIDI events using FluidSynth.

    :param fs: Initialized FluidSynth object.
    :param tokens: MIDI events to synthesize.
    :return: Path to the synthesized WAV file.
    """
    midifilepath = './data/output/' + name + '.mid'
    mid = events_to_midi(tokens)
    mid.save(midifilepath)
    fsynth.midi_to_audio(midifilepath, './data/audio/' + name + '.wav')

def synthesize_midi(midi, name='midi_output'):
    """
    Synthesizes audio from MIDI events using FluidSynth.

    :param fs: Initialized FluidSynth object.
    :param tokens: MIDI events to synthesize.
    :return: Path to the synthesized WAV file.
    """
    fsynth.midi_to_audio(midi, './data/audio/' + name + '.wav')