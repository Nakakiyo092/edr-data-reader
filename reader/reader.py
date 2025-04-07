#!/usr/bin/env python3

import os
import shutil
import time
import csv

import can
import isotp
from udsoncan import Request, Response
from udsoncan.services import ReadDataByIdentifier

def read_did(did, bus, notifier, tx_addr, rx_addrs, addr_type, isotp_params) -> bytearray:

    print("")
    if tx_addr.is_tx_29bits():
        print("Reading data id", hex(did), "with 29bits address.")
    elif addr_type == isotp.TargetAddressType.Functional:
        print("Reading data id", hex(did), "with 11bits functional address.")
    else:
        print("Reading data id", hex(did), "with 11bits physical address.")

    # Setup ISOTP stacks
    tx_stack = isotp.NotifierBasedCanStack(bus=bus, notifier=notifier, address=tx_addr, params=isotp_params)
    rx_stacks = []
    rx_stacks.append(tx_stack)  # Add tx_stack itself to support Physical addressing
    for rx_addr in rx_addrs:
        rx_stack = isotp.NotifierBasedCanStack(bus=bus, notifier=notifier, address=rx_addr, params=isotp_params)
        rx_stacks.append(rx_stack)

    # Request message
    request = ReadDataByIdentifier.make_request(didlist=[did], didconfig={'default':'s'})

    # Response message (positive/pending)
    response = Response(service=ReadDataByIdentifier, code=Response.Code.PositiveResponse, data=bytes([(did>>8)&0xFF,did&0xFF]))
    pend_response = Response(service=ReadDataByIdentifier, code=Response.Code.RequestCorrectlyReceived_ResponsePending)

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
            if time.time() - start_time > 5:
                print("Time out.")
                payload = None
                waiting = False
                break

            # Check response for all stacks
            for rx_stack in rx_stacks:
                payload = rx_stack.recv(block=True, timeout=0.01)
                if payload is not None:
                    # Response pending
                    if payload == pend_response.get_payload():
                        pass

                    # Positive response
                    if payload[:len(response)] == response.get_payload():
                        waiting = False
                        break

    except Exception as err:
        print(err)
        return None

    # Stop stacks
    for rx_stack in rx_stacks:
        rx_stack.stop()

    if payload is not None:
        print(len(payload), " bytes of data received.")
    else:
        print("No data was received.")

    return payload


def output_data(payload) -> bytearray:
    # Get target did from payload
    if payload is None:
        print(f"No data to output.")
        return
    if len(payload) < 3:
        print(f"The payload is too short.")
    else:
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
        return
    except PermissionError:
        print("You do not have the necessary permissions to read or write the file.")
        return
    except Exception as err:
        print(err)
        return

    # Make data
    byte_array = payload[3:]

    # Read the input CSV file and write to the output file with the additional column
    try:
        with open(source_file, mode="r", encoding="utf-8") as infile, open(destination_file, mode="w", encoding="utf-8", newline="") as outfile:
            reader = csv.reader(infile)
            writer = csv.writer(outfile)
            
            # Read header and add new column name
            header = next(reader)
            header.append("Raw value")  # Add a new column named 'Raw value'
            writer.writerow(header)
            
            # Process rows
            for row in reader:
                no = int(row[0])  # Convert No column to integer
                if 1 <= no <= len(byte_array):  # Check if No is within the range
                    row.append(byte_array[no - 1])  # Add corresponding byte array value
                else:
                    row.append("N/A")  # Handle cases where No is out of range
                writer.writerow(row)
        
    except FileNotFoundError:
        print(f"The file '{source_file}' or '{destination_file}' does not exist.")
        return
    except Exception as err:
        print(err)
        return


### Main process ###

# Setup and start a CAN bus
try:
    #bus = can.Bus(interface='slcan', channel='/dev/ttyACM0', bitrate=500000)
    bus = can.Bus(interface='slcan', channel='COM9', bitrate=500000)
    #bus = can.Bus(interface='vector', channel=0, bitrate=500000, app_name="Python-CAN")
    #bus = can.Bus('test', interface='virtual')
