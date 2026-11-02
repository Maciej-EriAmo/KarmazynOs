//! Formatowanie pustego dysku na ext3 (rev 1 z dziennikiem), które jądro
//! montuje jako ext4.
//!
//! Płyta nie ma `mke2fs`, a świat KAFD ma leżeć jako plik na systemie plików
//! jądra. To minimalny, standardowy układ:
//!
//! - blok 4096 B, `first_data_block = 0`, 32768 bloków na grupę;
//! - w każdej grupie: superblok (kopia), tablica deskryptorów, mapa bloków,
//!   mapa i-węzłów, tablica i-węzłów (2048 × 128 B), dane;
//! - cechy: `HAS_JOURNAL` (compat), `FILETYPE` (incompat), `LARGE_FILE`
//!   (ro_compat); bez extents i sum kontrolnych grup;
//! - katalog główny (i-węzeł 2), `lost+found` (i-węzeł 11) i dziennik JBD2
//!   (i-węzeł 8): pusty i czysty, rozmiar jak w `mke2fs`, bloki ciągłe w
//!   grupie 0 za katalogami, mapowane blokami pośrednimi jak w ext3.
//!
//! Bez dziennika jądro po twardym wyłączeniu montowało dysk jako
//! „unchecked fs”; z dziennikiem odtwarza ostatnią transakcję samo.

use std::io::{self, Seek, SeekFrom, Write};

pub const BLOCK: u64 = 4096;
const BLOCKS_PER_GROUP: u64 = BLOCK * 8;
const INODES_PER_GROUP: u64 = 2048;
const INODE_SIZE: u64 = 128;
const ITABLE_BLOCKS: u64 = INODES_PER_GROUP * INODE_SIZE / BLOCK;
const FIRST_INO: u32 = 11;
const ROOT_INO: u32 = 2;
const JOURNAL_INO: u32 = 8;
const LF_INO: u32 = 11;
pub const MAGIC: u16 = 0xEF53;
/// JBD2 nie przyjmie krótszego dziennika (`JBD2_MIN_JOURNAL_BLOCKS`).
const JOURNAL_MIN: u64 = 1024;
const JBD2_MAGIC: u32 = 0xC03B_3998;
const JBD2_SUPERBLOCK_V2: u32 = 4;
/// Wskaźników w bloku pośrednim (4096 / 4).
const PTRS: u64 = BLOCK / 4;

/// Układ systemu plików dla urządzenia o danym rozmiarze.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Layout {
    pub blocks: u64,
    pub groups: u64,
    pub gdt_blocks: u64,
    /// Bloki danych dziennika (0 = dysk za mały, ext2 bez dziennika).
    pub journal_blocks: u64,
}

impl Layout {
    pub fn for_size(bytes: u64) -> io::Result<Layout> {
        let mut blocks = bytes / BLOCK;
        let overhead = |gdt: u64| 1 + gdt + 2 + ITABLE_BLOCKS;
        loop {
            let groups = blocks.div_ceil(BLOCKS_PER_GROUP).max(1);
            let gdt_blocks = (groups * 32).div_ceil(BLOCK);
            let last = blocks - (groups - 1) * BLOCKS_PER_GROUP;
            // ostatnia grupa musi zmieścić metadane i trochę danych
            if last < overhead(gdt_blocks) + 16 {
                if groups == 1 {
                    return Err(io::Error::other(format!(
                        "dysk za mały na ext2 ({bytes} B)"
                    )));
                }
                blocks = (groups - 1) * BLOCKS_PER_GROUP;
                continue;
            }
            let mut l = Layout {
                blocks,
                groups,
                gdt_blocks,
                journal_blocks: 0,
            };
            l.journal_blocks = l.fit_journal();
            return Ok(l);
        }
    }

    /// Rozmiar dziennika jak `ext2fs_default_journal_size`, przycięty do
    /// tego, co mieści grupa 0 za metadanymi i dwoma katalogami.
    fn fit_journal(&self) -> u64 {
        let mut n = match self.blocks {
            b if b < 2048 => return 0,
            b if b < 32_768 => 1024,
            b if b < 256 * 1024 => 4096,
            b if b < 512 * 1024 => 8192,
            _ => 16_384,
        };
        let room = self.group_blocks(0) - self.overhead() - 2;
        while n >= JOURNAL_MIN {
            if n + journal_meta(n) + 16 <= room {
                return n;
            }
            n /= 2;
        }
        0
    }

