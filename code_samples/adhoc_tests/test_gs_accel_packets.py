#!/usr/bin/env python


import socket
import sys
import time

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

server_address = ('localhost', 9100)

# Packet grabbed from one generated by testGenerator (see react-groundstation/server/index.js, testGenerator(0x1003, payloads.accelerometer, "Flight Control");)
pkt = "\xd4\x06\x00\x00\x03\x10\x3c\x00\x07\x00\x00\x00\x9c\xff\x66\xfd\x00\x04\xe7\xfb\xa0\x41\xe7\xfb\xa0\x41\xe7\xfb\xa0\x41\x00\x00\x70\x42\x00\x00\x70\x42\x07\x00\x00\x00\x2e\xf8\x73\xec\x00\x10\x7d\x1f\x48\x43\x52\x58\x48\x43\x91\xad\x48\x43\x00\x00\xfa\x43\x00\x00\x16\x44\x7d\x4d"

# Packet from the virtual FCU
pkt = "\xb1\x00\x00\x00\x03\x10\x3c\x00\x04\x00\x00\x00\x41\x01\xb0\x01\x1f\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x41\x01\xb0\x01\x1f\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf5\x46"

message = pkt   # May need to do something to this...

for i in xrange(1000):
    sent = sock.sendto(message, server_address)
    time.sleep(0.1)
    print sent