except Exception as err:
    print(err)
    exit()

# Setup a debug listener that print all messages
#notifier = can.Notifier(bus, [can.Printer()])
notifier = can.Notifier(bus, [])


# Isotp parameters
isotp_params = {
 'stmin': 0,                             # Will request the sender to wait 0ms between consecutive frame. 0-127ms or 100-900ns with values from 0xF1-0xF9
 'blocksize': 0,                         # Request the sender to send all consecutives frames without waiting a new flow control message
 'wftmax': 0,                            # Number of wait frame allowed before triggering an error
 'tx_data_length': 8,                    # Link layer (CAN layer) works with 8 byte payload (CAN 2.0)
 'tx_data_min_length': 8,                # Minimum length of CAN messages. Messages are padded to meet this length.
 'tx_padding': 0,                        # Will pad all transmitted CAN messages with byte 0x00.
 'rx_flowcontrol_timeout': 1000,         # Triggers a timeout if a flow control is awaited for more than 1000 milliseconds
 'rx_consecutive_frame_timeout': 1000,   # Triggers a timeout if a consecutive frame is awaited for more than 1000 milliseconds
 'override_receiver_stmin': None,        # When set, this value will override the receiver stmin requirement. 
 'max_frame_size': 4095,                 # Limit the size of receive frame.
 'can_fd': False,                        # Does not set the can_fd flag on the output CAN messages
 'bitrate_switch': False,                # Does not set the bitrate_switch flag on the output CAN messages
 'rate_limit_enable': False,             # Disable the rate limiter
 'rate_limit_max_bitrate': 1000000,      # Ignored when rate_limit_enable=False. Sets the max bitrate when rate_limit_enable=True
 'rate_limit_window_size': 0.2,          # Ignored when rate_limit_enable=False. Sets the averaging window size for bitrate calculation when rate_limit_enable=True
 'listen_mode': False,                   # Does not use the listen_mode which prevent transmission.
}


# Read with 11bits functional address
tx_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=0x7DF, rxid=0x700)
rx_addrs = []
for i in range(0x100 - 0x8):
    rx_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=0x700+i, rxid=0x700+i+8)
    rx_addrs.append(rx_addr)

try:
    payload = read_did(0xfa13, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Functional, isotp_params)
    output_data(payload)
    payload = read_did(0xfa14, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Functional, isotp_params)
    output_data(payload)
    payload = read_did(0xfa15, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Functional, isotp_params)
    output_data(payload)
except Exception as err:
    print(err)


# Read with 11bits physical address
tx_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=0x7F1, rxid=0x7F9)
rx_addrs = []

try:
    payload = read_did(0xfa13, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Physical, isotp_params)
    output_data(payload)
    payload = read_did(0xfa14, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Physical, isotp_params)
    output_data(payload)
    payload = read_did(0xfa15, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Physical, isotp_params)
    output_data(payload)
except Exception as err:
    print(err)


# Read with 29bits address
tx_addr = isotp.Address(isotp.AddressingMode.NormalFixed_29bits, target_address=0xFF, source_address=0xF1)
rx_addrs = []
for i in range(0x100):
    if i != 0x33:
        rx_addr = isotp.Address(isotp.AddressingMode.NormalFixed_29bits, target_address=i, source_address=0xF1)
        rx_addrs.append(rx_addr)

try:
    payload = read_did(0xfa13, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Functional, isotp_params)
    output_data(payload)
    payload = read_did(0xfa14, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Functional, isotp_params)
    output_data(payload)
    payload = read_did(0xfa15, bus, notifier, tx_addr, rx_addrs, isotp.TargetAddressType.Functional, isotp_params)
    output_data(payload)
except Exception as err:
    print(err)


# Copy the README file
try:
    shutil.copy("format/README.md", "result/README.md")
except FileNotFoundError:
    print(f"The source file format/README.md does not exist.")
except PermissionError:
    print("You do not have the necessary permissions to read or write the file.")
except Exception as err:
    print(err)


# Shutdown the CAN bus
notifier.stop()
bus.shutdown()
