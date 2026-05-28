import socket
import os
import struct
from cryptography.fernet import Fernet
import pytun
import threading

HOST = ''
PORT = 8888


def _ones_complement_sum(data):
    if len(data) % 2:
        data += b'\x00'
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return (~s) & 0xffff


def fix_checksums(pkt):
    # Recompute IP + L4 checksums. Kernel hands TUN packets with CHECKSUM_UNNECESSARY
    # state after NAT, leaving the on-wire bytes with a pre-NAT checksum the remote
    # kernel rejects. We recompute so the client sees a valid packet.
    if len(pkt) < 20 or (pkt[0] >> 4) != 4:
        return pkt
    ihl = (pkt[0] & 0x0f) * 4
    total_len = struct.unpack('!H', pkt[2:4])[0]
    if len(pkt) < total_len or total_len < ihl:
        return pkt
    proto = pkt[9]
    buf = bytearray(pkt)

    buf[10] = 0
    buf[11] = 0
    ip_cksum = _ones_complement_sum(bytes(buf[:ihl]))
    buf[10] = (ip_cksum >> 8) & 0xff
    buf[11] = ip_cksum & 0xff

    l4_len = total_len - ihl
    pseudo = bytes(buf[12:20]) + bytes([0, proto]) + struct.pack('!H', l4_len)

    if proto == 6 and l4_len >= 20:  # TCP
        buf[ihl + 16] = 0
        buf[ihl + 17] = 0
        c = _ones_complement_sum(pseudo + bytes(buf[ihl:ihl + l4_len]))
        buf[ihl + 16] = (c >> 8) & 0xff
        buf[ihl + 17] = c & 0xff
    elif proto == 17 and l4_len >= 8:  # UDP
        buf[ihl + 6] = 0
        buf[ihl + 7] = 0
        c = _ones_complement_sum(pseudo + bytes(buf[ihl:ihl + l4_len]))
        if c == 0:
            c = 0xffff
        buf[ihl + 6] = (c >> 8) & 0xff
        buf[ihl + 7] = c & 0xff
    elif proto == 1 and l4_len >= 8:  # ICMP
        buf[ihl + 2] = 0
        buf[ihl + 3] = 0
        c = _ones_complement_sum(bytes(buf[ihl:ihl + l4_len]))
        buf[ihl + 2] = (c >> 8) & 0xff
        buf[ihl + 3] = c & 0xff

    return bytes(buf)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sock.bind((HOST, PORT))

key = os.environ.get('VPN_KEY').encode()
f = Fernet(key)
tun = pytun.TunTapDevice(name='tun0', flags=pytun.IFF_TUN | pytun.IFF_NO_PI)
tun.addr = '10.0.0.1'
tun.netmask = '255.255.255.0'
tun.mtu = 1500
tun.up()

client_addr = None

def tun_to_client():
    while True:
        if client_addr is not None:
            p = tun.read(tun.mtu)
            p = fix_checksums(p)
            print(f"Read from TUN, sending to client", flush=True)
            encrypted = f.encrypt(p)
            sock.sendto(encrypted, client_addr)

def client_to_tun():
    global client_addr
    while True:
        data, addr = sock.recvfrom(65535)
        try:
            decrypted = f.decrypt(data)
        except Exception as e:
            print(f"Decrypt failed from {addr}: {e}", flush=True)
            continue
        client_addr = addr
        print(f"Received from client: {addr}", flush=True)
        if decrypted == b'hello':
            continue
        tun.write(decrypted)

threading.Thread(target=tun_to_client, daemon=True).start()
threading.Thread(target=client_to_tun, daemon=True).start()

while True:
    pass