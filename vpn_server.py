import socket

HOST = ''
PORT = 8888

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sock.bind((HOST, PORT))

while True:
    print("Waiting for data...", flush=True)
    data, addr = sock.recvfrom(1024)
    print(f"Received message: {data.decode('utf-8')} from {addr}")
    sock.sendto(data, addr)
    