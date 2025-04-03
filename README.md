# EDR Data Reader
Python script to retreive [Event Data Recorder (EDR)](https://en.wikipedia.org/wiki/Event_data_recorder) data via CAN bus according to the Chinese standard GB39732-2020.

According to the standard, EDR is defined as:

> Composed of one or more vehicle-mounted electronic modules, this device or system is equipped with the functions of monitoring, collecting, and recording data of vehicle and occupant protection systems before, during, and after a collision event.

(Machine-translated by Copilot)

## Requirements
- Python 3
- See requirements.txt

## Usage
By default, the script uses the slcan device as a CAN interface.
You can use any [python-can](https://github.com/hardbyte/python-can) combatible interface by modifying the script.

The communication is configured so that the example in the standard can be recreated.
Some modifications may be required to deal with specific ECUs.

If successful, the data will be stored in the `result` directory.
