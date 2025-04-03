# EDR Data Reader
Python script to retreive EDR data via CAN bus according to the Chinese standard GB39732-2020.

## Requirements
- Python 3
- See requirements.txt

## Usage
By default, the script uses the slcan device as a CAN interface.
You can use any python-can combatible interface by modifying the script.

The communication is configured so that the example in the standard can be recreated.
Some modifications may be required to deal with specific ECUs.
