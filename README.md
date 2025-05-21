# EDR Data Reader
A Python script to retreive [Event Data Recorder (EDR)](https://en.wikipedia.org/wiki/Event_data_recorder) data via CAN bus according to the Chinese standard [GB39732-2020](https://std.samr.gov.cn/gb/search/gbDetailed?id=B7A9FA1FFC316818E05397BE0A0AB4AC).

According to the standard, EDR is defined as:

> Composed of one or more vehicle-mounted electronic modules, this device or system is equipped with the functions of monitoring, collecting, and recording data of vehicle and occupant protection systems before, during, and after a collision event.

(Machine-translated by Copilot)

## Requirements
- Python 3
- See requirements.txt

## Usage
By default, the script uses the slcan device `COM9` as a CAN interface.
You can use any [python-can](https://github.com/hardbyte/python-can) compatible interface by modifying the following line in the middle of `reader.py`.

```
    bus = can.Bus(interface='slcan', channel='COM9', bitrate=500000)
```

The communication is configured so that the example in the standard can be recreated.
Modifications may be required to deal with specific ECUs.

Connect your CAN device to the vehicle's diagnostic connector, then the script will run by the command below:

Windows
* `python .\reader\reader.py`

Linux or macOS
* `python3 ./reader/reader.py`

If successful, the data will be stored in the `result` directory.

