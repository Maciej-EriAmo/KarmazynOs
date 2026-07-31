//! KarmazynOs kentry — Multiboot2 entry (faza F / R2 + R5 slab demo).
//!
//! - COM1: `KARMAZYN_KENTRY_OK\n`
//! - opcjonalnie: dump cmdline z Multiboot2 info (SF.4)
//! - R5: static `SlabStore` — atom / tick / stats (bez CPython)
//!
//!   cd boot/kentry
//!   cargo build --release --target x86_64-unknown-none

#![no_std]
#![no_main]

use core::arch::asm;
use core::panic::PanicInfo;
use core::ptr;

use karmazyn_slab::{SlabStore, T_INIT};

/// Multiboot2 header (spec).
const MB2_MAGIC: u32 = 0xE852_50D6;
const MB2_ARCH_I386: u32 = 0;
const MB2_HEADER_LEN: u32 = 24;
/// Bootloader magic in EAX after Multiboot2 handoff.
const MB2_BOOTLOADER_MAGIC: u32 = 0x36D7_6289;
const TAG_CMDLINE: u32 = 1;
const TAG_END: u32 = 0;

#[repr(C, align(8))]
struct Multiboot2Header {
    magic: u32,
    architecture: u32,
    header_length: u32,
    checksum: u32,
    end_type: u16,
    end_flags: u16,
    end_size: u32,
}

const _: () = assert!(core::mem::size_of::<Multiboot2Header>() == 24);
const _: () = assert!(core::mem::align_of::<Multiboot2Header>() >= 8);

const MB2_CHECKSUM: u32 = (0u32)
    .wrapping_sub(MB2_MAGIC)
    .wrapping_sub(MB2_ARCH_I386)
    .wrapping_sub(MB2_HEADER_LEN);

#[used]
#[link_section = ".multiboot_header"]
static MULTIBOOT2_HEADER: Multiboot2Header = Multiboot2Header {
    magic: MB2_MAGIC,
    architecture: MB2_ARCH_I386,
    header_length: MB2_HEADER_LEN,
    checksum: MB2_CHECKSUM,
    end_type: 0,
    end_flags: 0,
    end_size: 8,
};

pub const KENTRY_OK: &[u8] = b"KARMAZYN_KENTRY_OK\n";

/// Freestanding store — BSS, not stack (R3 stack-size lesson).
static mut SLAB: SlabStore = SlabStore::new();

#[no_mangle]
pub extern "C" fn _start() -> ! {
    // Multiboot2: EAX = magic, EBX = &boot_info (32-bit ptr)
    let magic: u32;
    let info_ptr: u32;
    unsafe {
        asm!(
            "mov {m:e}, eax",
            "mov {i:e}, ebx",
            m = out(reg) magic,
            i = out(reg) info_ptr,
            options(nostack, nomem),
        );
    }

    serial_init();
    serial_write(KENTRY_OK);

    if magic == MB2_BOOTLOADER_MAGIC && info_ptr != 0 {
        serial_write(b"MB2_MAGIC_OK\n");
        if let Some(cmd) = unsafe { mb2_cmdline(info_ptr as usize) } {
            serial_write(b"CMDLINE=");
            serial_write(cmd);
            serial_write(b"\n");
        } else {
            serial_write(b"CMDLINE=\n");
        }
    } else {
        // direct jump / non-MB2 entry — still OK marker above
        serial_write(b"MB2_MAGIC_SKIP\n");
    }

    slab_demo();

    halt_loop()
}

