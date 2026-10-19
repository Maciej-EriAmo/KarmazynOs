#!/bin/sh
echo HSL_CHROOT_OK
export PATH=/usr/bin:/bin:/sbin:/usr/sbin
printf '%s\n' \
  "https://dl-cdn.alpinelinux.org/alpine/latest-stable/main" \
  "https://dl-cdn.alpinelinux.org/alpine/latest-stable/community" \
  > /etc/apk/repositories
apk_ok=1
i=1
while [ "$i" -le 5 ]; do
  if apk add --no-cache gcc make musl-dev linux-headers linux-virt-dev=6.18.57-r0; then
    apk_ok=0
    break
  fi
  echo "HSL_APK_RETRY $i"
  i=$((i + 1))
  sleep 4
done
echo "HSL_APK $apk_ok"
if [ "$apk_ok" -ne 0 ]; then
  echo HSL_BUILD_FAIL
  sync
  poweroff -f
  exit 1
fi
krel=$(uname -r)
echo "HSL_KREL $krel"
build="/lib/modules/$krel/build"
echo "HSL_BUILDDIR $build"
if [ ! -d "$build" ]; then
  echo HSL_NO_HEADERS
  ls -d /usr/src/* /lib/modules/* 2>/dev/null
  sync
  poweroff -f
  exit 1
fi
cd /src || exit 1
make -C "$build" M=/src modules
mk=$?
echo "HSL_MAKE $mk"
gcc -static -O2 -o /src/hsl-check /src/hsl-check.c
g1=$?
gcc -static -O2 -o /src/init-hsl /src/init.c
g2=$?
echo "HSL_GCC $g1 $g2"
if [ "$mk" -ne 0 ] || [ "$g1" -ne 0 ] || [ "$g2" -ne 0 ]; then
  echo HSL_BUILD_FAIL
  sync
  poweroff -f
  exit 1
fi
if [ -w /proc/sys/kernel/printk ]; then
  echo 0 > /proc/sys/kernel/printk
fi
b64() {
  if command -v base64 >/dev/null 2>&1; then
    base64 "$1"
  else
    busybox base64 "$1"
  fi
}
for f in holo_hsl.ko hsl-check init-hsl; do
  echo "BEGIN $f"
  b64 "/src/$f"
  echo "END $f"
done
echo HSL_BUILD_OK
sync
poweroff -f
