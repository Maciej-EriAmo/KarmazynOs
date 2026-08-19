# Tor B — plan wdrożenia wzorca (Rust / rustc)

**Status:** living · **Data:** 2026-08-19  
**Wzorzec:** LFS / Gentoo stage1. Język = **Rust**. Slot `gcc` = **`rustc`**.  
**Nie:** C-world, C#, własny rustc z inercji, kcc jako „nasz gcc”.

Powiązania: [`TOR_B_TOOLCHAIN.pl.md`](TOR_B_TOOLCHAIN.pl.md) · [`KANON.md`](KANON.md) · `native/verify_rebuild.ps1`

---

## Mapa wdrożenia

| Faza | Co | Gate | Stan |
|------|----|------|------|
| **W1 Seed** | Kolejność crate’ów, docs (KANON/TOR_B) | `.\native\verify_rebuild.ps1` → `REBUILD_OK` | ✅ |
| **W2 Package set** | Cztery crate’y w kolejności (bez workspace — `target/` zostaje przy crate) | G0/CI: slab → substrate → shell → kcc | ✅ |
| **W3 Wire** | Bootstrap + G0/CI wołają ten sam zestaw | `bootstrap_from_scratch` · `gate_product` · `.github/workflows/gate.yml` | ✅ |
| **W4 Twin** | `verify_rebuild.sh` (Unix = Windows) | `./native/verify_rebuild.sh` | ✅ |
| **W5** | Własny rustc / chroot / „od środka” | — | **PLAN**, nie teraz |

C ABI (`c_smoke`) zostaje **opcjonalnym FFI** (`-SkipC` / `--skip-c`), nie pakietem worlda.

---

## Kolejność pakietów (jak LFS chapters)

```text
host rustc+cargo          ← stage0 (obce, jak host gcc)
    1. karmazyn_slab      ← prawo T×reach (no_std)
    2. karmazyn_substrate ← jądro host (zależne od slab)
    3. karmazyn_shell     ← narzędzie na substracie
    4. kcc                ← narzędzie w Rust (nie backend C)
```

Poza worldem (świadomie): `boot/kentry` (inny target), `karmazyn_substrate_rs` (PyO3 / minister Pythona).

---

## Zakaz w tej fali

1. Nie wstawiać C/gcc do ścieżki wzorca.  
2. Nie przebudowywać rustc / mrustc.  
3. Nie udawać, że K0→C zamyka Gentoo-stage1.  
4. Nie mieszać gate product (Python/Lua/Studio) z czystością łańcucha Rust.

---

## Po W4 (gdy wrócisz)

- Prefiks: `install_prefix` może dostać `kcc.exe` jako narzędzie — opc.  
- kentry w CI zostaje osobnym targetem, nie memberem default workspace.  
- W5 tylko świadomie.
