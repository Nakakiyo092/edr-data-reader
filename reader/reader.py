#!/usr/bin/env python3

import time
import isotp
import can

# Isotp parameters
isotp_params = {
 'stmin': 0,
 'blocksize': 0,
 'tx_data_length': 8,
 'tx_data_min_length': 8,
 'tx_padding': 0,
 'rx_flowcontrol_timeout': 1000,
 'rx_consecutive_frame_timeout': 1000,
 'max_frame_size': 4095,
 'can_fd': False,
 'bitrate_switch': False,
}

#バス接続
try:
    bus = can.Bus(interface='slcan', channel='/dev/ttyACM0', bitrate=500000)
except Exception as err:
    print(err)
    exit()

tx_addr = isotp.Address(isotp.AddressingMode.NormalFixed_29bits, target_address=0xFF, source_address=0xF1)

#stack = isotp.CanStack(bus, address=tx_addr, params=isotp_params)
notifier = can.Notifier(bus, [can.Printer()])
stack = isotp.NotifierBasedCanStack(bus=bus, notifier=notifier, address=tx_addr, params=isotp_params)

#送信データ11byte
stack.start()
stack.send(b'\x22\xFA\x13')

time.sleep(5)

stack.stop()
bus.shutdown()

