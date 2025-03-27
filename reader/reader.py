#!/usr/bin/env python3

import can
import isotp
from udsoncan import Request, Response
from udsoncan.services import ReadDataByIdentifier

try:
    #bus = can.Bus(interface='slcan', channel='/dev/ttyACM0', bitrate=500000)
    bus = can.Bus(interface='slcan', channel='COM8', bitrate=500000)
    #bus = can.Bus(interface='vector', channel=0, bitrate=500000, app_name="Python-CAN")
    #bus = can.Bus('test', interface='virtual')
except Exception as err:
    print(err)
    exit()

# Isotp parameters
isotp_params = {
 'stmin': 0,                             # Will request the sender to wait 32ms between consecutive frame. 0-127ms or 100-900ns with values from 0xF1-0xF9
 'blocksize': 0,                         # Request the sender to send 8 consecutives frames before sending a new flow control message
 'wftmax': 0,                            # Number of wait frame allowed before triggering an error
 'tx_data_length': 8,                    # Link layer (CAN layer) works with 8 byte payload (CAN 2.0)
 # Minimum length of CAN messages. When different from None, messages are padded to meet this length. Works with CAN 2.0 and CAN FD.
 'tx_data_min_length': 8,
 'tx_padding': 0,                        # Will pad all transmitted CAN messages with byte 0x00.
 'rx_flowcontrol_timeout': 1000,         # Triggers a timeout if a flow control is awaited for more than 1000 milliseconds
 'rx_consecutive_frame_timeout': 1000,   # Triggers a timeout if a consecutive frame is awaited for more than 1000 milliseconds
 #'squash_stmin_requirement': False,      # When sending, respect the stmin requirement of the receiver. If set to True, go as fast as possible.
 'max_frame_size': 4095,                 # Limit the size of receive frame.
 'can_fd': False,                        # Does not set the can_fd flag on the output CAN messages
 'bitrate_switch': False,                # Does not set the bitrate_switch flag on the output CAN messages
 'rate_limit_enable': False,             # Disable the rate limiter
 'rate_limit_max_bitrate': 1000000,      # Ignored when rate_limit_enable=False. Sets the max bitrate when rate_limit_enable=True
 'rate_limit_window_size': 0.2,          # Ignored when rate_limit_enable=False. Sets the averaging window size for bitrate calculation when rate_limit_enable=True
 'listen_mode': False,                   # Does not use the listen_mode which prevent transmission.
}

notifier = can.Notifier(bus, [can.Printer()])                                       # Add a debug listener that print all messages
rx_addr = isotp.Address(isotp.AddressingMode.NormalFixed_29bits, target_address=0x77, source_address=0xF1)
tx_addr = isotp.Address(isotp.AddressingMode.NormalFixed_29bits, target_address=0xFF, source_address=0xF1)
rx_stack = isotp.NotifierBasedCanStack(bus=bus, notifier=notifier, address=rx_addr, params=isotp_params)  # Network/Transport layer (IsoTP protocol). Register a new listenenr
tx_stack = isotp.NotifierBasedCanStack(bus=bus, notifier=notifier, address=tx_addr, params=isotp_params)  # Network/Transport layer (IsoTP protocol). Register a new listenenr

request = ReadDataByIdentifier.make_request(didlist=[0xFA13], didconfig={'default':'s'})
response = Response(service=ReadDataByIdentifier, code=Response.Code.PositiveResponse, data=bytes([0xFA, 0x13]))

rx_stack.start()
tx_stack.start()

tx_stack.send(request.get_payload(), isotp.TargetAddressType.Functional)

try:
    while True:
        payload = rx_stack.recv(block=True, timeout=1)
        if payload is not None:
            if payload[:3] == response.get_payload()[:3]:
                print("Respoonse received!")
                print(payload)

except Exception as err:
    print(err)
    exit()

rx_stack.stop()
tx_stack.stop()

bus.shutdown()
