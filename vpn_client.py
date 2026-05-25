import socket
import sys
sys.stdout.flush()

HOST = 'server_service'
PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("Client starting...", flush=True)
msg = input(f"Enter message to send: ")
sock.sendto(msg.encode('utf-8'), (HOST, PORT))
data, addr = sock.recvfrom(1024)
print(f"{data.decode('utf-8')} from {addr}")
