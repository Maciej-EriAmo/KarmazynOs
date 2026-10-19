// SPDX-License-Identifier: GPL-2.0
/*
 * Ładowalna bramka HSL na jądrze 6.18 (Alpine virt).
 *
 * security_add_hooks() jest __init i bierze struct lsm_id. Moduł po starcie
 * jądra nie może zarejestrować LSM. holoPhiHss.c zostaje źródłem na jądro
 * złożone z tą łatą. Ten plik jest tym, co da się insmod na jądrze z płyty.
 *
 * Decyzja fazy 2: inode wpisany na listę (xattr security.hss.lock) dostaje
 * odmowę MAY_READ/MAY_WRITE, gdy wołający nie ma sesji Φ. Sesję ustawi demon
 * w fazie 3. Brak sesji = odmowa. Jądro nie liczy HMAC.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/kprobes.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/xattr.h>
#include <linux/file.h>
#include <linux/ptrace.h>
#include <linux/string.h>
#include <linux/mnt_idmapping.h>

#define HSL_XATTR "security.hss.lock"
#define HSL_WATCH_MAX 32

struct hsl_watch {
	dev_t dev;
	unsigned long ino;
};

static struct hsl_watch hsl_watches[HSL_WATCH_MAX];
static int hsl_watch_n;
static bool hsl_session;
static DEFINE_SPINLOCK(hsl_lock);

static int hsl_is_watched(struct inode *inode)
{
	dev_t dev = inode->i_sb->s_dev;
	unsigned long ino = inode->i_ino;
	int i, n;

	spin_lock(&hsl_lock);
	n = hsl_watch_n;
	for (i = 0; i < n; i++) {
		if (hsl_watches[i].dev == dev && hsl_watches[i].ino == ino) {
			spin_unlock(&hsl_lock);
			return 1;
		}
	}
	spin_unlock(&hsl_lock);
	return 0;
}

static int hsl_add_watch(struct inode *inode)
{
	spin_lock(&hsl_lock);
	if (hsl_watch_n >= HSL_WATCH_MAX) {
		spin_unlock(&hsl_lock);
		return -ENOSPC;
	}
	hsl_watches[hsl_watch_n].dev = inode->i_sb->s_dev;
	hsl_watches[hsl_watch_n].ino = inode->i_ino;
	hsl_watch_n++;
	spin_unlock(&hsl_lock);
	return 0;
}

/* Zapis 1 bajtu: fd pliku z xattr HSL. Odczyt: '0' brak sesji, '1' sesja. */
static ssize_t hsl_write(struct file *filp, const char __user *buf,
			  size_t len, loff_t *ppos)
{
	int fd, err;
	struct fd f;
	char raw[16];
	ssize_t n;

	if (len == 0 || len >= sizeof(raw))
		return -EINVAL;
	if (copy_from_user(raw, buf, len))
		return -EFAULT;
	raw[len] = 0;
	if (raw[0] == 'S') {
		spin_lock(&hsl_lock);
		hsl_session = true;
		spin_unlock(&hsl_lock);
		return len;
	}
	err = kstrtoint(skip_spaces(raw), 10, &fd);
	if (err)
		return err;
	f = fdget(fd);
	if (fd_empty(f))
		return -EBADF;
	n = vfs_getxattr(&nop_mnt_idmap, fd_file(f)->f_path.dentry, HSL_XATTR,
			 raw, 1);
	if (n < 0)
		n = vfs_getxattr(&nop_mnt_idmap, fd_file(f)->f_path.dentry,
				 "user.hss.lock", raw, 1);
	if (n < 0) {
		fdput(f);
		return n;
	}
	err = hsl_add_watch(file_inode(fd_file(f)));
	fdput(f);
	return err ? err : len;
}

static ssize_t hsl_read(struct file *filp, char __user *buf, size_t len,
			 loff_t *ppos)
{
	char c;

	if (*ppos)
		return 0;
	if (len < 2)
		return -EINVAL;
	spin_lock(&hsl_lock);
	c = hsl_session ? '1' : '0';
	spin_unlock(&hsl_lock);
	if (copy_to_user(buf, &c, 1))
		return -EFAULT;
	if (copy_to_user(buf + 1, "\n", 1))
		return -EFAULT;
	*ppos = 2;
	return 2;
}

static const struct file_operations hsl_fops = {
	.owner = THIS_MODULE,
	.read = hsl_read,
	.write = hsl_write,
};

static struct miscdevice hsl_misc = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "hss",
	.fops = &hsl_fops,
};

struct hsl_probe_ctx {
	int deny;
};

static int hsl_entry(struct kretprobe_instance *ri, struct pt_regs *regs)
{
	struct hsl_probe_ctx *ctx = (struct hsl_probe_ctx *)ri->data;
	struct inode *inode = (struct inode *)regs->di;
	int mask = (int)regs->si;
	bool session;

	ctx->deny = 0;
	if (!inode || !(mask & (MAY_READ | MAY_WRITE)))
		return 0;
	spin_lock(&hsl_lock);
	session = hsl_session;
	spin_unlock(&hsl_lock);
	if (session)
		return 0;
	if (hsl_is_watched(inode))
		ctx->deny = 1;
	return 0;
}

static int hsl_ret(struct kretprobe_instance *ri, struct pt_regs *regs)
{
	struct hsl_probe_ctx *ctx = (struct hsl_probe_ctx *)ri->data;

	if (ctx->deny && regs_return_value(regs) == 0)
		regs_set_return_value(regs, (unsigned long)-EACCES);
	return 0;
}

static struct kretprobe hsl_probe = {
	.kp.symbol_name = "security_inode_permission",
	.entry_handler = hsl_entry,
	.handler = hsl_ret,
	.data_size = sizeof(struct hsl_probe_ctx),
	.maxactive = 32,
};

static int __init hsl_init(void)
{
	int ret;

	ret = misc_register(&hsl_misc);
	if (ret)
		return ret;
	ret = register_kretprobe(&hsl_probe);
	if (ret) {
		misc_deregister(&hsl_misc);
		pr_err("holo_hsl: kretprobe %d\n", ret);
		return ret;
	}
	pr_info("holo_hsl: loaded (no phi session denies watched inodes)\n");
	return 0;
}

static void __exit hsl_exit(void)
{
	unregister_kretprobe(&hsl_probe);
	misc_deregister(&hsl_misc);
	pr_info("holo_hsl: unloaded\n");
}

module_init(hsl_init);
module_exit(hsl_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Karmazyn HSL gate for Linux 6.18");
MODULE_AUTHOR("KarmazynOs");