    fn group_start(&self, g: u64) -> u64 {
        g * BLOCKS_PER_GROUP
    }

    fn group_blocks(&self, g: u64) -> u64 {
        (self.blocks - self.group_start(g)).min(BLOCKS_PER_GROUP)
    }

    fn block_bitmap(&self, g: u64) -> u64 {
        self.group_start(g) + 1 + self.gdt_blocks
    }

    fn inode_bitmap(&self, g: u64) -> u64 {
        self.block_bitmap(g) + 1
    }

    fn inode_table(&self, g: u64) -> u64 {
        self.inode_bitmap(g) + 1
    }

    fn data_start(&self, g: u64) -> u64 {
        self.inode_table(g) + ITABLE_BLOCKS
    }

    fn overhead(&self) -> u64 {
        1 + self.gdt_blocks + 2 + ITABLE_BLOCKS
    }

    /// Zajęte bloki grupy `g` od jej początku (grupa 0: katalogi i dziennik).
    fn used(&self, g: u64) -> u64 {
        if g == 0 {
            self.overhead() + 2 + self.journal_blocks + journal_meta(self.journal_blocks)
        } else {
            self.overhead()
        }
    }
}

/// Bloki pośrednie potrzebne na `n` bloków danych (12 bezpośrednich,
/// pojedynczy pośredni, podwójny pośredni).
fn journal_meta(n: u64) -> u64 {
    if n <= 12 {
        return 0;
    }
    let rest = n - 12;
    if rest <= PTRS {
        return 1;
    }
    1 + 1 + (rest - PTRS).div_ceil(PTRS)
}

/// Mapowanie dziennika: dane w `data..data+n`, bloki pośrednie od `meta`.
/// Zwraca `i_block[15]` i treść bloków pośrednich (numer bloku, zawartość).
fn journal_map(n: u64, data: u64, meta: u64) -> ([u32; 15], Vec<(u64, Vec<u8>)>) {
    /// Blok pośredni pod numerem `*next` ze wskaźnikami na dane `from..from+count`.
    fn ind(next: &mut u64, data: u64, from: u64, count: u64, out: &mut Vec<(u64, Vec<u8>)>) -> u64 {
        let blk = *next;
        *next += 1;
        let mut b = vec![0u8; BLOCK as usize];
        for j in 0..count {
            put32(&mut b, (j * 4) as usize, (data + from + j) as u32);
        }
        out.push((blk, b));
        blk
    }
    let mut iblock = [0u32; 15];
    let mut out = Vec::new();
    for (k, slot) in iblock.iter_mut().take(12).enumerate() {
        if (k as u64) < n {
            *slot = (data + k as u64) as u32;
        }
    }
    let mut next = meta;
    if n > 12 {
        iblock[12] = ind(&mut next, data, 12, (n - 12).min(PTRS), &mut out) as u32;
    }
    if n > 12 + PTRS {
        let dind = next;
        next += 1;
        let mut d = vec![0u8; BLOCK as usize];
        let mut from = 12 + PTRS;
        let mut j = 0;
        while from < n {
            let count = (n - from).min(PTRS);
            let child = ind(&mut next, data, from, count, &mut out);
            put32(&mut d, j * 4, child as u32);
            from += count;
            j += 1;
        }
        out.push((dind, d));
        iblock[13] = dind as u32;
    }
    (iblock, out)
}

fn journal_inode(n: u64, iblock: &[u32; 15], now: u32) -> [u8; INODE_SIZE as usize] {
    let mut i = [0u8; INODE_SIZE as usize];
    put16(&mut i, 0, 0o100600);
    put32(&mut i, 4, (n * BLOCK) as u32);
    for o in [8, 12, 16] {
        put32(&mut i, o, now);
    }
    put16(&mut i, 26, 1);
    put32(&mut i, 28, ((n + journal_meta(n)) * (BLOCK / 512)) as u32);
    for (k, b) in iblock.iter().enumerate() {
        put32(&mut i, 40 + k * 4, *b);
    }
    i
}

