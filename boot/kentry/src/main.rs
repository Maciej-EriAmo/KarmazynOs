//! KarmazynOs kentry — Multiboot2 entry (faza F).
//!
//! MVP: po starcie pisze na COM1: `KARMAZYN_KENTRY_OK\n` i halt loop.
//! NIE ładuje Store / Pythona / Lua (L4 = osobna faza, po designie alokatora).
//!
//! Build (Linux lub cross):
//!   rustup target add x86_64-unknown-none
//!   cargo build --release --target x86_64-unknown-none
//!
//! Znak sukcesu SF.2: ten string na serialu w QEMU.

#![no_std]
#![no_main]

use core::arch::asm;
use core::panic::PanicInfo;

/// Multiboot2 header (spec: magic + arch + header_length + checksum + tags).
/// https://www.gnu.org/software/grub/manual/multiboot2/multiboot.html
const MB2_MAGIC: u32 = 0xE852_50D6;
const MB2_ARCH_I386: u32 = 0;
/// Fixed fields (16) + end tag (8) = 24; header must be 8-byte aligned.
const MB2_HEADER_LEN: u32 = 24;

#[repr(C, align(8))]
struct Multiboot2Header {
    magic: u32,
    architecture: u32,
    header_length: u32,
    checksum: u32,
    /// Terminating tag: type=0, flags=0, size=8
    end_type: u16,
    end_flags: u16,
    end_size: u32,
}

const _: () = assert!(core::mem::size_of::<Multiboot2Header>() == 24);
const _: () = assert!(core::mem::align_of::<Multiboot2Header>() >= 8);

/// magic + architecture + header_length + checksum == 0 (mod 2^32)
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

/// Public marker — must appear in binary / serial (SF.2 / SR.2).
pub const KENTRY_OK: &[u8] = b"KARMAZYN_KENTRY_OK\n";

#[no_mangle]
pub extern "C" fn _start() -> ! {
    // Multiboot2: eax=magic, ebx=info — ignore for MVP
    serial_init();
    serial_write(KENTRY_OK);
    halt_loop()
}

fn serial_init() {
    // COM1 0x3F8 — classic PC; enough for QEMU -serial stdio
    unsafe {
        outb(0x3F8 + 1, 0x00); // disable interrupts
        outb(0x3F8 + 3, 0x80); // DLAB on
        outb(0x3F8 + 0, 0x03); // divisor 3 → 38400
        outb(0x3F8 + 1, 0x00);
        outb(0x3F8 + 3, 0x03); // 8N1
        outb(0x3F8 + 2, 0xC7); // FIFO
        outb(0x3F8 + 4, 0x0B); // IRQs, RTS/DSR
    }
}

fn serial_write(bytes: &[u8]) {
    for &b in bytes {
        while !serial_tx_empty() {}
        unsafe { outb(0x3F8, b) };
    }
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
