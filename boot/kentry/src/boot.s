/* Multiboot2 wchodzi w 32-bit protected mode (PG=0, flat DS).
 * Ten plik podnosi long mode (tożsamościowe 1 GiB, 2 MiB strony) i woła kmain.
 * Adresy linkera = adresy fizyczne (VMA 1 MiB). Bez ISO, bez wyższej połowy.
 */
.section .text
.code32
.global _start
_start:
    cli
    cld
    movl %eax, mb_magic
    movl %ebx, mb_info

    lgdt gdt_desc
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    movw %ax, %fs
    movw %ax, %gs
    movl $stack_top, %esp

    /* SSE2: Rust (f64 w SlabStore) używa instrukcji XMM.
     * EM i TS zgaszone, inaczej pierwsza instrukcja XMM daje #UD/#NM. */
    movl %cr0, %eax
    andl $0xfffffff3, %eax
    orl $0x2, %eax
    movl %eax, %cr0
    movl %cr4, %eax
    orl $0x620, %eax
    movl %eax, %cr4

    movl $pml4, %eax
    movl %eax, %cr3

    movl $0xC0000080, %ecx
    rdmsr
    orl $0x100, %eax
    wrmsr

    movl %cr0, %eax
    orl $0x80000000, %eax
    movl %eax, %cr0

    /* EA rel16: selector 0x08, offset 32-bit — po skoku CPU jest w long mode. */
    .byte 0xEA
    .long long_mode_start
    .word 0x08

.code64
long_mode_start:
    clts
    cld
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %ss
    movw %ax, %fs
    movw %ax, %gs
    movq $stack_top, %rsp
    xorq %rbp, %rbp
    movl mb_magic(%rip), %edi
    movl mb_info(%rip), %esi
    call kmain
    cli
1:
    hlt
    jmp 1b

.section .data
.align 8
gdt_start:
    .quad 0
    .quad 0x00AF9A000000FFFF
    .quad 0x00CF92000000FFFF
gdt_end:

.align 4
gdt_desc:
    .word gdt_end - gdt_start - 1
    .long gdt_start

.align 4
mb_magic:
    .long 0
mb_info:
    .long 0

.align 4096
pml4:
    .quad pdpt + 3
    .fill 511, 8, 0
.align 4096
pdpt:
    .quad pd + 3
    .fill 511, 8, 0
.align 4096
pd:
    .set page_i, 0
    .rept 512
    .quad (page_i << 21) | 0x83
    .set page_i, page_i + 1
    .endr

.section .bss
.align 16
/* kmain trzyma na stosie ok. 90 KiB (kopia SlabStore). 16 KiB wchodziło w .text. */
.skip 262144
.global stack_top
stack_top:

/* QEMU -kernel (11.x) ładuje ELF przez PVH, nie przez Multiboot2.
 * Notatka: XEN_ELFNOTE_PHYS32_ENTRY (18) → _start, adres 32-bit w polu 64-bit.
 */
.section .note.Xen, "a", @note
.align 4
.long 4
.long 8
.long 18
.asciz "Xen"
.align 4
.quad _start
.align 4
