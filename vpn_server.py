import socket
import os
from cryptography.fernet import Fernet

key = os.environ.get('VPN_KEY').encode()
f = Fernet(key)

HOST = ''
PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sock.bind((HOST, PORT))

while True:
    print("Waiting for data...", flush=True)
    data, addr = sock.recvfrom(1024)
    decrypted = f.decrypt(data)
    print(f"Received message: {decrypted.decode('utf-8')} from {addr}")
    encrypted = f.encrypt(data)
    sock.sendto(encrypted, addr)
    