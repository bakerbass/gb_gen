from midi_utils import *
from send_midi_osc import send_midi
from main import interact

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
    interact() # melody, continuation, send continuation to liveosc
    return midi_file_path
def anti_to_liveosc(client, file_path, clip_index=1):
    print("/" + "="*50 + "/")
    print("anti_to_liveosc()")
    print("/" + "="*50 + "/\n")
    if not validate_midi_file(file_path):
        return
    send_midi(client, file_path, fire_immediately=False, clip_index=clip_index)