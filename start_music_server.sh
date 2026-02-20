#!/bin/bash

cd /home/kamil/Documents/music-server || exit 1

# activate venv
source .venv/bin/activate

# run app
python run.py
