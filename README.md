# NorthTunnel

NorthTunnel is a Layer 3 VPN built from scratch in Python. It creates an encrypted tunnel between a client and a server using TUN interfaces and UDP sockets, then routes all of the client's internet traffic through that tunnel so it exits from the server's IP.

---

## The Problem

Commercial VPNs (NordVPN, ExpressVPN, WireGuard) are black boxes from a learning perspective. You install a client, hit connect, and your traffic gets tunneled somewhere. There is a lot going on under the hood: virtual network interfaces, encryption, NAT, routing tables, kernel forwarding, and packet checksums. Reading about it is one thing, building one is another.

NorthTunnel is a portfolio project where I built the whole pipeline from the bottom up to actually understand how a Layer 3 VPN works. No high level networking libraries, just raw UDP sockets, a TUN interface, and Python.

---

## What It Does

- Client creates a virtual network interface (`tun0` at `10.0.0.2`) and reroutes all default traffic through it
- Packets that enter the client's TUN are encrypted with Fernet and sent over UDP to the server
- Server (at `10.0.0.1`) receives the encrypted UDP packets, decrypts them, and writes them to its own TUN interface
- Server has IP forwarding enabled and a NAT masquerading rule, so the kernel forwards those packets out to the real internet through `eth0` with the source IP rewritten to the server's address
- Responses come back to the server, get routed back into its TUN, get encrypted, and sent back over UDP to the client
- Client decrypts and writes the response to its TUN, where it gets delivered to whatever made the original request (ping, curl, browser)
- From the outside, all traffic looks like it came from the server, not the client

---

## Tech Stack

- **Language** - Python 3.13
- **Encryption** - `cryptography` library (Fernet symmetric encryption)
- **TUN interface** - `python-pytun`
- **Networking** - Python `socket` (UDP) and `threading`
- **Container runtime** - Docker and docker-compose
- **NAT and forwarding** - `iptables`
- **Routing config** - `iproute2`
- **Setup glue** - Bash

---

## How It Works

The flow from a client `curl example.com` to the response coming back:

1. Server starts, creates `tun0` at `10.0.0.1`, sets up `iptables` NAT masquerading on `eth0`, opens UDP port `8888`
2. Client starts, creates `tun0` at `10.0.0.2`, sends an encrypted `hello` bootstrap packet so the server learns its UDP address
3. Client's startup script adds a route for the server's Docker IP through normal networking first (otherwise the tunnel would try to route its own UDP packets through itself and you would get an infinite loop), then replaces the default route to go through `tun0`
4. `curl` issues a TCP SYN to `example.com`. The kernel sees the default route is via `tun0` and writes the packet there
5. The Python client reads the raw IP packet from `tun0`, encrypts it with Fernet, sends it as a UDP datagram to the server
6. Server receives the UDP datagram, decrypts it, recomputes the checksums (see Technical Challenges below for why), writes the packet to its own `tun0`
7. Linux kernel on the server picks the packet up from `tun0`, sees the destination is `example.com`, routes it out `eth0`, applies the MASQUERADE rule to rewrite the source IP from `10.0.0.2` to the server's `eth0` address
8. Reply comes back to the server's `eth0`. Connection tracking reverses the NAT, so the destination IP becomes `10.0.0.2` again, kernel routes it to `tun0`
9. Python server reads the reply from `tun0`, fixes checksums, encrypts, sends back to the client over UDP
10. Python client decrypts, writes to its `tun0`, kernel delivers the response to the curl socket

---

## Files