/// R5: exercise vacuum + retain, print stats. `SLAB_OK` only if both hold.
fn slab_demo() {
    serial_write(b"SLAB_DEMO\n");
    // SAFETY: single-threaded kentry; no concurrent access.
    let store = unsafe { &mut *ptr::addr_of_mut!(SLAB) };
    store.reset();

    // ── A: orphan vacuum ────────────────────────────────────────────────
    store.set_decay(0.1);
    let Some(orphan) = store.atom_new("O", "orphan", T_INIT) else {
        serial_write(b"SLAB_ATOM_FAIL\n");
        return;
    };
    store.settle(30);
    let orphan_gone = !store.has_atom(orphan);
    let reaped_a = store.reaped;
    if !orphan_gone || reaped_a == 0 {
        serial_write(b"SLAB_VACUUM_FAIL\n");
        serial_write(b"SLAB_ATOMS=");
        serial_u64(store.count_atoms() as u64);
        serial_write(b" REAPED=");
        serial_u64(reaped_a);
        serial_write(b"\n");
        return;
    }
    serial_write(b"SLAB_VACUUM_OK\n");

    // ── B: rooted retain (same freelist store) ──────────────────────────
    let Some(aid) = store.atom_new("S", "kentry", T_INIT) else {
        serial_write(b"SLAB_ATOM_FAIL\n");
        return;
    };
    let Some(bid) = store.bubble_new(None) else {
        serial_write(b"SLAB_BUBBLE_FAIL\n");
        return;
    };
    if !store.bind(bid, "v", aid) || !store.set_root(bid) {
        serial_write(b"SLAB_ROOT_FAIL\n");
        return;
    }
    store.settle(25);

    let atoms = store.count_atoms() as u64;
    let reaped = store.reaped;
    let live = if store.has_atom(aid) { 1u64 } else { 0u64 };

    serial_write(b"SLAB_ATOMS=");
    serial_u64(atoms);
    serial_write(b" REAPED=");
    serial_u64(reaped);
    serial_write(b" LIVE=");
    serial_u64(live);
    serial_write(b"\n");

    // Honest gate: vacuum worked and root retained cold atom
    if live == 1 && reaped >= 1 && atoms >= 1 {
        serial_write(b"SLAB_OK\n");
    } else {
        serial_write(b"SLAB_FAIL\n");
    }
}

/// Walk Multiboot2 info tags; return cmdline bytes (type=1) if present.
unsafe fn mb2_cmdline(info: usize) -> Option<&'static [u8]> {
    if info == 0 {
        return None;
    }
    // total_size at offset 0; tags start at offset 8
    let mut p = info + 8;
    let end = info + ptr::read_unaligned(info as *const u32) as usize;
    while p + 8 <= end {
        let typ = ptr::read_unaligned(p as *const u32);
        let size = ptr::read_unaligned((p + 4) as *const u32) as usize;
        if size < 8 {
            break;
        }
        if typ == TAG_END {
            break;
        }
        if typ == TAG_CMDLINE && size > 8 {
            let s = (p + 8) as *const u8;
            let max = size - 8;
            let mut len = 0usize;
            while len < max {
                if *s.add(len) == 0 {
                    break;
                }
                len += 1;
            }
            return Some(core::slice::from_raw_parts(s, len));
        }
        // tags aligned to 8 bytes
        p += (size + 7) & !7;
    }
    None
}

fn serial_init() {
    unsafe {
        outb(0x3F8 + 1, 0x00);
        outb(0x3F8 + 3, 0x80);
        outb(0x3F8 + 0, 0x03);
        outb(0x3F8 + 1, 0x00);
        outb(0x3F8 + 3, 0x03);
        outb(0x3F8 + 2, 0xC7);
        outb(0x3F8 + 4, 0x0B);
    }
}

fn serial_write(bytes: &[u8]) {
    for &b in bytes {
        while !serial_tx_empty() {}
        unsafe { outb(0x3F8, b) };
    }
}

fn serial_u64(mut n: u64) {
    let mut buf = [0u8; 20];
    let mut i = buf.len();
    if n == 0 {
        serial_write(b"0");
        return;
    }
    while n > 0 && i > 0 {
        i -= 1;
        buf[i] = b'0' + (n % 10) as u8;
        n /= 10;
    }
    serial_write(&buf[i..]);
}

fn serial_tx_empty() -> bool {
    unsafe { inb(0x3F8 + 5) & 0x20 != 0 }
}

unsafe fn outb(port: u16, val: u8) {
    asm!("out dx, al", in("dx") port, in("al") val, options(nomem, nostack, preserves_flags));
}

unsafe fn inb(port: u16) -> u8 {
    let val: u8;
    asm!("in al, dx", out("al") val, in("dx") port, options(nomem, nostack, preserves_flags));
    val
}

fn halt_loop() -> ! {
    loop {
        unsafe { asm!("hlt", options(nomem, nostack, preserves_flags)) };
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    serial_write(b"KARMAZYN_KENTRY_PANIC\n");
    halt_loop()
}
