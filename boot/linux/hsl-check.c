/* Bramka fazy 2: plik z xattr security.hss.lock bez sesji Φ dostaje EACCES. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/xattr.h>
#include <unistd.h>

int main(void)
{
	int fd, dev, n;
	ssize_t w;
	char num[16];
	int len;

	fd = open("/mnt/hsl-secret", O_CREAT | O_RDWR | O_TRUNC, 0600);
	if (fd < 0) {
		printf("HSL_OPEN_FAIL %d\n", errno);
		return 1;
	}
	if (write(fd, "secret", 6) != 6) {
		printf("HSL_WRITE_FAIL %d\n", errno);
		return 1;
	}
	if (setxattr("/mnt/hsl-secret", "security.hss.lock", "1", 1, 0) != 0) {
		if (setxattr("/mnt/hsl-secret", "user.hss.lock", "1", 1, 0) != 0) {
			printf("HSL_XATTR_FAIL %d\n", errno);
			return 1;
		}
		printf("HSL_XATTR_USER\n");
	}
	dev = open("/dev/hss", O_RDWR);
	if (dev < 0) {
		printf("HSL_DEV_FAIL %d\n", errno);
		return 1;
	}
	len = snprintf(num, sizeof(num), "%d", fd);
	w = write(dev, num, (size_t)len);
	if (w < 0) {
		printf("HSL_MARK_FAIL %d\n", errno);
		return 1;
	}
	close(fd);
	close(dev);
	n = open("/mnt/hsl-secret", O_RDONLY);
	if (n < 0 && errno == EACCES) {
		printf("HSL_DENY\n");
		return 0;
	}
	printf("HSL_ALLOW %d\n", n < 0 ? errno : 0);
	return 1;
}
