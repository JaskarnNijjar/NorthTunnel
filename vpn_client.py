import socket
import os
from cryptography.fernet import Fernet

key = os.environ.get('VPN_KEY').encode()
f = Fernet(key)

HOST = 'server_service'
PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("Client starting...")
msg = input(f"Enter message to send: ")
encrypted = f.encrypt(msg.encode('utf-8'))
sock.sendto(encrypted, (HOST, PORT))
data, addr = sock.recvfrom(1024)
decrypted = f.decrypt(data)
print(f"{decrypted.decode('utf-8')} from {addr}")
