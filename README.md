# Note 2 Anticipation (Name in progress)
This repo contains all of the tools used to generate melodies and chord progressions for Georgia Tech's GuitarBot, a guitar playing robot.

# How to use

2025/4/11

To put it in the simplest terms, main.py contains code to do the following:

1. Watch a directory for a new midi file
2. Extract the chords from this midi file
3. Generate a crude melody for this chord progression
4. Generate a melody based on this crude melody using EC2-VAE
5. Send this melody to GuitarBot over UDP messages

This code's documentation is inconsistent but I will do my best to help get anybody up and running with this functionality in mind. 