/// Superblok JBD2 (big-endian): pusty, czysty dziennik (`s_start = 0`).
fn journal_superblock(n: u64, uuid: [u8; 16]) -> Vec<u8> {
    let mut j = vec![0u8; BLOCK as usize];
    let be = |j: &mut [u8], o: usize, v: u32| j[o..o + 4].copy_from_slice(&v.to_be_bytes());
    be(&mut j, 0, JBD2_MAGIC);
    be(&mut j, 4, JBD2_SUPERBLOCK_V2);
    be(&mut j, 12, BLOCK as u32); // s_blocksize
    be(&mut j, 16, n as u32); // s_maxlen
    be(&mut j, 20, 1); // s_first
    be(&mut j, 24, 1); // s_sequence
    j[48..64].copy_from_slice(&uuid);
    be(&mut j, 64, 1); // s_nr_users
    j
}

fn put16(b: &mut [u8], o: usize, v: u16) {
    b[o..o + 2].copy_from_slice(&v.to_le_bytes());
}

fn put32(b: &mut [u8], o: usize, v: u32) {
    b[o..o + 4].copy_from_slice(&v.to_le_bytes());
}

fn set_bit(bm: &mut [u8], i: u64) {
    bm[(i / 8) as usize] |= 1 << (i % 8);
}

fn dirent(block: &mut [u8], off: usize, ino: u32, rec_len: u16, name: &str) -> usize {
    put32(block, off, ino);
    put16(block, off + 4, rec_len);
    block[off + 6] = name.len() as u8;
    block[off + 7] = 2; // katalog
    block[off + 8..off + 8 + name.len()].copy_from_slice(name.as_bytes());
    off + rec_len as usize
}

fn dir_inode(mode: u16, links: u16, block: u64, now: u32) -> [u8; INODE_SIZE as usize] {
    let mut i = [0u8; INODE_SIZE as usize];
    put16(&mut i, 0, mode);
    put32(&mut i, 4, BLOCK as u32);
    for o in [8, 12, 16] {
        put32(&mut i, o, now);
    }
    put16(&mut i, 26, links);
    put32(&mut i, 28, (BLOCK / 512) as u32);
    put32(&mut i, 40, block as u32);
    i
}

/// Superblok (1024 B) dla grupy `g`. `jnl` = `i_block` i-węzła dziennika.
#[allow(clippy::too_many_arguments)]
fn superblock(
    l: &Layout,
    g: u64,
    free_blocks: u64,
    free_inodes: u64,
    now: u32,
    uuid: [u8; 16],
    jnl: &[u32; 15],
) -> [u8; 1024] {
    let mut s = [0u8; 1024];
    put32(&mut s, 0, (l.groups * INODES_PER_GROUP) as u32);
    put32(&mut s, 4, l.blocks as u32);
    put32(&mut s, 12, free_blocks as u32);
    put32(&mut s, 16, free_inodes as u32);
    put32(&mut s, 20, 0); // first_data_block
    put32(&mut s, 24, 2); // log_block_size: 1024 << 2
    put32(&mut s, 28, 2);
    put32(&mut s, 32, BLOCKS_PER_GROUP as u32);
    put32(&mut s, 36, BLOCKS_PER_GROUP as u32);
    put32(&mut s, 40, INODES_PER_GROUP as u32);
    put32(&mut s, 48, now);
    put16(&mut s, 54, 0xFFFF); // max_mnt_count: bez wymuszonego fsck
    put16(&mut s, 56, MAGIC);
    put16(&mut s, 58, 1); // czysty
    put16(&mut s, 60, 1); // błędy: kontynuuj
    put32(&mut s, 64, now);
    put32(&mut s, 76, 1); // rev 1 (dynamic)
    put32(&mut s, 84, FIRST_INO);
    put16(&mut s, 88, INODE_SIZE as u16);
    put16(&mut s, 90, g as u16);
    put32(&mut s, 96, 0x0002); // INCOMPAT_FILETYPE
    put32(&mut s, 100, 0x0002); // RO_COMPAT_LARGE_FILE
    s[104..120].copy_from_slice(&uuid);
    s[120..128].copy_from_slice(b"karmazyn");
    if l.journal_blocks > 0 {
        put32(&mut s, 92, 0x0004); // COMPAT_HAS_JOURNAL
        put32(&mut s, 224, JOURNAL_INO); // s_journal_inum
        // kopia mapowania dziennika dla e2fsck (EXT3_JNL_BACKUP_BLOCKS)
        s[253] = 1;
        for (k, b) in jnl.iter().enumerate() {
            put32(&mut s, 268 + k * 4, *b);
        }
        put32(&mut s, 268 + 16 * 4, (l.journal_blocks * BLOCK) as u32);
    }
    s
}

