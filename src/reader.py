#!/usr/bin/env python3

"""
A Python script to retrieve Event Data Recorder (EDR) data via CAN bus
according to the Chinese standard GB39732-2020.

EDR is a system that monitors, collects, and records vehicle and occupant
protection data before, during, and after a collision event. This script
reads 3 standardized data identifiers (DIDs 0xFA13, 0xFA14, 0xFA15) using
3 address types (11-bit functional, 11-bit physical, and 29-bit), making
9 attempts in total. All attempts are executed sequentially without early
termination. Successful reads are saved as CSV files in the 'result' directory.

Usage:
    Connect a CAN device to the vehicle's OBD-II diagnostic connector,
    then run the script from the repository root:

    Windows:
        python src\reader.py <devicename> [options]

    Linux or macOS:
        python3 src/reader.py <devicename> [options]

    Arguments:
        devicename    CAN device name (e.g., COM9 on Windows, /dev/ttyACM0 on Linux)

    Options:
        -v, --verbose       Enable verbose output (prints all CAN frames)
        -t, --timeout SECS  Response timeout in seconds per DID read (default: 10)

    For full help:
        python src/reader.py --help

    Output:
        Results are saved to the 'result' directory as CSV files
        (did_fa13.csv, did_fa14.csv, did_fa15.csv) with raw byte values
        appended to each row.

License:
    MIT License.
    See the accompanying LICENSE file for full terms.
"""

import os
import shutil
import time
import csv

import argparse
import can
import isotp
from udsoncan import Response
from udsoncan.services import ReadDataByIdentifier

_DEFAULT_TIMEOUT_S = 10.0
_TESTER_ADDR = 0xF1  # ISO 15765-4: tester source address for 29-bit NormalFixed addressing
_OBD_FUNC_ADDR = 0x33  # ISO 15765-4: OBD-II functional broadcast address (excluded from rx)

# Parameters from GB39732-2020
_EDR_DID_LIST = (0xFA13, 0xFA14, 0xFA15)
_TX_PHYS_11BIT = 0x7F1  # Tester physical TX ID (ECU receives on this ID)
_RX_PHYS_11BIT = 0x7F9  # Tester physical RX ID (ECU transmits on this ID); offset of 8 from TX
_TX_FUNC_11BIT = 0x7DF  # 11-bit OBD-II functional broadcast CAN ID per ISO 15765-4
_BROADCAST_29BIT = 0xFF  # 29-bit UDS functional broadcast target address per ISO 15765-4

_ISOTP_PARAMS = {
    # Will request the sender to wait 0ms between consecutive frame.
    # 0-127ms or 100-900ns with values from 0xF1-0xF9.
    'stmin': 0,
    # Request the sender to send all consecutives frames
    # without waiting a new flow control message.
    'blocksize': 0,
    # Number of wait frame allowed before triggering an error.
    'wftmax': 0,
    # Link layer (CAN layer) works with 8 byte payload (CAN 2.0).
    'tx_data_length': 8,
    # Minimum length of CAN messages. Messages are padded to meet this length.
    'tx_data_min_length': 8,
    # Will pad all transmitted CAN messages with byte 0x00.
    'tx_padding': 0,
    # Triggers a timeout if a flow control is awaited for more than 1000 milliseconds.
    'rx_flowcontrol_timeout': 1000,
    # Triggers a timeout if a consecutive frame is awaited for more than 1000 milliseconds.
    'rx_consecutive_frame_timeout': 1000,
    # When sending, respect the stmin requirement of the receiver.
    # Could be set to a float value in seconds.
    'override_receiver_stmin': None,
    # Limit the size of receive frame.
    'max_frame_size': 4095,
    # Does not set the can_fd flag on the output CAN messages.
    'can_fd': False,
    # Does not set the bitrate_switch flag on the output CAN messages.
    'bitrate_switch': False,
    # Disable the rate limiter.
    'rate_limit_enable': False,
    # Ignored when rate_limit_enable=False. Sets the max bitrate when rate_limit_enable=True.
    'rate_limit_max_bitrate': 1000000,
    # Ignored when rate_limit_enable=False.
    # Sets the averaging window size for bitrate calculation when rate_limit_enable=True.
    'rate_limit_window_size': 0.2,
    # Does not use the listen_mode which prevent transmission.
    'listen_mode': False,
}


