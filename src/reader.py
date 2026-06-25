#!/usr/bin/env python3

"""
A Python script to retrieve Event Data Recorder (EDR) data via CAN bus
according to the Chinese standard GB39732-2020.

EDR is a system that monitors, collects, and records vehicle and occupant
protection data before, during, and after a collision event. This script
reads 3 standardized data identifiers (DIDs 0xFA13, 0xFA14, 0xFA15) using
3 address types (11-bit functional, 11-bit physical, and 29-bit functional),
making 9 attempts in total by default. The --id-type option restricts this to a
single scheme (3 attempts), and --ecu-addr targets a single known responder
instead of sweeping every address. All attempts are executed sequentially
without early termination. Successful reads are saved as CSV files in the
'result' directory.

Usage:
    Connect a CAN device to the vehicle's OBD-II diagnostic connector,
    then run the script from the repository root:

    Windows (PowerShell):
        python src/reader.py <devicename> [options]

    Linux or macOS:
        python3 src/reader.py <devicename> [options]

    Arguments:
        devicename    CAN device name (e.g., COM9 on Windows, /dev/ttyACM0 on Linux)

    Options:
        -v, --verbose        Enable verbose output (prints all CAN frames)
        -t, --timeout SECS   Response timeout in seconds per DID read (default: 10)
        -i, --id-type TYPE   Addressing scheme: 11func, 11phys, or 29func
                             (default: try all three)
        -a, --ecu-addr ADDR  Known ECU physical address (0x-prefixed for hex,
                             else decimal; ex. 0x77) to target a single responder
                             in the functional schemes instead of sweeping

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
import re
import shutil
import time
import csv

import argparse
import can
import isotp
from udsoncan import Response
from udsoncan.services import ReadDataByIdentifier

_DEFAULT_TIMEOUT_S = 10.0
_TX_FUNC_11BIT = 0x7DF  # 11-bit OBD-II functional broadcast CAN ID per ISO 15765-4
_TESTER_ADDR = 0xF1     # ISO 15765-4: tester source address for 29-bit NormalFixed addressing
_OBD_FUNC_ADDR = 0x33   # ISO 15765-4: OBD-II functional broadcast address (excluded from rx)
_BROADCAST_29BIT = 0xFF # 29-bit UDS functional broadcast target address per ISO 15765-4

# Each addressing scheme returns a CAN acceptance filter, applied to the bus
# before that scheme is read (see the _build_* funcs). It keeps the Notifier
# from fanning background traffic out to every pre-allocated stack, which would
# stall the response. Root cause, mechanism and measurements: issue #46.

# Parameters from GB39732-2020
_EDR_DID_LIST = (0xFA13, 0xFA14, 0xFA15)
_TX_PHYS_11BIT = 0x7F1  # Tester physical TX ID (ECU receives on this ID)
_RX_PHYS_11BIT = 0x7F9  # Tester physical RX ID (ECU transmits on this ID); offset of 8 from TX

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


def _ecu_address(value):
    """Parse an ECU physical address (one byte) from the command line.

    Uses Python int() base-0 rules: a bare number is decimal (119) and a 0x
    prefix is hex (0x77). Scheme-specific range checks happen after parsing,
    once the addressing scheme is known (see _check_ecu_addr).
    """
    try:
        addr = int(value, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid ECU address '{value}': expected a byte like 0x77 (hex) or 119 (dec)"
        )
    if not 0x00 <= addr <= 0xFF:
        raise argparse.ArgumentTypeError(
            f"ECU address 0x{addr:X} out of range: expected 0x00-0xFF"
        )
    return addr


def _get_argparser():
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
    parser.add_argument(
        "-i", "--id-type",
        choices=list(_SCHEME_BUILDERS),
        default=None,
        help="addressing scheme to use: 11bits functional (11func), 11bits "
             "physical (11phys), or 29bits functional (29func); default tries "
             "all three"
    )
    parser.add_argument(
        "-a", "--ecu-addr",
        type=_ecu_address,
        default=None,
        metavar="ADDR",
        help="known ECU physical address (0x-prefixed for hex, else decimal; "
             "ex. 0x77) to target a single responder instead of sweeping every "
             "address; applies to the functional schemes, ignored for 11phys "
             "which already targets one ECU"
    )
    return parser


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


def _build_11func(bus, notifier, params, address=None):
    """11bits functional: emit-only tx_stack on 0x7DF + per-ECU rx_stacks (0x700-0x7FF).

    When ``address`` is given, only the single rx pair for that responder is built
    (response on 0x700|address, FC on 0x700|address-8) instead of the full sweep.
    """
    # rxid=0x700 is a placeholder to satisfy Address validation; no ECU transmits on it.
    tx_addr = isotp.Address(
        isotp.AddressingMode.Normal_11bits, txid=_TX_FUNC_11BIT, rxid=0x700
    )
    tx_stack = isotp.NotifierBasedCanStack(
        bus=bus, notifier=notifier, address=tx_addr, params=params
    )
    # Pre-allocate one rx stack per plausible per-ECU physical pair (DESIGN.md library-gap),
    # so the FF and the subsequent FC/CFs are received on the responder's own pair.
    # rxid = 0x700|addr is the ECU's response ID; txid = rxid-8 is where it expects
    # the tester's request/FC (the fixed 8-offset convention also used by the sweep).
    if address is not None:
        rxids = [0x700 | address]
    else:
        rxids = [0x700 + i + 8 for i in range(0x100 - 0x8)]
    rx_stacks = []
    for rxid in rxids:
        rx_addr = isotp.Address(
            isotp.AddressingMode.Normal_11bits, txid=rxid - 8, rxid=rxid
        )
        rx_stacks.append(isotp.NotifierBasedCanStack(
            bus=bus, notifier=notifier, address=rx_addr, params=params
        ))
    # Exact reply ID when targeting one ECU; otherwise the 0x700-0x7FF sweep
    # range, which is not diagnostic-reserved -- prefer --ecu-addr on a real bus.
    if address is not None:
        can_filters = [{"can_id": 0x700 | address, "can_mask": 0x7FF, "extended": False}]
    else:
        can_filters = [{"can_id": 0x700, "can_mask": 0x700, "extended": False}]
    return (tx_stack, rx_stacks, isotp.TargetAddressType.Functional,
            "11bits functional address", can_filters)


def _build_11phys(bus, notifier, params, address=None):
    """11bits physical: single symmetric stack used for both send and receive.

    ``address`` is accepted for a uniform builder signature but unused: physical
    addressing already targets one fixed responder pair (0x7F1/0x7F9).
    """
    addr = isotp.Address(
        isotp.AddressingMode.Normal_11bits, txid=_TX_PHYS_11BIT, rxid=_RX_PHYS_11BIT
    )
    stack = isotp.NotifierBasedCanStack(
        bus=bus, notifier=notifier, address=addr, params=params
    )
    # Physical addressing already uses one exact reply ID (0x7F9).
    can_filters = [{"can_id": _RX_PHYS_11BIT, "can_mask": 0x7FF, "extended": False}]
    return (stack, [stack], isotp.TargetAddressType.Physical,
            "11bits physical address", can_filters)


def _build_29bit(bus, notifier, params, address=None):
    """29bits NormalFixed: emit-only broadcast tx_stack + per-ECU rx_stacks.

    When ``address`` is given, only the single rx stack for that responder is
    built (replies on 0x18DAF1<address>) instead of sweeping every address.
    """
    tx_addr = isotp.Address(
        isotp.AddressingMode.NormalFixed_29bits,
        target_address=_BROADCAST_29BIT,
        source_address=_TESTER_ADDR,
    )
    tx_stack = isotp.NotifierBasedCanStack(
        bus=bus, notifier=notifier, address=tx_addr, params=params
    )
    # Cover the responder address(es). With a known address, build just that one;
    # otherwise sweep every plausible address (excluding the OBD functional broadcast).
    if address is not None:
        targets = [address]
    else:
        targets = [i for i in range(0xF0) if i != _OBD_FUNC_ADDR]
    rx_stacks = []
    for i in targets:
        rx_addr = isotp.Address(
            isotp.AddressingMode.NormalFixed_29bits,
            target_address=i,
            source_address=_TESTER_ADDR,
        )
        rx_stacks.append(isotp.NotifierBasedCanStack(
            bus=bus, notifier=notifier, address=rx_addr, params=params
        ))
    # Exact reply ID when targeting one ECU; otherwise the reserved 0x18DAF1xx range.
    if address is not None:
        can_filters = [{"can_id": 0x18DAF100 | address, "can_mask": 0x1FFFFFFF, "extended": True}]
    else:
        can_filters = [{"can_id": 0x18DAF100, "can_mask": 0x1FFFFF00, "extended": True}]
    return (tx_stack, rx_stacks, isotp.TargetAddressType.Functional,
            "29bits functional address", can_filters)


# Maps the --id-type choice to its scheme builder. Insertion order is also the
# order tried when no scheme is fixed (i.e. --id-type omitted).
_SCHEME_BUILDERS = {
    "11func": _build_11func,
    "11phys": _build_11phys,
    "29func": _build_29bit,
}


def _check_ecu_addr(args):
    """Validate --ecu-addr against the scheme(s) it will be used with.

    Returns an error message, or None if acceptable. 11-bit functional needs
    >= 0x08 so its response ID stays in 0x708-0x7FF; 29-bit allows 0x00-0xFF.
    With no fixed scheme (--id-type omitted) the address must satisfy both
    functional schemes, i.e. the 0x08-0xFF intersection. Physical addressing
    ignores the address.
    """
    if args.ecu_addr is None or args.id_type == "11phys":
        return None
    if args.id_type == "29func":
        lo, hi = 0x00, 0xFF
    else:  # "11func", or None meaning every functional scheme
        lo, hi = 0x08, 0xFF
    if not lo <= args.ecu_addr <= hi:
        scope = args.id_type or "the functional schemes"
        return (f"argument -a/--ecu-addr: 0x{args.ecu_addr:X} is out of range for "
                f"{scope}: expected 0x{lo:02X}-0x{hi:02X}")
    return None


def _read_all_dids(args, bus, notifier):
    """Read the EDR DIDs over the selected addressing scheme(s).

    Tries every scheme by default, or only --id-type when one is given.
    """
    if args.id_type is not None:
        builders = [_SCHEME_BUILDERS[args.id_type]]
    else:
        builders = list(_SCHEME_BUILDERS.values())
    for builder in builders:
        try:
            tx_stack, rx_stacks, addr_type, mode_label, can_filters = builder(
                bus, notifier, _ISOTP_PARAMS, args.ecu_addr
            )
            # Narrow the bus to this scheme's response IDs before receiving, so the
            # Notifier drops other traffic in recv() instead of fanning it out to
            # every stack (issue #46). Applied per scheme so e.g. the 29-bit read
            # also rejects all 11-bit traffic.
            try:
                bus.set_filters(can_filters)
            except Exception as err:
                print("Could not apply CAN acceptance filters; continuing unfiltered.")
                print(err)
            # The 11bits physical builder returns the same instance as tx_stack and
            # rx_stacks[0]; set() dedupes so start() / stop() run once per stack.
            # python-can-isotp's TransportLayer is designed for long-lived stacks:
            # construct once per scheme, reuse across DIDs, tear down at the end.
            all_stacks = {tx_stack, *rx_stacks}
            for s in all_stacks:
                s.start()
            try:
                for did in _EDR_DID_LIST:
                    payload = _read_did(
                        did, tx_stack, rx_stacks, addr_type, mode_label, args.timeout
                    )
                    _output_data(payload)
            finally:
                for s in all_stacks:
                    s.stop()
        except Exception as err:
            print(err)


def _read_did(did, tx_stack, rx_stacks, addr_type, mode_label,
              timeout=_DEFAULT_TIMEOUT_S) -> bytearray | None:
    """Read one data by identifier (DID) from the target ECU."""

    print("")
    print(f"Reading data id {hex(did)} with {mode_label}.")

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

    # Send request. Stacks are started/stopped by the caller (_read_all_dids)
    # once per addressing scheme, not per DID.
    tx_stack.send(request.get_payload(), addr_type)

    try:
        # Wait for response.
        # Non-blocking recv(): a sweep over hundreds of rx_stacks takes microseconds
        # when empty, so the user-supplied timeout is honored within ~1 ms granularity.
        # monotonic() is immune to wall-clock adjustments mid-wait.
        payload = None
        deadline = time.monotonic() + timeout
        while payload is None and time.monotonic() < deadline:
            for rx_stack in rx_stacks:
                received = rx_stack.recv(block=False)
                if received is None:
                    continue
                # Compare only the header portion of the received payload against
                # the expected positive-response bytes. The remainder is data.
                if received[:len(response)] == response.get_payload():
                    # Positive response
                    payload = received
                    break
                # Non-matching payload (e.g., negative response). See DESIGN.md.
            if payload is None:
                time.sleep(0.001)
    except Exception as err:
        print(err)
        return None

    if payload is not None:
        print(len(payload), "bytes of data received.")
    else:
        print("No data was received.")

    return payload


# `E=N*A+B` where A and B are optional. Examples found in format/*.csv:
#   E=N          -> (1, 0)
#   E=N-127      -> (1, -127)
#   E=N+2000     -> (1, 2000)
#   E=N*100      -> (100, 0)
#   E=N*0.1-300  -> (0.1, -300)
#   E=N*5-780    -> (5, -780)
# `×` is accepted as `*` for forward compatibility.
_LINEAR_FORMULA = re.compile(r'^E=N(?:[*×]([+-]?\d*\.?\d+))?(?:([+-])(\d+\.?\d*))?$')


def _parse_value_table(s: str) -> dict[int, str]:
    """Parse '0xFE:Invalid;0xFF:N/A' into {0xFE: 'Invalid', 0xFF: 'N/A'}.

    Returns an empty dict for 'N/A', 'Subsequent byte', empty strings, or any
    unparsable entry.
    """
    if s in ("N/A", "Subsequent byte", ""):
        return {}
    result: dict[int, str] = {}
    for entry in s.split(";"):
        entry = entry.strip()
        if ":" not in entry:
            continue
        key_str, label = entry.split(":", 1)
        try:
            key = int(key_str.strip(), 16)
        except ValueError:
            continue
        result[key] = label.strip()
    return result


def _parse_linear(expr: str) -> tuple[float, float]:
    """Parse 'E=A*N+B' style formulas into (scale, offset).

    'E=N' yields (1.0, 0.0). Raises ValueError if the expression does not match
    the linear pattern.
    """
    normalized = expr.replace(" ", "").replace("×", "*")
    m = _LINEAR_FORMULA.match(normalized)
    if not m:
        raise ValueError(f"Unrecognized linear formula: {expr}")
    scale_str, op, offset_str = m.groups()
    scale = float(scale_str) if scale_str else 1.0
    if offset_str:
        offset = float(offset_str)
        if op == '-':
            offset = -offset
    else:
        offset = 0.0
    return scale, offset


def _convert(raw: int, value_table: str, conversion: str) -> str:
    """Apply value_table or conversion to a (possibly multi-byte) raw value.

    Order: value_table match first, then conversion handlers ('Ascii',
    'Not defined', or a linear formula). Returns '' for 'Not defined' or any
    case the conversion cannot be parsed.
    """
    table = _parse_value_table(value_table)
    if raw in table:
        return table[raw]

    if conversion == "Ascii":
        # Printable ASCII char, else fall back to a two-digit hex form.
        if 0x20 <= raw < 0x7F:
            return chr(raw)
        return f"0x{raw:02X}"

    if conversion in ("Not defined", "Subsequent byte", ""):
        return ""

    try:
        scale, offset = _parse_linear(conversion)
    except ValueError:
        return ""

    return f"{scale * raw + offset:g}"


def _output_data(payload) -> None:
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

    # Read the input CSV file and write to the output file with the additional columns
    try:
        with (
            open(source_file, mode="r", encoding="utf-8", newline="") as infile,
            open(destination_file, mode="w", encoding="utf-8", newline="") as outfile
        ):
            reader = csv.reader(infile)
            writer = csv.writer(outfile)

            # Read header and add new column names
            header = next(reader)
            header.extend(["Raw value", "Physical value"])
            writer.writerow(header)

            # Buffer the data rows so we can look ahead to determine multi-byte
            # signal width (counting subsequent 'Subsequent byte' rows).
            data_rows = list(reader)

            for i, row in enumerate(data_rows):
                try:
                    no = int(row[0])  # Convert "No." column to integer
                except (ValueError, IndexError):
                    continue

                # "No." is 1-indexed in the CSV; subtract 1 to index into byte_array.
                if 1 <= no <= len(byte_array):
                    raw_byte = byte_array[no - 1]
                else:
                    raw_byte = "N/A"

                conversion = row[5] if len(row) > 5 else ""

                # Continuation rows: only the leading row of a multi-byte signal
                # carries the physical value; here we just echo the raw byte.
                if conversion == "Subsequent byte":
                    writer.writerow(row + [raw_byte, ""])
                    continue

                # Signal-start row: scan forward for continuation rows to determine width.
                width = 1
                while (i + width < len(data_rows)
                       and len(data_rows[i + width]) > 5
                       and data_rows[i + width][5] == "Subsequent byte"):
                    width += 1

                # Aggregate the bytes for this signal in big-endian (Motorola)
                # order. Skip the physical conversion if any byte falls outside
                # the received payload.
                physical: str = ""
                if isinstance(raw_byte, int) and no + width - 1 <= len(byte_array):
                    agg = 0
                    for k in range(width):
                        agg = (agg << 8) | byte_array[no - 1 + k]
                    value_table = row[4] if len(row) > 4 else ""
                    physical = _convert(agg, value_table, conversion)

                writer.writerow(row + [raw_byte, physical])

    except Exception as err:
        print(err)
        return


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
    argparser = _get_argparser()
    args = argparser.parse_args()
    addr_err = _check_ecu_addr(args)
    if addr_err:
        argparser.error(addr_err)

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
