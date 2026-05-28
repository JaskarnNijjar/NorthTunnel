import socket
import os
from cryptography.fernet import Fernet
import pytun
import threading

HOST = ''
PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sock.bind((HOST, PORT))

key = os.environ.get('VPN_KEY').encode()
f = Fernet(key)
tun = pytun.TunTapDevice(name='tun0')
tun.addr = '10.0.0.1'
tun.netmask = '255.255.255.0'
tun.mtu = 1500
tun.up()

client_addr = None

def tun_to_client():
    while True:
        if client_addr is not None:
            p = tun.read(tun.mtu)
            print(f"Read from TUN, sending to client", flush=True)
            encrypted = f.encrypt(p)
            sock.sendto(encrypted, client_addr)

def client_to_tun():
    global client_addr
    while True:
        data, addr = sock.recvfrom(1024)
        client_addr = addr
        print(f"Received from client: {addr}", flush=True)
        decrypted = f.decrypt(data)
        if decrypted == b'hello':
            continue
        tun.write(decrypted)

threading.Thread(target=tun_to_client, daemon=True).start()
threading.Thread(target=client_to_tun, daemon=True).start()

while True:
    pass