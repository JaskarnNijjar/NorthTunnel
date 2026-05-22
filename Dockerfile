FROM python:3.13
WORKDIR /app

RUN apt-get update && apt-get install -y \
    iproute2 iputils-ping net-tools \
    && rm -rf /var/lib/apt/lists/*
    
COPY . /app
RUN pip install -r requirements.txt


CMD ["python", "vpn_server.py"]