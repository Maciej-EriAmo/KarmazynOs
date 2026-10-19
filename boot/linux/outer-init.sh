#!/bin/busybox sh
/bin/busybox --install -s /bin
export PATH=/bin
echo "HSL_UNAME $(uname -r)"
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev
mount -t tmpfs -o size=3200M tmp /new
if [ -f /proc/sys/net/ipv6/conf/all/disable_ipv6 ]; then
  echo 1 > /proc/sys/net/ipv6/conf/all/disable_ipv6
fi
insmod /e1000.ko
echo "HSL_E1000 $?"
sleep 1
echo "HSL_NET $(ls /sys/class/net)"
nic=""
for cand in $(ls /sys/class/net); do
  if [ "$cand" = lo ]; then
    continue
  fi
  if ifconfig "$cand" up 2>/dev/null; then
    nic=$cand
    break
  fi
done
echo "HSL_NIC $nic"
if [ -z "$nic" ]; then
  dmesg | tail -n 40
  poweroff -f
  exit 1
fi
# To jądro virt nie ma AF_PACKET, więc udhcpc nie wstaje. Slirp QEMU ma stały adres.
ifconfig "$nic" 10.0.2.15 netmask 255.255.255.0 up
route add default gw 10.0.2.2
mkdir -p /etc
printf 'nameserver 10.0.2.3\n' > /etc/resolv.conf
echo "HSL_IP 10.0.2.15 gw 10.0.2.2"
if command -v ping >/dev/null 2>&1; then
  ping -c 1 -W 3 10.0.2.2
  echo "HSL_PING $?"
fi
if [ -f /minirootfs.tar.gz ]; then
  cp /minirootfs.tar.gz /new/root.tar.gz
  echo HSL_ROOT_LOCAL
else
  wget -O /new/root.tar.gz "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/alpine-minirootfs-3.24.2-x86_64.tar.gz"
  echo "HSL_WGET $?"
fi
if [ ! -s /new/root.tar.gz ]; then
  echo HSL_NO_ROOT
  poweroff -f
  exit 1
fi
tar -C /new -xzf /new/root.tar.gz
echo "HSL_TAR $?"
mkdir -p /new/src /new/out
cp /src/* /new/src/
if [ -f /etc/resolv.conf ]; then
  cp /etc/resolv.conf /new/etc/resolv.conf
fi
mount --bind /proc /new/proc
mount --bind /sys /new/sys
mount --bind /dev /new/dev
echo HSL_NO_9P
chroot /new /bin/sh /src/build-init.sh
echo HSL_OUTER_DONE
poweroff -f
