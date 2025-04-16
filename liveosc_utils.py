from midi_utils import *

def midi_to_liveosc(client, file_path, segmented_sends=False, input_offset=0):
    print("/" + "="*50 + "/")
    print("midi_to_liveosc()")
    print("/" + "="*50 + "/\n")
    global midi_file_count, midi_file_path

    if not validate_midi_file(file_path):
        return

    midi_file_path = file_path
    
    if (segmented_sends):
        midi_file_path = file_path
        if midi_file_count == 0:
            print("First file being sent! File path:" + file_path + " | File no. " + str(midi_file_count))
            # First file: send immediately with fire_immediately False and no offset.
            send_midi(client, file_path, fire_immediately=True, time_offset=8)
            midi_file_count += 1
        elif midi_file_count == 1:
            print("Second file being sent! File path:" + file_path + " | File no. " + str(midi_file_count))
            # Second file: send to same track/clip as first file, but offset by one bar (e.g. 4 beats).
            client.send_message("/live/clip/fire", [0, 0])
            send_midi(client, file_path, fire_immediately=False, time_offset=12, file_idx=1)
            midi_file_count += 1
        else:
            print("Subsequent file being sent! File path:" + file_path + " | File no. " + str(midi_file_count))
            send_midi(client, file_path, fire_immediately=False, clip_index=midi_file_count-1, file_idx=midi_file_count)
    else:
        send_midi(client, file_path, fire_immediately=True, time_offset=input_offset)
    #interact() # melody, continuation, send continuation to liveosc
    return midi_file_path
def anti_to_liveosc(client, file_path, clip_index=1):
    print("/" + "="*50 + "/")
    print("anti_to_liveosc()")
    print("/" + "="*50 + "/\n")
    if not validate_midi_file(file_path):
        return
    send_midi(client, file_path, fire_immediately=False, clip_index=clip_index)
    

def send_midi(client, file_path, bpm=120, timesig=[4, 4], fire_immediately=False, time_offset=0, track_index=0, clip_index=0, file_idx=0):
    """
    Sends the MIDI note events in file_path to Ableton via OSC.
    If a time_offset (in beats) is provided, it will be added to each note event's start time.

    :param client: OSC client.
    :param file_path: Path to the MIDI file.
    :param bpm: Beats per minute.
    :param timesig: Time signature as [beats_per_bar, note_value].
    :param fire_immediately: If True, the clip is fired immediately.
    :param time_offset: Offset (in beats) added to all note events.
    """
    try:
        midi_file = mido.MidiFile(file_path)
        # Calculate clip length in beats using MIDI file length
        clip_length = midi_file.length / bpm * 60 * timesig[0]  # rough estimate in beats

        # Create a new MIDI clip in Ableton (if not the second file):
        if not file_idx == 1:
            clip_length = 16
            print(f"Creating new clip at track {track_index}, clip {clip_index}, length {clip_length}")
            client.send_message("/live/clip_slot/create_clip", [track_index, clip_index, clip_length])

        active_notes = {}  # note -> (start_time, velocity)
        note_events = []   # List to store note events
        current_time = 0   # absolute time in ticks

        for msg in midi_file.tracks[0]:
            current_time += msg.time
            current_time_in_beats = current_time / midi_file.ticks_per_beat
            # Do not add offset here when recording the note start.
            if msg.type == "note_on" and msg.velocity > 0:
                active_notes[msg.note] = (current_time_in_beats, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                if msg.note in active_notes:
                    start_time, velocity = active_notes.pop(msg.note)
                    # When sending, add the time_offset to both the start and current_time
                    effective_start = start_time + time_offset
                    effective_end = current_time_in_beats + time_offset
                    duration = effective_end - effective_start
                    note_events.append((track_index, clip_index, msg.note, effective_start, duration, velocity, 0))

        # Send note events to Ableton
        for event in note_events:
            client.send_message("/live/clip/add/notes", list(event))
        if not (time_offset == 0):
            client.send_message("/live/clip/set/loop_start", [track_index, clip_index, 8])
            client.send_message("/live/clip/set/loop_end", [track_index, clip_index, 24])
        else:
            client.send_message("/live/clip/set/loop_end", [track_index, clip_index, clip_length * 4])
        if fire_immediately: # honestly this stuff should happen outside of this file
            print("Fire away!")
            client.send_message("/live/clip/fire", [track_index, clip_index])
        print(f"Loaded MIDI file: {file_path} (offset {time_offset} beats)")
    except Exception as e:
        print(f"Failed to load MIDI file: {e}")