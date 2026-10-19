/* PID 1: ładuje holo_hsl.ko, odpala hsl-check, potem zostaje shellem. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static void ensure_hss_node(void)
{
	int s;
	char buf[32];
	unsigned maj, min;
	ssize_t n;

	if (access("/dev/hss", F_OK) == 0)
		return;
	s = open("/sys/class/misc/hss/dev", O_RDONLY);
	if (s < 0)
		return;
	n = read(s, buf, sizeof(buf) - 1);
	close(s);
	if (n <= 0)
		return;
	buf[n] = 0;
	if (sscanf(buf, "%u:%u", &maj, &min) == 2)
		mknod("/dev/hss", S_IFCHR | 0600, makedev(maj, min));
}

static void load_module(void)
{
	int fd = open("/holo_hsl.ko", O_RDONLY);
	if (fd < 0) {
		dprintf(1, "HSL_NO_KO %d\n", errno);
		return;
	}
	if (syscall(SYS_finit_module, fd, "", 0) != 0)
		dprintf(1, "HSL_INSMOD_FAIL %d\n", errno);
	else
		dprintf(1, "HSL_LOADED\n");
	close(fd);
	ensure_hss_node();
}

static void run(char *const argv[])
{
	pid_t pid = fork();
	int st = 0;
	if (pid == 0) {
		execv(argv[0], argv);
		dprintf(1, "HSL_EXEC_FAIL %s %d\n", argv[0], errno);
		_exit(127);
	}
	if (pid > 0)
		waitpid(pid, &st, 0);
}

int main(void)
{
	char *check[] = { "/hsl-check", NULL };
	char *shell[] = { "/karmazyn_shell", NULL };

	mkdir("/proc", 0755);
	mkdir("/sys", 0755);
	mkdir("/dev", 0755);
	mkdir("/mnt", 0755);
	mount("proc", "/proc", "proc", 0, NULL);
	mount("sys", "/sys", "sysfs", 0, NULL);
	mount("dev", "/dev", "devtmpfs", 0, NULL);
	if (mount("tmp", "/mnt", "tmpfs", 0, NULL) != 0)
		dprintf(1, "HSL_TMPFS_FAIL %d\n", errno);
	load_module();
	run(check);
	execv(shell[0], shell);
	dprintf(1, "SHELL_EXEC_FAIL %d\n", errno);
	for (;;)
		pause();
}