def get_argparser():
    """Get the command line argument parser."""

    parser = argparse.ArgumentParser(
        description="Retrieve EDR data via CAN bus. Press [CTRL] + 'c' to quit."
    )
    parser.add_argument(
        "devicename",
        type=str,
        help="device name like COM9 or /dev/ttyACM0 (required)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="enable verbose output"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=_DEFAULT_TIMEOUT_S,
        help="response timeout in seconds per DID read (default: 10)"
    )
    return parser


def read_did(did, bus, notifier, tx_addr, rx_addrs, addr_type, isotp_params,
             timeout=_DEFAULT_TIMEOUT_S) -> bytearray | None:
    """Read one data by identifier (DID) from the target ECU."""

    print("")
    if tx_addr.is_tx_29bits():
        print("Reading data id", hex(did), "with 29bits address.")
    elif addr_type == isotp.TargetAddressType.Functional:
        print("Reading data id", hex(did), "with 11bits functional address.")
    else:
        print("Reading data id", hex(did), "with 11bits physical address.")

    # Setup ISOTP stacks
    tx_stack = isotp.NotifierBasedCanStack(
        bus=bus,
        notifier=notifier,
        address=tx_addr,
        params=isotp_params
    )
    rx_stacks = []
    # In Physical addressing, request and response share the same address pair (tx_addr),
    # so rx_addrs can be void. tx_stack is included in rx_stacks to receive the ECU's response.
    rx_stacks.append(tx_stack)
    for rx_addr in rx_addrs:
        rx_stack = isotp.NotifierBasedCanStack(
            bus=bus, notifier=notifier,
            address=rx_addr,
            params=isotp_params
        )
        rx_stacks.append(rx_stack)

    # Build the UDS ReadDataByIdentifier request payload.
    # didconfig maps DID to a string codec; udsoncan requires it even though we
    # discard the decoded value and work with raw bytes from the payload directly.
    request = ReadDataByIdentifier.make_request(didlist=[did], didconfig={'default': 's'})

    # Build the expected positive-response header for filtering.
    # A positive response for ReadDataByIdentifier (service 0x22) starts with:
    #   0x62 (service ID | 0x40) followed by the 2-byte DID (big-endian).
    # Any received payload that does not start with this header is not our answer.
    response = Response(
        service=ReadDataByIdentifier,
        code=Response.Code.PositiveResponse,
        data=bytes([(did >> 8) & 0xFF, did & 0xFF])  # DID encoded as big-endian 2-byte
    )

    # Start stacks
    for rx_stack in rx_stacks:
        rx_stack.start()

    # Send request
    tx_stack.send(request.get_payload(), addr_type)

    try:
        # Wait for response
        waiting = True
        start_time = time.time()
        while waiting:
            # Response timeout
            if time.time() - start_time > timeout:
                payload = None
                break

            # Check response for all stacks
            for rx_stack in rx_stacks:
                # Use a short blocking recv (10 ms) so we yield to the notifier
                # thread between iterations rather than spinning at 100 % CPU,
                # while still cycling through all stacks frequently enough to
                # catch the first available response without noticeable delay.
                payload = rx_stack.recv(block=True, timeout=0.01)
                if payload is not None:
                    # Compare only the header portion of the received payload against
                    # the expected positive-response bytes. The remainder is data.
                    if payload[:len(response)] == response.get_payload():
                        # Positive response
                        waiting = False
                        break
                    else:
                        # No Negative response handling. See the DESIGN.md.
                        pass

    except Exception as err:
        print(err)
        return None

    # Stop stacks
    for rx_stack in rx_stacks:
        rx_stack.stop()

    if payload is not None:
        print(len(payload), "bytes of data received.")
    else:
        print("No data was received.")

    return payload


