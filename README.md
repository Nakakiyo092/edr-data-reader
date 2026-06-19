> [!WARNING]
> **Privacy and legal disclaimer.** Before using this tool, confirm that
> you have the right to retrieve EDR data from the target vehicle and
> that you will handle the retrieved data lawfully.
>
> - **Authorization.** Use this tool only on vehicles you own or are
>   explicitly authorized to analyze. Unauthorized retrieval may violate
>   privacy laws (e.g., GDPR, CCPA, Japan's APPI) and constitute
>   unauthorized access to a computer system in some jurisdictions.
> - **Personal data of the driver.** EDR data records driver behavior
>   and is the personal information of the driver, who is not
>   necessarily the vehicle owner (e.g., rentals, family or fleet
>   vehicles).
> - **Console output.** With `--verbose`, the script prints CAN frames
>   that may contain the same personal data; handle the console output
>   with the same care as the result CSV.
> - **Storage and deletion.** Store the retrieved data securely and
>   delete it when it is no longer needed. Cross-border transfer of the
>   data may be regulated.
> - **Third-party sharing.** Do not share the data with insurers, repair
>   shops, or any third party without the driver's explicit consent.
> - **Liability.** The author assumes no liability for misuse. The user
>   is responsible for compliance with applicable laws regarding the
>   retention, use, and disclosure of retrieved data.

# EDR Data Reader

A Python script to retrieve [Event Data Recorder (EDR)](https://en.wikipedia.org/wiki/Event_data_recorder) data via CAN bus according to the Chinese standard [GB39732-2020](https://std.samr.gov.cn/gb/search/gbDetailed?id=B7A9FA1FFC316818E05397BE0A0AB4AC).

According to the standard, EDR is defined as:

> Composed of one or more vehicle-mounted electronic modules, this device or system is equipped with the functions of monitoring, collecting, and recording data of vehicle and occupant protection systems before, during, and after a collision event.

(Machine-translated by Copilot)

## Requirements
- Python 3.13 or later
- See requirements.txt

## Usage
Connect your CAN device to the vehicle's diagnostic connector, then the script will tell you the usage by the command below:

Windows
* `python src\reader.py --help`

Linux or macOS
* `python3 src/reader.py --help`

If successful, the data will be stored in the `result` directory.

By default, the script uses a slcan device as a CAN interface.
You can use any [python-can](https://github.com/hardbyte/python-can) compatible interface by modifying the following line in the middle of `reader.py`.

```python
    bus = can.Bus(interface='slcan', channel=args.devicename, bitrate=500000)
```

The communication is configured so that the example in the standard can be recreated.
Modifications may be required to deal with specific ECUs.

To test this script without an actual ECU, there is a [mock script](https://github.com/Nakakiyo092/edr-ecu-mock) which simulates an ECU with EDR data.

## Design

See [DESIGN.md](./DESIGN.md) for the design philosophy and the rationale
behind specific implementation decisions.
