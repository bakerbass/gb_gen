"""
melody_generator.py

Provides a callable module to:
  • Set up the environment and load the pre-trained Chords Progressions Transformer Melody model.
  • Take an input seed MIDI file, generate a melody based on it, and save the full composition.
  • Extract only the melody channel and create a combined MIDI file with the original seed.
  • Return the file paths of the generated melody and the combined MIDI.
"""

import os
import copy
import torch
import tqdm
import pretty_midi
from midi_utils import quantize_midi
from CPT import TMIDIX
from CPT.x_transformer_1_23_2 import TransformerWrapper, AutoregressiveWrapper, Decoder
from huggingface_hub import hf_hub_download

# Global configuration – adjust these parameters as needed
MODEL_PRECISION = 'float16'  # or "float16" if preferred
DEVICE_TYPE = 'cuda'
SEQ_LEN = 4096       # maximal sequence length
PAD_IDX = 449        # model pad index
DIM = 1024           # model dimension
DEPTH = 4            # decoder depth
HEADS = 8            # number of heads
MODEL_CHECKPOINT_FILE = 'Chords_Progressions_Transformer_Melody_Trained_Model_31061_steps_0.3114_loss_0.9002_acc.pth'
MODELS_DIR = os.path.join("CPT", "Models", "Melody")

# Global model
model = None

def setup_model():
    """
    Sets up and loads the pre-trained model.
    Returns the model and the torch.autocast context.
    """
    global model
    # Choose dtypes based on precision
    if MODEL_PRECISION == 'bfloat16' and torch.cuda.is_bf16_supported():
        dtype_str = 'bfloat16'
    else:
        dtype_str = 'float16'
    ptdtype = {'bfloat16': torch.bfloat16, 'float16': torch.float16}[dtype_str]
    
    ctx = torch.amp.autocast(device_type=DEVICE_TYPE, dtype=ptdtype)

    model_path = os.path.join(MODELS_DIR, MODEL_CHECKPOINT_FILE)

    if not os.path.isfile(model_path):
        print(f"Model not found at {model_path}. Downloading from Hugging Face Hub...")
        model_path = hf_hub_download(
            repo_id='asigalov61/Chords-Progressions-Transformer',
            filename=MODEL_CHECKPOINT_FILE,
            local_dir=MODELS_DIR,
            local_dir_use_symlinks=False
        )
        print("Download complete.")

    # Instantiate the model architecture (adjust the parameters if needed)
    model_instance = TransformerWrapper(
        num_tokens=PAD_IDX+1,
        max_seq_len=SEQ_LEN,
        attn_layers=Decoder(dim=DIM, depth=DEPTH, heads=HEADS, attn_flash=True)
    )
    model_instance = AutoregressiveWrapper(model_instance, ignore_index=PAD_IDX, pad_value=PAD_IDX)
    model_instance = model_instance.cuda()
    
    # Construct the model path
    model_path = os.path.join(MODELS_DIR, MODEL_CHECKPOINT_FILE)
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model checkpoint not found at {model_path}")
    
    # Load state dict and prepare eval mode
    model_instance.load_state_dict(torch.load(model_path))
    model_instance.eval()

    model = model_instance
    print("Model loaded with", dtype_str, "precision.")
    return model, ctx