def output_data(payload) -> None:
    """Output the data to a CSV file according to the format defined in the 'format' folder."""

    # Get target did from payload
    if payload is None:
        print("No data to output.")
        return
    if len(payload) < 3:
        print("The payload is too short.")
        return

    did = f"{payload[1]:02x}{payload[2]:02x}"

    # File paths for source and destination
    source_file = "format/did_" + did + ".csv"
    destination_file = "result/did_" + did + ".csv"

    # Copy the file
    try:
        os.makedirs("result", exist_ok=True)
        shutil.copy(source_file, destination_file)
    except FileNotFoundError:
        print(f"The source file '{source_file}' does not exist.")
        print(f"The output file '{destination_file}' was not created from '{source_file}'.")
        return
    except PermissionError:
        print("You do not have the necessary permissions to read or write the file.")
        print(f"The output file '{destination_file}' was not created from '{source_file}'.")
        return
    except Exception as err:
        print(err)
        return

    # Strip the 3-byte UDS response header (service ID 0x62 + 2-byte DID) to get
    # the raw data bytes that map to the CSV rows.
    byte_array = payload[3:]

    # Read the input CSV file and write to the output file with the additional column
    try:
        with (
            open(source_file, mode="r", encoding="utf-8", newline="") as infile,
            open(destination_file, mode="w", encoding="utf-8", newline="") as outfile
        ):
            reader = csv.reader(infile)
            writer = csv.writer(outfile)

            # Read header and add new column name
            header = next(reader)
            header.append("Raw value")  # Add a new column named 'Raw value'
            writer.writerow(header)

            # Process rows
            for row in reader:
                try:
                    no = int(row[0])  # Convert "No." column to integer
                except (ValueError, IndexError):
                    continue
                # "No." is 1-indexed in the CSV; subtract 1 to index into byte_array.
                if 1 <= no <= len(byte_array):
                    row.append(byte_array[no - 1])
                else:
                    row.append("N/A")
                writer.writerow(row)

    except Exception as err:
        print(err)
        return


def _create_bus(args):
    """Create and return a CAN bus, or None if initialization fails."""
    try:
        if args.devicename == "virtual":
            return can.Bus('test', interface='virtual')
        elif args.devicename == "vector":
            return can.Bus(interface='vector', channel=0, bitrate=500000, app_name="Python-CAN")
        else:
            # 500 kbps is the standard high-speed CAN bitrate for OBD-II (ISO 15765-4).
            return can.Bus(interface='slcan', channel=args.devicename, bitrate=500000)
    except can.CanInitializationError as err:
        print("Could not access CAN network.")
        print("The program is aborting.")
        print(err)
        if args.devicename not in ("virtual", "vector"):
            print("Possible causes:")
            print(f"  - Wrong device name: check '{args.devicename}' is correct")
            print( "  - Device not powered: check the device is powered on")
            print( "  - Device not connected: check the device is properly connected")
            print( "  - Wrong firmware: check the device has correct firmware")
            print( "  - Permission denied (Linux): try 'sudo usermod -aG dialout $USER' and re-login")
            print(f"    or 'sudo chmod 666 {args.devicename}'")
        return None
    except Exception as err:
        print("Could not access CAN network.")
        print("The program is aborting.")
        print(err)
        return None


