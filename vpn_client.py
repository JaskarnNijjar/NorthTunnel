import socket
import os
from cryptography.fernet import Fernet
import pytun
import threading

HOST = 'server_service'
PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

key = os.environ.get('VPN_KEY').encode()
f = Fernet(key)
tun = pytun.TunTapDevice(name='tun0')
tun.addr = '10.0.0.2'
tun.netmask = '255.255.255.0'
tun.mtu = 1500
tun.up()

sock.sendto(f.encrypt(b'hello'), (HOST, PORT))

def tun_to_server():
    while True:
            p = tun.read(tun.mtu)
            print(f"Read from TUN, sending to server", flush=True)
            sock.sendto(f.encrypt(p), (HOST, PORT))

def server_to_tun():
    while True:
        data, addr = sock.recvfrom(4096)
        print(f"Received from server", flush=True)
        tun.write(f.decrypt(data))


threading.Thread(target=tun_to_server, daemon=True).start()
threading.Thread(target=server_to_tun, daemon=True).start()

while True:
    pass