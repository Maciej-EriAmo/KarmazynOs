#!/bin/sh
export PATH=/bin
[ "$1" = bound ] || [ "$1" = renew ] || exit 0
ifconfig "$interface" "$ip" netmask "${subnet:-255.255.255.0}" up
if [ -n "$router" ]; then
  route del default >/dev/null 2>&1
  route add default gw "$router"
fi
mkdir -p /etc
echo "nameserver ${dns:-10.0.2.3}" > /etc/resolv.conf
echo "HSL_IP $ip gw $router dns $dns"
