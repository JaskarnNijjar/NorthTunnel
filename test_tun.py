import pytun
import time

tun = pytun.TunTapDevice(name='tun0')
tun.addr = '10.0.0.1'
tun.netmask = '255.255.255.0'
tun.mtu = 1500
tun.up()

print('TUN interface up at', tun.addr)
time.sleep(30)