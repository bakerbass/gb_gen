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

## Installation
1. First, clone this repo. Be sure to add --recurse-submodules so [EC2-VAE](https://github.com/ZZWaang/icm-deep-music-generation) is cloned as well. 
2. Inside the path
```./icm-deep-music-generation/model_param```
there is a text file that contains a google drive link for the pretrained model. Download this and put it in the same directory as the text file.
3. Use the included environment_droplet.yml file to install other dependencies. This should work but I didn't test it. Note that I used python 3.11 for this project. The yml file contains extra dependencies that aren't really needed as I added and removed tools during the project.
4. Finally, you will need the dictionary of seeds. Because this was generated based on data from [DadaGP](https://github.com/dada-bots/dadaGP), I can't add it publicly here. 
However, you can request access via [this google drive link.](https://drive.google.com/file/d/14OQaGaP7bYZ1ypYk3v_24R4TBBXY_PVp/view?usp=sharing)
## Usage
Once everything is installed, be sure to change any directories that are in the main file to match your setup. You don't need the NeuralNote directory to actually be the correct location, it can be a local directory that you manually put midi files into. Or you could get creative and skip the watcher entirely.
