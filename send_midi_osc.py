import mido

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