/// Zapisuje cały system plików na `dev` (urządzenie albo plik o rozmiarze `size`).
/// Bloki danych nie są zerowane (jak `mke2fs` na dysku z TRIM): ext2 ich nie czyta,
/// dopóki nie są przydzielone.
pub fn format<D: Write + Seek>(dev: &mut D, size: u64, now: u32, uuid: [u8; 16]) -> io::Result<Layout> {
    let l = Layout::for_size(size)?;
    let root_blk = l.data_start(0);
    let lf_blk = root_blk + 1;
    let jdata = lf_blk + 1;
    let (jnl, jmeta) = if l.journal_blocks > 0 {
        journal_map(l.journal_blocks, jdata, jdata + l.journal_blocks)
    } else {
        ([0u32; 15], Vec::new())
    };

    let mut free_blocks_total = 0;
    let mut gdt = vec![0u8; (l.gdt_blocks * BLOCK) as usize];
    for g in 0..l.groups {
        let free_b = l.group_blocks(g) - l.used(g);
        let free_i = INODES_PER_GROUP - if g == 0 { u64::from(FIRST_INO) } else { 0 };
        free_blocks_total += free_b;
        let d = &mut gdt[(g * 32) as usize..(g * 32 + 32) as usize];
        put32(d, 0, l.block_bitmap(g) as u32);
        put32(d, 4, l.inode_bitmap(g) as u32);
        put32(d, 8, l.inode_table(g) as u32);
        put16(d, 12, free_b as u16);
        put16(d, 14, free_i as u16);
        put16(d, 16, if g == 0 { 2 } else { 0 });
    }
    let free_inodes_total = l.groups * INODES_PER_GROUP - u64::from(FIRST_INO);

    let at = |dev: &mut D, block: u64, data: &[u8]| -> io::Result<()> {
        dev.seek(SeekFrom::Start(block * BLOCK))?;
        dev.write_all(data)
    };

    for g in 0..l.groups {
        let start = l.group_start(g);
        let sb = superblock(&l, g, free_blocks_total, free_inodes_total, now, uuid, &jnl);
        let mut first = vec![0u8; BLOCK as usize];
        if g == 0 {
            first[1024..2048].copy_from_slice(&sb);
        } else {
            first[..1024].copy_from_slice(&sb);
        }
        at(dev, start, &first)?;
        at(dev, start + 1, &gdt)?;

        let mut bbm = vec![0u8; BLOCK as usize];
        for i in 0..l.used(g) {
            set_bit(&mut bbm, i);
        }
        for i in l.group_blocks(g)..BLOCKS_PER_GROUP {
            set_bit(&mut bbm, i); // poza końcem urządzenia
        }
        at(dev, l.block_bitmap(g), &bbm)?;

        let mut ibm = vec![0u8; BLOCK as usize];
        if g == 0 {
            for i in 0..u64::from(FIRST_INO) {
                set_bit(&mut ibm, i);
            }
        }
        for i in INODES_PER_GROUP..BLOCK * 8 {
            set_bit(&mut ibm, i); // dopełnienie mapy
        }
        at(dev, l.inode_bitmap(g), &ibm)?;

        let mut itable = vec![0u8; (ITABLE_BLOCKS * BLOCK) as usize];
        if g == 0 {
            let put = |t: &mut [u8], ino: u32, raw: &[u8]| {
                let o = ((ino - 1) as u64 * INODE_SIZE) as usize;
                t[o..o + INODE_SIZE as usize].copy_from_slice(raw);
            };
            put(&mut itable, ROOT_INO, &dir_inode(0o040755, 3, root_blk, now));
            put(&mut itable, LF_INO, &dir_inode(0o040700, 2, lf_blk, now));
            if l.journal_blocks > 0 {
                put(&mut itable, JOURNAL_INO, &journal_inode(l.journal_blocks, &jnl, now));
            }
        }
        at(dev, l.inode_table(g), &itable)?;
    }

    let mut root = vec![0u8; BLOCK as usize];
    let o = dirent(&mut root, 0, ROOT_INO, 12, ".");
    let o = dirent(&mut root, o, ROOT_INO, 12, "..");
    dirent(&mut root, o, LF_INO, (BLOCK as usize - o) as u16, "lost+found");
    at(dev, root_blk, &root)?;
    let mut lf = vec![0u8; BLOCK as usize];
    let o = dirent(&mut lf, 0, LF_INO, 12, ".");
    dirent(&mut lf, o, ROOT_INO, (BLOCK as usize - o) as u16, "..");
    at(dev, lf_blk, &lf)?;

    if l.journal_blocks > 0 {
        // dziennik wyzerowany (jak mke2fs bez lazy_journal_init), potem jego superblok
        let zero = vec![0u8; (256 * BLOCK) as usize];
        let mut b = 0;
        while b < l.journal_blocks {
            let k = (l.journal_blocks - b).min(256);
            at(dev, jdata + b, &zero[..(k * BLOCK) as usize])?;
            b += k;
        }
        at(dev, jdata, &journal_superblock(l.journal_blocks, uuid))?;
        for (blk, data) in &jmeta {
            at(dev, *blk, data)?;
        }
    }
    dev.flush()?;
    Ok(l)
}

