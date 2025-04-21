import rtmidi

midiin = rtmidi.RtMidiIn()

controls_to_listen = [0, 1, 2, 3, 4, 8, 16]
channels_to_listen = [0, 1, 2]

def print_message(midi):
    if midi.isNoteOn():
        print('ON: ', midi.getMidiNoteName(midi.getNoteNumber()), midi.getVelocity())
    elif midi.isNoteOff():
        print('OFF:', midi.getMidiNoteName(midi.getNoteNumber()))
    elif midi.isController():
        print('CONTROLLER', midi.getControllerNumber(), midi.getControllerValue())

ports = range(midiin.getPortCount())
if ports:
    midi_index_to_choose = 0
    for i in ports:
        name = midiin.getPortName(i)
        print(name)
        if "volt" in name.lower():
            midi_index_to_choose = i

    print(f"Opening port {midi_index_to_choose}!") 
    midiin.openPort(0)
    while True:
        m = midiin.getMessage(250) # some timeout in ms
        if m:
            print(m)
            print_message(m)
        
            
else:
    print('NO MIDI INPUT PORTS!')