- `Dockerfile` - builds the image with Python 3.13 and the networking tools needed at runtime (`iproute2`, `iputils-ping`, `net-tools`, `iptables`, `ethtool`, `tcpdump`)
- `docker-compose.yml` - defines `client_service` and `server_service` on a shared Docker network, gives both `NET_ADMIN` capability and access to `/dev/net/tun`, sets `net.ipv4.ip_forward=1` on the server via `sysctls`
- `vpn_server.py` - creates `tun0` at `10.0.0.1`, listens on UDP `8888`, runs two threads. One reads encrypted packets from the client and writes decrypted data to `tun0`. The other reads from `tun0`, fixes the IP/TCP/UDP/ICMP checksums in `fix_checksums()`, encrypts, and sends back to the client
- `vpn_client.py` - creates `tun0` at `10.0.0.2`, sends a bootstrap packet so the server knows where to send replies, runs two threads. One reads from `tun0` and sends encrypted UDP to the server. The other receives from the server, decrypts, and writes to `tun0`
- `server_start.sh` - verifies `ip_forward` is set, installs the NAT and FORWARD `iptables` rules, starts the Python server in the background, then disables TUN checksum offloading with `ethtool` once `tun0` is up
- `client_start.sh` - starts the Python client in the background, waits for `tun0`, disables TUN offloading, preserves the route to the server's Docker IP through normal `eth0` networking, then replaces the default route to go through `tun0`
- `.env` - holds the shared Fernet key as `VPN_KEY=...` (gitignored)
- `requirements.txt` - `cryptography` and `python-pytun`

---

## Technical Challenges

Getting the encrypted tunnel itself working was straightforward. Getting actual internet routing through it was not. There were four real bugs that all had to be fixed before `curl example.com` from inside the client container worked end to end.

**1. `iptables` was never installed in the image**

The original `Dockerfile` only installed `iproute2`, `iputils-ping`, and `net-tools`. The server startup script called `iptables -t nat -A POSTROUTING ... -j MASQUERADE` to set up NAT, but the binary did not exist. The script had no `set -e` so the error printed to stderr and bash kept going. The server came up looking fine but no NAT rule was ever installed, so packets leaving the server still had source IP `10.0.0.2` and Docker's bridge had no idea how to route replies back.

Fix: added `iptables` to the `Dockerfile`, added `set -e` to `server_start.sh` so future silent failures of this kind cannot happen.

**2. `echo 1 > /proc/sys/net/ipv4/ip_forward` was also silently failing**

After fixing iptables, the script tried to enable IP forwarding by writing to `/proc/sys/net/ipv4/ip_forward`. Inside a Docker container that file is read only and the write fails. The kernel was forwarding packets anyway because Docker Desktop's underlying VM has it enabled globally, but that is just lucky, not correct.

Fix: set `net.ipv4.ip_forward=1` via the `sysctls` block in `docker-compose.yml`, which Docker allows as a per namespace setting. The script now reads the value and exits if it is not `1`, instead of trying to write it.

**3. TCP checksum corruption from NAT plus receive offload (the hard one)**

After fixing the first two, ping `8.8.8.8` through the tunnel worked but every single TCP connection failed. The `tcpdump` output on the client's `tun0` showed something like `cksum 0xf7a9 (incorrect -> 0x7ca7)` on every SYN-ACK coming back. The `/proc/net/snmp` counters showed `InCsumErrors` equal to `InSegs`, which means every TCP segment received was being dropped for a bad checksum.

What was happening: the server's `eth0` is one end of a Docker veth pair. Inbound packets arrive marked `CHECKSUM_UNNECESSARY` because hardware (or the bridge) already validated them. Normally when the kernel does NAT and rewrites the destination IP, it updates the TCP checksum incrementally. But when the packet is marked as already validated, the kernel trusts that and skips the update. The TCP header still contains the pre-NAT checksum, which is wrong now that the destination IP is different. Userspace reads the packet from `tun0` with this stale checksum, encrypts it, sends it. The client kernel computes the checksum from scratch (TUN has no offload), it does not match, packet dropped.

ICMP (ping) was unaffected because the ICMP checksum has no pseudo-header containing the IP addresses, so changing the destination IP does not invalidate it.

Things I tried that did not work: disabling generic receive offload and large receive offload on `eth0` with `ethtool` (the offload state still came from the upstream veth peer), and adding `iptables -t mangle ... -j CHECKSUM --checksum-fill` (that target only acts on packets in `CHECKSUM_PARTIAL` state, not `CHECKSUM_UNNECESSARY`).

