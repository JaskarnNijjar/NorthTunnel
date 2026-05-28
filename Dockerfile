FROM python:3.13
WORKDIR /app

RUN apt-get update && apt-get install -y \
    iproute2 iputils-ping net-tools iptables ethtool tcpdump \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
RUN chmod +x server_start.sh client_start.sh
RUN pip install -r requirements.txt


CMD ["python", "vpn_server.py"]