def generate_melody(seed_midi_path, output_dir='./generated', temperature=0.75,
                    max_melody_notes_per_chord=12, number_of_chords_to_generate=128):
    """
    Generates a melody from a seed MIDI file.
    
    Process:
      1. Reads the seed MIDI and converts it to a single track millisecond score using TMIDIX.
      2. Processes the score (advanced score processing, chordify) to obtain chord tokens.
      3. Runs the generation loop using the global model.
      4. Converts the resulting score (ms_SONG format) to a MIDI file via Tegridy_ms_SONG_to_MIDI_Converter.
      5. Returns the file path of the full composition MIDI.
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Read seed MIDI file in binary mode and convert to ms score:
    with open(seed_midi_path, 'rb') as f:
        seed_data = f.read()
    raw_score = TMIDIX.midi2single_track_ms_score(seed_data)
    
    # Process the score: you can use advanced_score_processor to get an "enhanced" score.
    raw_escore = TMIDIX.advanced_score_processor(raw_score, return_enhanced_score_notes=True)[0]
    # Remove percussion channel events (channel index 9)
    raw_escore = [e for e in raw_escore if e[3] != 9]
    
    # Augment the enhanced score (this might include adding extra attributes)
    escore = TMIDIX.augment_enhanced_score_notes(raw_escore)
    
    # Chordify the score (wrap into an ms SONG object)
    cscore = TMIDIX.chordify_score([1000, escore])
    
    # Create chord tokens list (this snippet mimics the notebook process)
    chords_tokens = []
    cho_toks = []
    for c in cscore:
        # extract unique pitch classes modulo 12
        tones_chord = sorted(set([t[4] % 12 for t in c]))
        try:
            chord_token = TMIDIX.ALL_CHORDS_SORTED.index(tones_chord)
        except Exception:
            fixed = TMIDIX.check_and_fix_tones_chord(tones_chord)
            chord_token = TMIDIX.ALL_CHORDS_SORTED.index(fixed)
        cho_toks.append(chord_token + 128)
        if cho_toks and len(cho_toks) > 1:
            chords_tokens.append(cho_toks)
            cho_toks = [cho_toks[-1]]
    cho_toks = cho_toks + cho_toks  # duplicate final token
    chords_tokens.append(cho_toks)
    
    # Generation: extend a token list using the model.
    output_tokens = []
    for i in tqdm.tqdm(range(min(len(chords_tokens), number_of_chords_to_generate))):
        try:
            output_tokens.extend(chords_tokens[i])
            o = 0
            count = 0
            # Generate up to max melody notes per chord
            while o < 128 and count < max_melody_notes_per_chord:
                x = torch.LongTensor([[output_tokens]]).cuda()
                # Use the autocast context from setup_model
                with torch.amp.autocast(device_type=DEVICE_TYPE, dtype=torch.float16):
                    out = model.generate(x[-number_of_chords_to_generate:], 1,
                                         temperature=temperature,
                                         return_prime=False,
                                         verbose=False)
                o = out.tolist()[0][0]
                if o < 128:
                    output_tokens.append(o)
                    count += 1
        except Exception as e:
            print("Generation error:", e)
            break

    # Build a full ms SONG from the generated tokens.
    song_f = []
    time_cursor = 0
    dur = 32    # you can adjust duration
    vel = 90
    # For each group in the generated tokens list, assemble chord and melody notes.
    for group in chords_tokens:
        chord_index = group[0] - 128
        tones_chord = TMIDIX.ALL_CHORDS_SORTED[chord_index]
        # Add chord events
        for t in tones_chord:
            song_f.append(['note', time_cursor * 16, dur * 16, 0, 60 + t, vel, 0])
            song_f.append(['note', time_cursor * 16, dur * 16, 0, 48 + t, vel, 0])
        ptc_count = len(group)
        ptc_time_dur = dur // (ptc_count if ptc_count > 0 else 1)
        for p in group:
            song_f.append(['note', time_cursor * 16, ptc_time_dur * 16, 3, p, vel, 40])
            time_cursor += ptc_time_dur

    # Define output file base (without extension)
    output_base = os.path.join(output_dir, "Seed-Composition")
    print("Converting to MIDI. Please stand-by...")
    detailed_stats = TMIDIX.Tegridy_ms_SONG_to_MIDI_Converter(
                        song_f,
                        output_signature='Chords Progressions Transformer',
                        output_file_name=output_base,
                        track_name='guitarbotics',
                        list_of_MIDI_patches=[0]*16
                     )
    print("Composition MIDI saved as:", output_base + ".mid")
    return output_base + ".mid"

def extract_melody(midi_file_path, output_dir='./generated', melody_patch=40, melody_channel=3):
    """
    Uses pretty_midi to extract only the melody channel from a given MIDI file.
    It returns the path of the newly extracted melody MIDI file.
    """
    try:
        pm_midi = pretty_midi.PrettyMIDI(midi_file_path)
        # Filter instruments: choose those with a program matching the melody patch or on the melody channel.
        melody_instruments = [inst for inst in pm_midi.instruments if inst.program == melody_patch or inst.channel == melody_channel]
        if not melody_instruments:
            print("No melody instrument found in", midi_file_path)
            return midi_file_path
        # Create new PrettyMIDI with only melody instruments.
        melody_pm = pretty_midi.PrettyMIDI()
        for inst in melody_instruments:
            melody_pm.instruments.append(inst)
        base = os.path.splitext(os.path.basename(midi_file_path))[0]
        extracted_path = os.path.join(output_dir, base + "_melody.mid")
        melody_pm.write(extracted_path)
        print("Melody-only MIDI saved as:", extracted_path)
        return extracted_path
    except Exception as e:
        print("Error extracting melody channel:", e)
        return midi_file_path

def combine_seed_with_melody(seed_midi_path, melody_midi_path, output_dir='./generated', combined_name="Combined_Seed_Melody.mid"):
    """
    Combines the seed MIDI file with an extracted melody MIDI file.
    Simple implementation combines the instruments from both files into one PrettyMIDI object.
    Returns the path to the combined MIDI file.
    """
    try:
        seed_pm = pretty_midi.PrettyMIDI(seed_midi_path)
        melody_pm = pretty_midi.PrettyMIDI(melody_midi_path)
        combined_pm = pretty_midi.PrettyMIDI()
        # Add all instruments from seed MIDI.
        for inst in seed_pm.instruments:
            combined_pm.instruments.append(inst)
        # Append all instruments from melody MIDI.
        for inst in melody_pm.instruments:
            combined_pm.instruments.append(inst)
        combined_path = os.path.join(output_dir, combined_name)
        combined_pm.write(combined_path)
        print("Combined MIDI saved as:", combined_path)
        return combined_path
    except Exception as e:
        print("Error combining seed with melody:", e)
        return seed_midi_path
def limit_note_range(midi_file_path, output_dir='./generated', new_name=None):
    """
    Adjusts the pitches of all notes in the given MIDI file so that each note's pitch falls 
    within the range [40, 74]. For any note outside this range, the note's pitch is shifted by 
    octaves (+/- 12) until it falls into this range.
    
    Parameters:
      midi_file_path (str): Path to the original MIDI file.
      output_dir (str): Directory where the adjusted MIDI file will be saved.
      new_name (str): (Optional) New filename (without extension). If not specified, the original
                      basename is used with a '_range_adjusted' suffix.
    
    Returns:
      str: The file path to the adjusted MIDI file.
    """
    import pretty_midi
    import os
    
    # Load the MIDI file.
    pm = pretty_midi.PrettyMIDI(midi_file_path)
    
    # Process each instrument and each note.
    for instrument in pm.instruments:
        for note in instrument.notes:
            # While the note pitch is less than 40, add 12.
            while note.pitch < 52:
                #print(f"Shifting note pitch {note.pitch} up by an octave: ", note.pitch + 12)
                note.pitch += 12
            # While the note pitch is greater than 74, subtract 12.
            while note.pitch > 86:
                #print(f"Shifting note pitch {note.pitch} down by an octave: ", note.pitch - 12)
                note.pitch -= 12
    
    # Ensure output directory exists.
    os.makedirs(output_dir, exist_ok=True)
    
    # Determine the new file name.
    base = os.path.splitext(os.path.basename(midi_file_path))[0]
    if new_name:
        output_base = new_name
    else:
        output_base = base + "_range_limited"
    
    adjusted_path = os.path.join(output_dir, output_base + ".mid")
    pm.write(adjusted_path)
    print("Adjusted MIDI saved as:", adjusted_path)
    return adjusted_path
def generate_melody_variations(seed_melody_path, variations=3, output_dir='./generated', **gen_kwargs):
    """
    Uses a given seed MIDI file (for example, a previously generated melody)
    to generate multiple new composition files.
    
    Parameters:
      seed_melody_path (str): MIDI file to use as the seed.
      variations (int): Number of new files to generate.
      output_dir (str): Directory where generated files will be stored.
      **gen_kwargs: Additional keyword arguments to pass to generate_melody.
    
    Returns:
      list: List of file paths for the generated composition MIDI files.
    """
    variation_paths = []
    # Loop to generate the specified number of variations.
    for i in range(variations):
        var_output_base = os.path.join(output_dir, "Seed-Composition_variation_" + str(i+1))
        print(f"Generating variation {i+1} using seed {seed_melody_path}...")
        # Here we call generate_melody using the seed_melody_path.
        # (The generation process uses TMIDIX conversion which should work with the seed MIDI format.)
        composition_path = generate_melody(seed_melody_path, output_dir=var_output_base, **gen_kwargs)
        
        # Optionally, you can also adjust the note range of this new composition:
        composition_path = limit_note_range(composition_path)
        variation_paths.append(composition_path)
    return variation_paths
if __name__ == "__main__":
    # For testing purposes: set up, load model, generate and process seed compositions.
    seed_midi = os.path.join("test_midis", "flatstest.mid")
    print("Setting up model...")
    setup_model()
    
    # Quantize Midi
    print("Generating composition from seed MIDI:", seed_midi)
    composition_midi = generate_melody(seed_midi)
    print("Generated composition MIDI stored at:", composition_midi)
    
    # Extract melody from the composition MIDI.
    melody_midi = extract_melody(composition_midi)
    print("Extracted melody MIDI stored at:", melody_midi)
    
    # Combine the original seed with the extracted melody.
    combined_midi = combine_seed_with_melody(seed_midi, melody_midi)
    
    # Limit the note range of the combined file.
    limited_midi = limit_note_range(combined_midi)
    print("Combined seed and melody MIDI (limited) stored at:", limited_midi)
    
    # Use the generated melody (or the limited version) as a new seed
    # for generating three new variations.
    print("Generating melody variations using the extracted melody as seed...")
    variations = generate_melody_variations(limited_midi, variations=3)
    for idx, var in enumerate(variations):
        print(f"Variation {idx+1} MIDI stored at: {var}")