Fix: recompute the IP and L4 checksums in Python before encrypting, in `fix_checksums()` in `vpn_server.py`. It parses the IPv4 header, identifies the protocol, zeros out the existing checksum field, and writes the recalculated value back. I also had to switch the TUN device flags from the default `IFF_TUN` to `IFF_TUN | IFF_NO_PI` so `tun.read()` returns the raw IP packet without a 4 byte packet info prefix. Without that, the first byte of the buffer was a flags byte (`0x00`), not the IP version nibble (`0x4`), and the checksum function was bailing out thinking the packet was not IPv4.

**4. Receive buffer too small plus exception killing the receiver thread**

After the checksum fix, plain HTTP worked but HTTPS hung. The server logs showed `cryptography.fernet.InvalidToken` exceptions in `Thread-2 (client_to_tun)`. Two problems stacked on top of each other.

First, the server's socket was doing `sock.recvfrom(1024)`. A full MTU IP packet is 1500 bytes, and Fernet adds about 30 percent of overhead (base64 encoded ciphertext, header, MAC), so encrypted packets reach around 2 KB. Anything over 1024 bytes got truncated by the kernel. Fernet's integrity check failed on the partial ciphertext and raised `InvalidToken`.

Second, that exception killed the receiver thread. After the first truncated packet, the server stopped reading any client traffic at all, which is why the TLS handshake hung instead of failing fast.

Fix: increased the buffer to `65535` (the maximum UDP datagram size) on both sides, and wrapped the `f.decrypt()` calls in try/except so a malformed packet just gets logged and skipped instead of taking the thread down.

---

## Known Limitations

- The encryption key is a single shared symmetric Fernet key stored in a `.env` file. A real VPN would use a proper key exchange protocol like Diffie-Hellman or Noise, plus per session keys
- The server tracks one `client_addr` global, so only one client can be connected at a time. A second client would overwrite the first
- The client only sends its bootstrap `hello` packet once at startup. If the server restarts, the client never re-bootstraps and the tunnel stops working until the client is restarted too. A production version would send periodic keepalives
- `tun_to_client` busy-spins on `if client_addr is not None` until a client connects, burning CPU for no reason. A `threading.Event` would be cleaner
- Currently runs locally in Docker on the same host. For real use the server would be deployed to a VPS or a Raspberry Pi at a different location
- Because the server is a Docker container on the same Mac, the exit IP is whatever NAT chain Docker Desktop happens to use, which ends up being your Mac's public IP. For actual IP masking the server needs to be on a separate machine somewhere else
- No congestion control, no MTU negotiation, no fragmentation handling beyond what UDP and the kernel do for you. Real VPNs deal with this carefully

---

## Running Locally

**Prerequisites:** Docker Desktop, Git. Python only needs to exist inside the Docker images, not on your host.

**Clone the repo:**
```bash
git clone https://github.com/YOURUSERNAME/NorthTunnel.git
cd NorthTunnel
```

**Generate a Fernet key and put it in `.env`:**
```bash
python3 -c "from cryptography.fernet import Fernet; print('VPN_KEY=' + Fernet.generate_key().decode())" > .env
```

(If you do not have Python on your host, you can run that one liner inside any Python container instead.)

**Build and start the server:**
```bash
docker-compose up -d --build server_service
```

**Start the client:**
```bash
docker-compose run --name northtunnel-client client_service bash client_start.sh
```

**Test it from another terminal:**
```bash
docker exec northtunnel-client ping -c 3 8.8.8.8
docker exec northtunnel-client curl -s https://example.com -o /dev/null -w "HTTP %{http_code}\n"
docker exec northtunnel-client curl -s https://api.ipify.org
```

The last command should print your Mac's public IP, which confirms the traffic is going out through the server and not directly from the client.

---

## References

Primary reference: [jonaslieb.de/blog/python-vpn](https://jonaslieb.de/blog/python-vpn) walks through building a Layer 3 VPN in Python with TUN interfaces and UDP sockets.

Secondary reference: [github.com/veldig/vpn-tun-demo](https://github.com/veldig/vpn-tun-demo) is a useful Docker compose setup for two containers sharing a TUN based tunnel.