def _read_all_dids(args, bus, notifier):
    """Read all EDR DIDs via 11bits functional, 11bits physical, and 29bits addresses."""

    # Abbreviated name
    func = isotp.TargetAddressType.Functional
    phys = isotp.TargetAddressType.Physical

    # Read with 11bits functional address (See GB39732-2020 for the address values)
    # rxid=0x700 is a dummy; the functional broadcast (txid=0x7DF) does not listen on a fixed ID.
    tx_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=_TX_FUNC_11BIT, rxid=0x700)
    rx_addrs = []
    # Pre-allocate one receive stack per plausible physical CAN ID pair in the 0x700–0x7FF range.
    # GB39732-2020 physical pairs follow the convention: ECU TX = tester TX + 8
    # (e.g., _TX_PHYS_11BIT=0x7F1, _RX_PHYS_11BIT=0x7F9, difference=8).
    # The upper bound 0x100-0x8 (=248) keeps rxid = 0x700+i+8 within 0x7FF (11-bit max).
    for i in range(0x100 - 0x8):
        rx_addrs.append(isotp.Address(
            isotp.AddressingMode.Normal_11bits, txid=0x700 + i, rxid=0x700 + i + 8))

    try:
        for did in _EDR_DID_LIST:
            payload = read_did(did, bus, notifier, tx_addr, rx_addrs, func, _ISOTP_PARAMS, args.timeout)
            output_data(payload)
    except Exception as err:
        print(err)

    # Read with 11bits physical address (See GB39732-2020 for the address values)
    tx_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=_TX_PHYS_11BIT, rxid=_RX_PHYS_11BIT)
    rx_addrs = []

    try:
        for did in _EDR_DID_LIST:
            payload = read_did(did, bus, notifier, tx_addr, rx_addrs, phys, _ISOTP_PARAMS, args.timeout)
            output_data(payload)
    except Exception as err:
        print(err)

    # Read with 29bits address (See GB39732-2020 for the address values)
    tx_addr = isotp.Address(
        isotp.AddressingMode.NormalFixed_29bits,
        target_address=_BROADCAST_29BIT,
        source_address=_TESTER_ADDR
    )
    rx_addrs = []
    # In NormalFixed 29-bit addressing the CAN arbitration ID encodes both target and source
    # addresses. The tester sends Flow Control back to each ECU using the ECU's own source
    # address as the target_address. Addresses 0xF0–0xFF are reserved for testers and
    # functional use per ISO 15765-4, so only 0x00–0xEF (range 0xF0 = 240 values) are valid
    # ECU source addresses. _OBD_FUNC_ADDR (0x33) is a functional broadcast address and must
    # be excluded to avoid interfering with OBD-II traffic.
    for i in range(0xF0):
        if i != _OBD_FUNC_ADDR:
            rx_addrs.append(isotp.Address(
                isotp.AddressingMode.NormalFixed_29bits,
                target_address=i,
                source_address=_TESTER_ADDR
            ))

    try:
        for did in _EDR_DID_LIST:
            payload = read_did(did, bus, notifier, tx_addr, rx_addrs, func, _ISOTP_PARAMS, args.timeout)
            output_data(payload)
    except Exception as err:
        print(err)


def _copy_readme():
    """Copy the README file from the format folder to the result folder."""
    try:
        shutil.copy("format/README.md", "result/README.md")
    except FileNotFoundError:
        print("The source file format/README.md does not exist.")
        print("The file format/README.md was not copied to result/README.md.")
    except PermissionError:
        print("You do not have the necessary permissions to read or write a file.")
        print("The file format/README.md was not copied to result/README.md.")
    except Exception as err:
        print(err)


def main():
    """Main process."""

    # Parse command line arguments
    argparser = get_argparser()
    args = argparser.parse_args()

    # Setup and start a CAN bus
    bus = _create_bus(args)
    if bus is None:
        return

    if args.verbose:
        # Setup a debug listener that print all CAN frames
        notifier = can.Notifier(bus, [can.Printer()])
    else:
        notifier = can.Notifier(bus, [])

    try:
        # Read all EDR DIDs
        _read_all_dids(args, bus, notifier)
    finally:
        # Shutdown the CAN bus
        notifier.stop()
        bus.shutdown()

    # Copy the README file
    _copy_readme()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