/// Czy pod offsetem 1024 leży superblok ext2/3/4.
#[cfg(test)]
pub fn has_ext_superblock(first_2k: &[u8]) -> bool {
    first_2k.len() >= 1082 && u16::from_le_bytes([first_2k[1080], first_2k[1081]]) == MAGIC
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn le32(b: &[u8], o: usize) -> u32 {
        u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
    }
    fn le16(b: &[u8], o: usize) -> u16 {
        u16::from_le_bytes(b[o..o + 2].try_into().unwrap())
    }

    #[test]
    fn small_disk_one_group() {
        let size = 16 << 20;
        let mut dev = Cursor::new(vec![0u8; size as usize]);
        let l = format(&mut dev, size, 1_700_000_000, [7; 16]).unwrap();
        assert_eq!((l.blocks, l.groups, l.gdt_blocks), (4096, 1, 1));
        assert_eq!(l.journal_blocks, 1024);
        let img = dev.into_inner();
        assert!(has_ext_superblock(&img[..2048]));
        let sb = &img[1024..2048];
        assert_eq!(le32(sb, 4), 4096);
        assert_eq!(le32(sb, 0), 2048);
        // wolne = 4096 − (1 sb + 1 gdt + 2 mapy + 64 i-węzły + 2 katalogi
        //                + 1024 dziennik + 1 blok pośredni)
        assert_eq!(le32(sb, 12), 4096 - 70 - 1025);
        assert_eq!(le32(sb, 92), 0x0004);
        assert_eq!(le32(sb, 224), 8);
        assert_eq!(le32(sb, 16), 2048 - 11);
        // deskryptor grupy 0
        let gd = &img[4096..4096 + 32];
        assert_eq!((le32(gd, 0), le32(gd, 4), le32(gd, 8)), (2, 3, 4));
        assert_eq!(le16(gd, 16), 2);
        // i-węzeł 2: katalog z blokiem danych 68
        let ino2 = &img[(4 * 4096 + 128) as usize..(4 * 4096 + 256) as usize];
        assert_eq!(le16(ino2, 0), 0o040755);
        assert_eq!(le32(ino2, 40), 68);
        // wpisy katalogu głównego: ".", "..", "lost+found" do końca bloku
        let root = &img[68 * 4096..69 * 4096];
        assert_eq!(&root[8..9], b".");
        assert_eq!(&root[24 + 8..24 + 18], b"lost+found");
        assert_eq!(le16(root, 24 + 4) as usize, 4096 - 24);
        // mapa bloków: 1095 pierwszych zajętych (136 pełnych bajtów + 7 bitów),
        // reszta grupy poza dyskiem zajęta
        let bbm = &img[2 * 4096..3 * 4096];
        assert_eq!(bbm[0..136], [0xff; 136]);
        assert_eq!(bbm[136], 0b0111_1111);
        assert_eq!(bbm[137], 0);
        assert_eq!(bbm[512], 0xff);
        // i-węzeł 8: dziennik, 1024 bloki od 70, pośredni w 1094
        let ino8 = &img[(4 * 4096 + 7 * 128) as usize..(4 * 4096 + 8 * 128) as usize];
        assert_eq!(le16(ino8, 0), 0o100600);
        assert_eq!(le32(ino8, 4), 1024 * 4096);
        assert_eq!(le32(ino8, 40), 70);
        assert_eq!(le32(ino8, 40 + 11 * 4), 81);
        assert_eq!(le32(ino8, 40 + 12 * 4), 1094);
        let ind = &img[1094 * 4096..1095 * 4096];
        assert_eq!(le32(ind, 0), 82);
        assert_eq!(le32(ind, 1011 * 4), 70 + 1023);
        assert_eq!(le32(ind, 1012 * 4), 0);
        // superblok JBD2 w pierwszym bloku dziennika, pusty
        let j = &img[70 * 4096..71 * 4096];
        assert_eq!(u32::from_be_bytes(j[0..4].try_into().unwrap()), 0xC03B_3998);
        assert_eq!(u32::from_be_bytes(j[16..20].try_into().unwrap()), 1024);
        assert_eq!(u32::from_be_bytes(j[28..32].try_into().unwrap()), 0);
        // kopia mapowania w superbloku
        assert_eq!(le32(sb, 268), 70);
        assert_eq!(le32(sb, 268 + 16 * 4), 1024 * 4096);
    }

    /// Każdy logiczny blok dziennika trafia w swój blok danych, także przez
    /// podwójny blok pośredni.
    #[test]
    fn journal_map_resolves_every_block() {
        for n in [1024u64, 4096, 16_384] {
            let data = 1000;
            let meta = data + n;
            let (ib, metas) = journal_map(n, data, meta);
            assert_eq!(metas.len() as u64, journal_meta(n));
            let block = |b: u32| -> &Vec<u8> {
                &metas.iter().find(|(k, _)| *k == u64::from(b)).unwrap().1
            };
            for lg in 0..n {
                let phys = if lg < 12 {
                    ib[lg as usize]
                } else if lg < 12 + PTRS {
                    le32(block(ib[12]), ((lg - 12) * 4) as usize)
                } else {
                    let r = lg - 12 - PTRS;
                    let ind = le32(block(ib[13]), ((r / PTRS) * 4) as usize);
                    le32(block(ind), ((r % PTRS) * 4) as usize)
                };
                assert_eq!(u64::from(phys), data + lg, "n={n} lg={lg}");
            }
            // bloki pośrednie leżą tuż za danymi, bez dziur
            let mut nums: Vec<u64> = metas.iter().map(|(k, _)| *k).collect();
            nums.sort();
            assert_eq!(nums, (meta..meta + journal_meta(n)).collect::<Vec<_>>());
        }
    }

    #[test]
    fn large_disk_many_groups_drops_tiny_tail() {
        // 3 grupy + ogon za mały na metadane (10 bloków) → ogon odpada
        let size = (3 * BLOCKS_PER_GROUP + 10) * BLOCK;
        let l = Layout::for_size(size).unwrap();
        assert_eq!((l.groups, l.blocks), (3, 3 * BLOCKS_PER_GROUP));
        assert!(Layout::for_size(64 * BLOCK).is_err());
        assert_eq!(Layout::for_size(1 << 30).unwrap().groups, 8);
        assert_eq!(Layout::for_size(1 << 30).unwrap().journal_blocks, 8192);
        // za mały na dziennik: ext2 bez niego
        assert_eq!(Layout::for_size(1500 * BLOCK).unwrap().journal_blocks, 0);
    }
}
