import argparse
import time
import threading
import mido
from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server, udp_client

response_port = 11001  # Port to receive OSC responses
received_data = {"bpm": 120, "time_signature": (4, 4)}  # Dictionary to store received values
DEFAULT_BPM = 120  # Default BPM value
# Callback functions for OSC responses
def bpm_callback(address, *args):
    received_data["bpm"] = args[0]
    print(f"Received BPM: {args[0]}")

def time_signature_callback(address, *args):
    if "numerator" in address:
        received_data["time_signature"] = (args[0], received_data["time_signature"][1])
        print(f"Received Time Signature Numerator: {args[0]}")
    elif "denominator" in address:
        received_data["time_signature"] = (received_data["time_signature"][0], args[0])
        print(f"Received Time Signature Denominator: {args[0]}")

# Setup the dispatcher
dispatcher = Dispatcher()
dispatcher.map("/live/song/get/tempo", bpm_callback)  # Map the tempo query response
dispatcher.map("/live/song/get/signature_numerator", time_signature_callback)  # Map the time signature query response
dispatcher.map("/live/song/get/signature_denominator", time_signature_callback)  # Map the time signature query response
# Start the OSC server in a separate thread
def start_server(ip, port):
    server = osc_server.ThreadingOSCUDPServer((ip, port), dispatcher)
    print(f"OSC Server running on {server.server_address}")
    server.serve_forever()

def query_ableton(client):
    # Query Ableton for BPM and time signature
    client.send_message("/live/song/get/tempo", [])  # Request BPM
    client.send_message("/live/song/get/signature_numerator", [])  # Request time signature
    client.send_message("/live/song/get/signature_denominator", [])  # Request time signature denominator
    # Wait for responses (you might need to adjust the sleep time)
    time.sleep(1)

    bpm = received_data.get("bpm")
    time_signature = received_data.get("time_signature")

    if bpm is None or time_signature is None:
        print("Failed to receive BPM or Time Signature from Ableton")
        bpm = DEFAULT_BPM
        time_signature = (4, 4)

    print(f"Final BPM: {bpm}, Time Signature: {time_signature[0]}/{time_signature[1]}")
    return bpm, time_signature

def create_midi_clip(client, bpm):
    # Load MIDI file
    midi_file = mido.MidiFile("gnr_kohd.mid")

    # Select track and clip slot
    track_index = 0  # Track number (0-based)
    clip_index = 0   # Clip slot number (0-based)

    # Create a new MIDI clip
    clip_length = midi_file.length * (bpm / 60)  # MIDI file length in beats considering BPM
    client.send_message("/live/clip/create", [track_index, clip_index, clip_length])  # Length in beats

    # Parse MIDI notes
    active_notes = {}  # Dictionary to track active notes by their pitch
    current_time = 0  # Tracks the elapsed time in ticks for proper timing

    for msg in midi_file.tracks[0]:  # Adjust for the desired MIDI track
        current_time += msg.time  # Update the current time based on the delta time in the MIDI file

        if msg.type == "note_on" and msg.velocity > 0:  # Start a new note
            active_notes[msg.note] = current_time  # Record the start

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send_ip", default="127.0.0.1",
                        help="The IP of the OSC server to send to")
    parser.add_argument("--send_port", type=int, default=11000,
                        help="The port the OSC server is sending to")
    parser.add_argument("--recv_ip", default="127.0.0.1",
                        help="The IP to listen on")
    parser.add_argument("--recv_port", type=int, default=11001,
                        help="The port to listen on")
    args = parser.parse_args()

    # Start the server in a separate thread
    server_thread = threading.Thread(target=start_server, args=(args.recv_ip, args.recv_port))
    server_thread.start()

   # Ensure the server thread is properly joined before exiting
    server_thread.join()

    # Configure OSC client
    client = udp_client.SimpleUDPClient(args.send_ip, args.send_port)

    # Query Ableton and create MIDI clip
    bpm, time_signature = query_ableton(client)
    create_midi_clip(client, bpm)