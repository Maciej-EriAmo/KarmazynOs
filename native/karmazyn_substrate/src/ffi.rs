//! C ABI — stable seam for Python (ctypes/cffi) and future hosts.
//!
//! Handles are opaque u64 store pointers. Bubble/atom ids are u32.
//! Language payloads are opaque u64 tokens (e.g. Python id(obj)).

use crate::store::Store;
use crate::ABI_VERSION;
use std::ffi::{c_char, CStr, CString};
use std::os::raw::c_int;
use std::ptr;
use std::sync::Mutex;

/// Slot tablicy uchwytów. `gen` rośnie przy każdym ponownym użyciu slotu.
struct Slot {
    gen: u32,
    store: Option<Store>,
}

/// Global table: store_handle → Store.
/// Handle = `(gen << 32) | (index + 1)`: never 0. A freed slot is reused with
/// gen + 1, so a stale handle no longer resolves to the new store (no ABA).
/// The first store in a slot has gen 0, so its handle is just `index + 1`.
static STORES: Mutex<Vec<Slot>> = Mutex::new(Vec::new());

fn encode_handle(idx: usize, gen: u32) -> u64 {
    (u64::from(gen) << 32) | (idx as u64 + 1)
}

/// Slot index of a live handle (index and generation match).
fn slot_of(slots: &[Slot], handle: u64) -> Option<usize> {
    let low = handle & 0xFFFF_FFFF;
    let idx = usize::try_from(low.checked_sub(1)?).ok()?;
    let gen = (handle >> 32) as u32;
    let slot = slots.get(idx)?;
    (slot.gen == gen && slot.store.is_some()).then_some(idx)
}

fn with_store<R>(handle: u64, f: impl FnOnce(&Store) -> R) -> Option<R> {
    // Klon Arc i puszczenie zamka STORES zanim wejdziemy w callback.
    // Hak env_of/extra_reach wołany z tick może znów wejść w ksub_*.
    let store = {
        let g = STORES.lock().ok()?;
        let idx = slot_of(&g, handle)?;
        g[idx].store.clone()?
    };
    Some(f(&store))
}

/// Slot index for a live handle, or None (0, freed, stale).
fn live_index(handle: u64) -> Option<usize> {
    let g = STORES.lock().ok()?;
    slot_of(&g, handle)
}

fn with_store_mut<R>(handle: u64, f: impl FnOnce(&Store) -> R) -> Option<R> {
    with_store(handle, f)
}

// ── version / lifecycle ─────────────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn ksub_version() -> *const c_char {
    ABI_VERSION.as_ptr() as *const c_char
}

#[no_mangle]
pub extern "C" fn ksub_store_new(thermal: c_int) -> u64 {
    let Ok(mut g) = STORES.lock() else {
        return 0;
    };
    let store = Some(Store::new(thermal != 0));
    if let Some(i) = g.iter().position(|s| s.store.is_none()) {
        let gen = g[i].gen.wrapping_add(1);
        g[i] = Slot { gen, store };
        return encode_handle(i, gen);
    }
    if g.len() >= u32::MAX as usize {
        return 0;
    }
    g.push(Slot { gen: 0, store });
    encode_handle(g.len() - 1, 0)
}

#[no_mangle]
pub extern "C" fn ksub_store_free(handle: u64) {
    // Nieaktualny albo podwójnie zwolniony uchwyt nic nie robi.
    let Some(idx) = live_index(handle) else {
        return;
    };
    // Ta sama kolejność co ksub_register_*: HOOKS, potem STORES.
    if let Ok(mut hooks) = HOOKS.lock() {
        if idx < hooks.len() {
            hooks[idx] = None;
        }
    }
    if let Ok(mut g) = STORES.lock() {
        if slot_of(&g, handle) == Some(idx) {
            g[idx].store = None;
        }
    }
}

// ── atoms ───────────────────────────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn ksub_atom_new(
    handle: u64,
    s: *const c_char,
    e: *const c_char,
    t: f64,
) -> u32 {
    let s = unsafe { cstr(s) };
    let e = unsafe { cstr(e) };
    with_store(handle, |st| st.atom_new(&s, &e, t)).unwrap_or(u32::MAX)
}

