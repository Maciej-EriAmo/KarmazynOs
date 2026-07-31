/* Minimal linker script for Multiboot2 ELF (x86_64) */
ENTRY(_start)

SECTIONS
{
  . = 1M;

  .boot : ALIGN(8)
  {
    KEEP(*(.multiboot_header))
  }

  .text : ALIGN(4K)
  {
    *(.text .text.*)
  }

  .rodata : ALIGN(4K)
  {
    *(.rodata .rodata.*)
  }

  .data : ALIGN(4K)
  {
    *(.data .data.*)
  }

  .bss : ALIGN(4K)
  {
    *(.bss .bss.*)
    *(COMMON)
  }
}
