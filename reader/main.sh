#!/bin/sh

# Set permission for USB port
sudo chmod 666 /dev/ttyACM0

# Read data and output to result directory
python3 reader/reader.py