#[no_mangle]
pub extern "C" fn ksub_atom_set_value(handle: u64, aid: u32, token: u64) -> c_int {
    with_store(handle, |st| st.atom_set_value_token(aid, token) as c_int).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_atom_value(handle: u64, aid: u32) -> u64 {
    with_store(handle, |st| st.atom_value_token(aid).unwrap_or(0)).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_has_atom(handle: u64, aid: u32) -> c_int {
    with_store(handle, |st| st.has_atom(aid) as c_int).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_delete_atom(handle: u64, aid: u32) -> c_int {
    with_store(handle, |st| st.delete_atom(aid) as c_int).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_heat(handle: u64, aid: u32) -> c_int {
    with_store(handle, |st| st.heat(aid) as c_int).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_atom_t(handle: u64, aid: u32) -> f64 {
    with_store(handle, |st| st.get_atom_t(aid).unwrap_or(-1.0)).unwrap_or(-1.0)
}

#[no_mangle]
pub extern "C" fn ksub_atom_set_t(handle: u64, aid: u32, t: f64) -> c_int {
    with_store(handle, |st| st.atom_set_t(aid, t) as c_int).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_atom_is_dead(handle: u64, aid: u32) -> c_int {
    with_store(handle, |st| {
        st.atom_is_dead(aid).map(|d| d as c_int).unwrap_or(-1)
    })
    .unwrap_or(-1)
}

/// Upsert atom with fixed id. Returns 1 on success.
#[no_mangle]
pub extern "C" fn ksub_atom_upsert(
    handle: u64,
    aid: u32,
    s: *const c_char,
    e: *const c_char,
    t: f64,
    token: u64,
) -> c_int {
    let s = unsafe { cstr(s) };
    let e = unsafe { cstr(e) };
    with_store(handle, |st| st.atom_upsert(aid, &s, &e, t, token) as c_int).unwrap_or(0)
}

/// Fill `out` with up to `max_out` atom ids.
/// Returns the total number of ids (may be larger than `max_out`), or -1.
/// `max_out == 0` returns the total without writing.
#[no_mangle]
pub extern "C" fn ksub_atom_ids(handle: u64, out: *mut u32, max_out: u32) -> i32 {
    if out.is_null() && max_out > 0 {
        return -1;
    }
    with_store(handle, |st| {
        let ids = st.atom_ids();
        let total = ids.len();
        let n = total.min(max_out as usize);
        if n > 0 && !out.is_null() {
            unsafe {
                std::ptr::copy_nonoverlapping(ids.as_ptr(), out, n);
            }
        }
        total as i32
    })
    .unwrap_or(-1)
}

// ── bubbles ─────────────────────────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn ksub_bubble_new(handle: u64, label: *const c_char, parent: i64) -> u32 {
    let label = unsafe { cstr(label) };
    let parent = if parent < 0 {
        None
    } else {
        Some(parent as u32)
    };
    with_store(handle, |st| st.bubble_new(&label, parent)).unwrap_or(u32::MAX)
}

#[no_mangle]
pub extern "C" fn ksub_bind(handle: u64, bid: u32, name: *const c_char, aid: u32) -> c_int {
    let name = unsafe { cstr(name) };
    with_store(handle, |st| match st.bind(bid, &name, aid) {
        Ok(()) => 1,
        Err(_) => 0,
    })
    .unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn ksub_lookup(handle: u64, bid: u32, name: *const c_char) -> i64 {
    let name = unsafe { cstr(name) };
    with_store(handle, |st| {
        st.lookup(bid, &name).map(|a| a as i64).unwrap_or(-1)
    })
    .unwrap_or(-1)
}

#[no_mangle]
pub extern "C" fn ksub_unbind(handle: u64, bid: u32, name: *const c_char) -> i64 {
    let name = unsafe { cstr(name) };
    with_store(handle, |st| {
        st.unbind(bid, &name)
            .map(|a| a as i64)
            .unwrap_or(-1)
    })
    .unwrap_or(-1)
}

#[no_mangle]
pub extern "C" fn ksub_set_root(handle: u64, bid: u32) {
    let _ = with_store(handle, |st| st.set_root(bid));
}

#[no_mangle]
pub extern "C" fn ksub_unset_root(handle: u64, bid: u32) {
    let _ = with_store(handle, |st| st.unset_root(bid));
}

// ── tick / stats ────────────────────────────────────────────────────────────

#[no_mangle]
pub extern "C" fn ksub_tick(handle: u64) {
    let _ = with_store(handle, |st| st.tick());
}

#[no_mangle]
pub extern "C" fn ksub_settle(handle: u64, n: u32) {
    let _ = with_store(handle, |st| st.settle(n));
}

#[repr(C)]
pub struct KSubStats {
    pub total: u64,
    pub hot: u64,
    pub warm: u64,
    pub cold: u64,
    pub tomb: u64,
    pub alive: u64,
    pub dead: u64,
    pub reaped: u64,
    pub retained_tomb: u64,
    pub bubbles: u64,
}

#[no_mangle]
pub extern "C" fn ksub_stats(handle: u64, out: *mut KSubStats) -> c_int {
    if out.is_null() {
        return 0;
    }
    match with_store(handle, |st| st.stats()) {
        Some(s) => {
            unsafe {
                *out = KSubStats {
                    total: s.total as u64,
                    hot: s.hot as u64,
                    warm: s.warm as u64,
                    cold: s.cold as u64,
                    tomb: s.tomb as u64,
                    alive: s.alive as u64,
                    dead: s.dead as u64,
                    reaped: s.reaped,
                    retained_tomb: s.retained_tomb as u64,
                    bubbles: s.bubbles as u64,
                };
            }
            1
        }
        None => 0,
    }
}

// ── hooks (function pointers; host keeps data in token space) ───────────────

/// env_of callback: (value_token, userdata) -> bubble_id (0 = none)
pub type EnvOfC = Option<extern "C" fn(u64, *mut std::ffi::c_void) -> u32>;
/// extra_reach: write up to max_out ids into out; return count
pub type ExtraReachC =
    Option<extern "C" fn(out: *mut u32, max_out: u32, userdata: *mut std::ffi::c_void) -> u32>;

struct HookCtx {
    env_of: EnvOfC,
    env_ud: usize,
    extra: ExtraReachC,
    extra_ud: usize,
}

// Per-store hook context (parallel to STORES indices).
static HOOKS: Mutex<Vec<Option<HookCtx>>> = Mutex::new(Vec::new());

#[no_mangle]
pub extern "C" fn ksub_register_env_of(
    handle: u64,
    cb: EnvOfC,
    userdata: *mut std::ffi::c_void,
) -> c_int {
    let Some(idx) = live_index(handle) else {
        return 0;
    };
    let ud = userdata as usize;
    let Ok(mut hooks) = HOOKS.lock() else {
        return 0;
    };
    while hooks.len() <= idx {
        hooks.push(None);
    }
    let entry = hooks[idx].get_or_insert(HookCtx {
        env_of: None,
        env_ud: 0,
        extra: None,
        extra_ud: 0,
    });
    entry.env_of = cb;
    entry.env_ud = ud;

    let env_of = cb;
    let env_ud = ud;
    with_store_mut(handle, |st| {
        st.unregister_env_of("c_abi");
        if let Some(f) = env_of {
            st.register_env_of("c_abi", move |tok| {
                let b = f(tok, env_ud as *mut std::ffi::c_void);
                if b == 0 {
                    None
                } else {
                    Some(b)
                }
            });
        }
    });
    1
}

#[no_mangle]
pub extern "C" fn ksub_register_extra_reach(
    handle: u64,
    cb: ExtraReachC,
    userdata: *mut std::ffi::c_void,
) -> c_int {
    let Some(idx) = live_index(handle) else {
        return 0;
    };
    let ud = userdata as usize;
    let Ok(mut hooks) = HOOKS.lock() else {
        return 0;
    };
    while hooks.len() <= idx {
        hooks.push(None);
    }
    let entry = hooks[idx].get_or_insert(HookCtx {
        env_of: None,
        env_ud: 0,
        extra: None,
        extra_ud: 0,
    });
    entry.extra = cb;
    entry.extra_ud = ud;

    let extra = cb;
    let extra_ud = ud;
    with_store_mut(handle, |st| {
        st.unregister_extra_reach("c_abi");
        if let Some(f) = extra {
            st.register_extra_reach("c_abi", move || {
                let mut cap = 256usize;
                loop {
                    let mut buf = vec![0u32; cap];
                    let n = f(
                        buf.as_mut_ptr(),
                        buf.len() as u32,
                        extra_ud as *mut std::ffi::c_void,
                    ) as usize;
                    if n < cap || cap >= (1 << 20) {
                        buf.truncate(n.min(buf.len()));
                        return buf;
                    }
                    cap = cap.saturating_mul(2);
                }
            });
        }
    });
    1
}

// ── helpers ─────────────────────────────────────────────────────────────────

unsafe fn cstr(p: *const c_char) -> String {
    if p.is_null() {
        return String::new();
    }
    CStr::from_ptr(p).to_string_lossy().into_owned()
}

/// Allocate a copy of `s` for the host. Pair with [`ksub_string_free`].
/// Returns null on null input or allocation failure.
#[no_mangle]
pub extern "C" fn ksub_strdup(s: *const c_char) -> *mut c_char {
    if s.is_null() {
        return ptr::null_mut();
    }
    let Ok(cs) = unsafe { CStr::from_ptr(s) }.to_str() else {
        return ptr::null_mut();
    };
    match CString::new(cs) {
        Ok(owned) => owned.into_raw(),
        Err(_) => ptr::null_mut(),
    }
}

/// Free a C string previously returned by [`ksub_strdup`] (or equivalent into_raw).
/// No-op on null. Do **not** free static pointers such as [`ksub_version`].
#[no_mangle]
pub extern "C" fn ksub_string_free(p: *mut c_char) {
    if !p.is_null() {
        unsafe {
            let _ = CString::from_raw(p);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn atom(h: u64) -> u32 {
        ksub_atom_new(h, c"var".as_ptr(), c"x".as_ptr(), 50.0)
    }

    #[test]
    fn stale_handle_does_not_reach_reused_slot() {
        let h1 = ksub_store_new(1);
        assert_ne!(h1, 0);
        let a = atom(h1);
        assert_eq!(ksub_has_atom(h1, a), 1);
        ksub_store_free(h1);
        assert_eq!(ksub_has_atom(h1, a), 0);
        // nowy store może dostać ten sam slot, ale nie ten sam uchwyt
        let h2 = ksub_store_new(1);
        assert_ne!(h2, h1);
        let b = atom(h2);
        assert_eq!(ksub_has_atom(h2, b), 1);
        assert_eq!(ksub_has_atom(h1, b), 0, "stary uchwyt trafił w nowy store");
        // podwójne free starego uchwytu nie zabija nowego store
        ksub_store_free(h1);
        assert_eq!(ksub_has_atom(h2, b), 1);
        ksub_store_free(h2);
    }

    #[test]
    fn hooks_refuse_stale_handle() {
        let h = ksub_store_new(1);
        ksub_store_free(h);
        assert_eq!(ksub_register_env_of(h, None, ptr::null_mut()), 0);
        assert_eq!(ksub_register_extra_reach(h, None, ptr::null_mut()), 0);
        assert_eq!(ksub_register_env_of(0, None, ptr::null_mut()), 0);
    }

    #[test]
    fn handle_encodes_index_and_generation() {
        assert_eq!(encode_handle(0, 0), 1);
        assert_eq!(encode_handle(4, 3), (3u64 << 32) | 5);
        let slots = vec![
            Slot { gen: 0, store: None },
            Slot { gen: 2, store: Some(Store::new(false)) },
        ];
        assert_eq!(slot_of(&slots, encode_handle(1, 2)), Some(1));
        assert_eq!(slot_of(&slots, encode_handle(1, 1)), None);
        assert_eq!(slot_of(&slots, encode_handle(0, 0)), None);
        assert_eq!(slot_of(&slots, 0), None);
    }
}
