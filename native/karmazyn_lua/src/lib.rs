//! Lua guest on the same seam as `karmazyn_lisp`:
//!   eval_line(str) -> str
//!   session bubble is a Store root labelled `"lua"`
//!
//! The language heap is mlua (PUC 5.4, vendored at build). Tables and
//! closures stay on that heap. Only atoms created through `karmazyn.*`
//! live in the Store. This guest does not register `env_of("guest")`.

use std::cell::{Cell, RefCell};
use std::collections::{HashMap, VecDeque};
use std::fs;
use std::io::{self, IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::thread;
use std::time::Duration;

use karmazyn_substrate::{
    state_for_t, AtomId, BubbleId, Store, T_HOT, T_INIT, T_MAX, T_TOMB, T_WARM,
};
use mlua::{ffi, Function, Lua, MultiValue, Result as LuaResult, Value};

const HOST_API_VERSION: &str = "1.1.0";
const GUEST_VERSION: &str = "Lua 5.4 (Karmazyn mlua)";
/// Instruction budget for one chunk (`eval_line` / `run_tool`). As PID 1 an
/// endless loop would hang the whole system, so the guest cuts it off.
pub const DEFAULT_BUDGET: u64 = 200_000_000;
/// The hook fires every this many VM instructions.
const HOOK_STEP: i32 = 10_000;
/// Registry keys read by `budget_hook` (integers; limit 0 = no limit).
const BUDGET_LIMIT_KEY: &str = "karmazyn.budget.limit";
const BUDGET_USED_KEY: &str = "karmazyn.budget.used";

struct AgentRec {
    name: String,
    task: String,
    status: String,
    prisms: Vec<String>,
}

struct HoloRec {
    topic: String,
    labels: Vec<String>,
    epoch: u64,
}

struct Guest {
    aliases: RefCell<HashMap<String, AtomId>>,
    /// Epoch at which each alias was created. Age on the proxy is `epoch - born`.
    born: RefCell<HashMap<String, u64>>,
    env: Cell<BubbleId>,
    epoch: Cell<u64>,
    input: RefCell<VecDeque<String>>,
    /// Interactive shell reads stdin when the queue is empty. Tests leave this off.
    stdin_on: Cell<bool>,
    fs: RefCell<HashMap<(String, String), String>>,
    cache: RefCell<HashMap<String, (String, String)>>,
    agents: RefCell<HashMap<i64, AgentRec>>,
    holograms: RefCell<HashMap<String, HoloRec>>,
}

pub struct Evaluator {
    env: Cell<BubbleId>,
    lua: Lua,
    prints: Rc<RefCell<String>>,
    project: Rc<RefCell<Option<PathBuf>>>,
    tools: Rc<RefCell<Vec<String>>>,
    guest: Rc<Guest>,
    /// None = no limit. Counted per chunk; `eval_line` resets the count.
    budget: Cell<Option<u64>>,
    /// C function that arms `budget_hook` on the thread that runs chunks.
    arm_budget: Function,
}

impl Evaluator {
    pub fn new(store: &Store) -> Self {
        Self::mount(store, "lua")
    }

    pub fn env(&self) -> BubbleId {
        self.env.get()
    }

    pub fn mount(store: &Store, env_label: &str) -> Self {
        let lua = Lua::new();
        let prints = Rc::new(RefCell::new(String::new()));
        let project = Rc::new(RefCell::new(None));
        let env = store.bubble_new(env_label, None);
        store.set_root(env);
        let guest = Rc::new(Guest {
            aliases: RefCell::new(HashMap::new()),
            born: RefCell::new(HashMap::new()),
            env: Cell::new(env),
            epoch: Cell::new(0),
            input: RefCell::new(VecDeque::new()),
            stdin_on: Cell::new(false),
            fs: RefCell::new(HashMap::new()),
            cache: RefCell::new(HashMap::new()),
            agents: RefCell::new(HashMap::new()),
            holograms: RefCell::new(HashMap::new()),
        });
        let tools = Rc::new(RefCell::new(Vec::new()));
        install_sandbox(&lua).expect("lua sandbox");
        install_print(&lua, prints.clone()).expect("lua print");
        install_searchers(&lua, project.clone()).expect("lua searchers");
        install_karmazyn(&lua, store.clone(), guest.clone()).expect("karmazyn host");
        let arm_budget = install_budget(&lua, Some(DEFAULT_BUDGET)).expect("lua budget");
        Self {
            env: Cell::new(env),
            lua,
            prints,
            project,
            tools,
            guest,
            budget: Cell::new(Some(DEFAULT_BUDGET)),
            arm_budget,
        }
    }

    /// Instruction limit per chunk. `None` turns it off.
    pub fn set_budget(&self, limit: Option<u64>) {
        self.budget.set(limit);
        let _ = self
            .lua
            .set_named_registry_value(BUDGET_LIMIT_KEY, budget_reg(limit));
    }

    pub fn budget(&self) -> Option<u64> {
        self.budget.get()
    }

    /// Re-bind the session root after a snapshot load. The mlua heap is not
    /// in the snapshot, so scripts do not come back. Aliases are rebuilt from
    /// the `"lua"` bubble bindings, which the snapshot does keep.
    pub fn remount_session(&self, store: &Store) {
        let label = "lua";
        let found = store.bubble_ids().into_iter().find(|id| {
            store.bubble_label(*id).as_deref() == Some(label)
        });
        let env = match found {
            Some(id) => id,
            None => store.bubble_new(label, None),
        };
        store.set_root(env);
        self.env.set(env);
        self.guest.env.set(env);
        let mut aliases = HashMap::new();
        let mut born = HashMap::new();
        let epoch = self.guest.epoch.get();
        if let Some(binds) = store.bubble_bindings(env) {
            for (name, aid) in binds {
                if is_engine_sid(&name) || !store.has_atom(aid) {
                    continue;
                }
                born.insert(name.clone(), epoch);
                aliases.insert(name, aid);
            }
        }
        *self.guest.aliases.borrow_mut() = aliases;
        *self.guest.born.borrow_mut() = born;
    }

    pub fn install_preload_dir(&self, dir: impl AsRef<Path>) -> Result<usize, String> {
        let dir = dir.as_ref();
        if !dir.is_dir() {
            return Err(format!("brak katalogu {}", dir.display()));
        }
        let mut files: Vec<PathBuf> = fs::read_dir(dir)
            .map_err(|e| e.to_string())?
            .filter_map(|ent| ent.ok().map(|e| e.path()))
            .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("lua"))
            .collect();
        files.sort();
        let mut n = 0;
        for path in files {
            let Some(name) = path.file_stem().and_then(|s| s.to_str()) else {
                continue;
            };
            if name.is_empty() {
                continue;
            }
            let source = fs::read_to_string(&path).map_err(|e| e.to_string())?;
            self.install_preload(name, &source)?;
            n += 1;
        }
        Ok(n)
    }

    pub fn install_preload(&self, name: &str, source: &str) -> Result<(), String> {
        let func = self
            .lua
            .load(source)
            .set_name(name)
            .into_function()
            .map_err(|e| e.to_string())?;
        let package: mlua::Table = self.lua.globals().get("package").map_err(|e| e.to_string())?;
        let preload: mlua::Table = package.get("preload").map_err(|e| e.to_string())?;
        preload.set(name, func).map_err(|e| e.to_string())?;
        self.tools.borrow_mut().push(name.to_string());
        Ok(())
    }

    /// Names installed via `install_preload` / `install_preload_dir`, sorted.
    pub fn tool_names(&self) -> Vec<String> {
        let mut names = self.tools.borrow().clone();
        names.sort();
        names.dedup();
        names
    }

    /// Queue a line for `karmazyn.read_line` (tests and scripted tools).
    pub fn push_input(&self, line: &str) {
        self.guest.input.borrow_mut().push_back(line.to_string());
    }

    /// When the queue is empty, `read_line` reads stdin and prints the prompt.
    pub fn enable_stdin(&self, on: bool) {
        self.guest.stdin_on.set(on);
    }

    /// Advance the session epoch by the ticks a shell `tick`/`settle` already ran.
    pub fn add_epoch(&self, n: u64) {
        if n == 0 {
            return;
        }
        self.guest
            .epoch
            .set(self.guest.epoch.get().saturating_add(n));
    }

    /// Run a preloaded `lua_bin` script. Calls `package.preload[name]` directly so
    /// a second `tool ls` runs again (`require` would return the cached module).
    /// `spec` is `name` plus optional arguments (`tool nano notatki --temp`).
    pub fn run_tool(&self, store: &Store, spec: &str) -> Result<String, String> {
        let mut parts = spec.split_whitespace();
        let Some(name) = parts.next() else {
            return Err("usage: tool <name> [arg...]".into());
        };
        if !name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_')
        {
            return Err("usage: tool <name> [arg...]".into());
        }
        let mut call = format!(
            "do local fn = package.preload['{name}']; if not fn then error('brak narzędzia {name}') end; return fn("
        );
        let mut first = true;
        for arg in parts {
            if arg.chars().any(|c| c == '\\' || c == '\'' || c.is_control()) {
                return Err("usage: tool <name> [arg...]".into());
            }
            if !first {
                call.push_str(", ");
            }
            first = false;
            call.push('\'');
            call.push_str(arg);
            call.push('\'');
        }
        call.push_str(") end");
        Ok(self.eval_line(store, &call))
    }

    pub fn set_project_root(&self, root: impl Into<PathBuf>) {
        *self.project.borrow_mut() = Some(root.into());
    }

    /// One chunk. Empty input is `""`. A language error is `blad: …`, never a panic.
    /// Prints and `return` are both kept. Locals do not leak between calls.
    pub fn eval_line(&self, _store: &Store, line: &str) -> String {
        let line = line.trim();
        if line.is_empty() {
            return String::new();
        }
        self.prints.borrow_mut().clear();
        if let Err(e) = self.arm_budget.call::<()>(()) {
            return format!("blad: {e}");
        }
        match self.lua.load(line).set_name("=stdin").eval::<MultiValue>() {
            Ok(values) => join_print_and_return(&self.prints.borrow(), &values),
            Err(e) => format!("blad: {e}"),
        }
    }
}

fn budget_reg(limit: Option<u64>) -> i64 {
    limit.map_or(0, |n| i64::try_from(n).unwrap_or(i64::MAX))
}

/// Instruction budget as a raw count hook. mlua's own `set_hook` serves one
/// thread only and switches itself off in coroutines; a raw `lua_sethook` is
/// copied by `lua_newthread`, so every coroutine counts against the same chunk.
/// Returns the C function that arms the hook and zeroes the count.
fn install_budget(lua: &Lua, limit: Option<u64>) -> LuaResult<Function> {
    lua.set_named_registry_value(BUDGET_LIMIT_KEY, budget_reg(limit))?;
    lua.set_named_registry_value(BUDGET_USED_KEY, 0i64)?;
    unsafe extern "C-unwind" fn arm(l: *mut ffi::lua_State) -> std::os::raw::c_int {
        ffi::lua_pushinteger(l, 0);
        ffi::lua_setfield(l, ffi::LUA_REGISTRYINDEX, c"karmazyn.budget.used".as_ptr());
        ffi::lua_sethook(l, Some(budget_hook), ffi::LUA_MASKCOUNT, HOOK_STEP);
        0
    }
    unsafe { lua.create_c_function(arm) }
}

/// Past the limit the hook fires on every instruction, so the error comes back
/// right after a `pcall` (or a failed `coroutine.resume`) that caught it.
/// No value with a destructor is alive when `lua_error` longjmps out.
unsafe extern "C-unwind" fn budget_hook(l: *mut ffi::lua_State, _ar: *mut ffi::lua_Debug) {
    let step = ffi::lua_Integer::from(ffi::lua_gethookcount(l).max(1));
    ffi::lua_getfield(l, ffi::LUA_REGISTRYINDEX, c"karmazyn.budget.limit".as_ptr());
    let limit = ffi::lua_tointegerx(l, -1, std::ptr::null_mut());
    ffi::lua_getfield(l, ffi::LUA_REGISTRYINDEX, c"karmazyn.budget.used".as_ptr());
    let used = ffi::lua_tointegerx(l, -1, std::ptr::null_mut()).saturating_add(step);
    ffi::lua_pop(l, 2);
    ffi::lua_pushinteger(l, used);
    ffi::lua_setfield(l, ffi::LUA_REGISTRYINDEX, c"karmazyn.budget.used".as_ptr());
    if limit > 0 && used > limit {
        ffi::lua_sethook(l, Some(budget_hook), ffi::LUA_MASKCOUNT, 1);
        let msg = format!("przekroczono limit instrukcji ({limit})");
        ffi::lua_pushlstring(l, msg.as_ptr().cast(), msg.len());
        drop(msg);
        ffi::lua_error(l);
    }
    if step != ffi::lua_Integer::from(HOOK_STEP) {
        // wątek z poprzedniego chunka mógł zostać na kroku 1
        ffi::lua_sethook(l, Some(budget_hook), ffi::LUA_MASKCOUNT, HOOK_STEP);
    }
}

fn join_print_and_return(printed: &str, values: &MultiValue) -> String {
    let returned = if values.is_empty() {
        String::new()
    } else {
        format_multi(values)
    };
    match (printed.is_empty(), returned.is_empty()) {
        (true, _) => returned,
        (false, true) => printed.to_string(),
        (false, false) => format!("{printed}\n{returned}"),
    }
}

fn format_multi(values: &MultiValue) -> String {
    values
        .iter()
        .map(fmt_value)
        .collect::<Vec<_>>()
        .join("\t")
}

fn fmt_value(v: &Value) -> String {
    match v {
        Value::Nil => "nil".into(),
        Value::Boolean(b) => b.to_string(),
        Value::Integer(n) => n.to_string(),
        Value::Number(n) => fmt_num(*n),
        Value::String(s) => lua_string(s),
        Value::Table(_) => "table".into(),
        Value::Function(_) => "function".into(),
        Value::Thread(_) => "thread".into(),
        Value::LightUserData(_) | Value::UserData(_) => "userdata".into(),
        Value::Error(e) => e.to_string(),
        _ => "userdata".into(),
    }
}

fn lua_string(s: &mlua::String) -> String {
    s.to_str().map(|t| t.as_ref().to_string()).unwrap_or_default()
}

fn fmt_num(n: f64) -> String {
    if n.is_finite() && n.fract() == 0.0 && n.abs() < 1e15 {
        format!("{}", n as i64)
    } else {
        format!("{n}")
    }
}

fn install_sandbox(lua: &Lua) -> LuaResult<()> {
    lua.globals().set("_VERSION", GUEST_VERSION)?;
    lua.load(
        r#"
dofile = nil
loadfile = nil
io = nil
if os then
  os.execute = nil
  os.remove = nil
  os.rename = nil
  os.tmpname = nil
  os.exit = nil
  os.getenv = nil
end
if string then
  string.dump = nil
end
debug = nil
if package then
  package.loadlib = nil
  package.path = ""
  package.cpath = ""
  package.searchers = {}
end
"#,
    )
    .exec()?;
    Ok(())
}

fn install_print(lua: &Lua, prints: Rc<RefCell<String>>) -> LuaResult<()> {
    let print_fn = lua.create_function(move |_, args: MultiValue| {
        let line = format_multi(&args);
        let mut buf = prints.borrow_mut();
        if !buf.is_empty() {
            buf.push('\n');
        }
        buf.push_str(&line);
        Ok(())
    })?;
    lua.globals().set("print", print_fn)?;
    Ok(())
}

fn install_searchers(lua: &Lua, project: Rc<RefCell<Option<PathBuf>>>) -> LuaResult<()> {
    let package: mlua::Table = lua.globals().get("package")?;
    let preload_searcher = lua.create_function(|lua, name: String| -> LuaResult<MultiValue> {
        let package: mlua::Table = lua.globals().get("package")?;
        let preload: mlua::Table = package.get("preload")?;
        let pre: Value = preload.get(name)?;
        if matches!(pre, Value::Function(_)) {
            Ok(MultiValue::from_vec(vec![pre]))
        } else {
            Ok(MultiValue::new())
        }
    })?;
    let project_searcher = lua.create_function(move |lua, name: String| -> LuaResult<MultiValue> {
        let root = match project.borrow().clone() {
            Some(root) => root,
            None => return Ok(MultiValue::new()),
        };
        let Some(path) = module_file(&root, &name) else {
            return Ok(MultiValue::new());
        };
        if !path.is_file() {
            return Ok(MultiValue::new());
        }
        let text = fs::read_to_string(&path).map_err(mlua::Error::external)?;
        let func = lua.load(&text).set_name(&name).into_function()?;
        Ok(MultiValue::from_vec(vec![Value::Function(func)]))
    })?;
    let searchers = lua.create_table()?;
    searchers.set(1, preload_searcher)?;
    searchers.set(2, project_searcher)?;
    package.set("searchers", searchers)?;
    Ok(())
}

/// `lib.greeter` → `{root}/lib/greeter.lua`. Rejects `..`, drives and slashes.
fn module_file(root: &Path, name: &str) -> Option<PathBuf> {
    if name.is_empty()
        || name.contains("..")
        || name.contains(':')
        || name.contains('\\')
        || name.contains('/')
        || !name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '.')
    {
        return None;
    }
    let rel = name.replace('.', "/");
    Some(root.join(format!("{rel}.lua")))
}

fn install_karmazyn(lua: &Lua, store: Store, guest: Rc<Guest>) -> LuaResult<()> {
    let k = lua.create_table()?;
    k.set("_VERSION", HOST_API_VERSION)?;
    k.set("T_INIT", T_INIT)?;
    k.set("T_HOT", T_HOT)?;
    k.set("T_WARM", T_WARM)?;
    k.set("T_TOMB", T_TOMB)?;
    k.set("T_MAX", T_MAX)?;

    let store_c = store.clone();
    let guest_c = guest.clone();
    let create = lua.create_function(move |lua, args: MultiValue| -> LuaResult<Value> {
        create_atom(lua, &store_c, &guest_c, &args)
    })?;
    k.set("create_atom", create)?;

    let store_g = store.clone();
    let guest_g = guest.clone();
    let get = lua.create_function(move |lua, id: String| -> LuaResult<Value> {
        atom_proxy(lua, &store_g, &guest_g, &id)
    })?;
    k.set("get_atom", get)?;

    let store_d = store.clone();
    let guest_d = guest.clone();
    let delete = lua.create_function(move |_, id: String| -> LuaResult<bool> {
        Ok(delete_atom(&store_d, &guest_d, &id))
    })?;
    k.set("delete_atom", delete)?;

    let store_l = store.clone();
    let guest_l = guest.clone();
    let list = lua.create_function(move |lua, args: MultiValue| -> LuaResult<mlua::Table> {
        list_atoms(lua, &store_l, &guest_l, &args)
    })?;
    k.set("list_atoms", list)?;

    let store_s = store.clone();
    let guest_s = guest.clone();
    let step = lua.create_function(move |_, n: Option<i64>| -> LuaResult<i64> {
        let n = n.unwrap_or(1).max(1) as u32;
        store_s.settle(n);
        guest_s
            .epoch
            .set(guest_s.epoch.get().saturating_add(n as u64));
        Ok(n as i64)
    })?;
    k.set("step", step)?;

    let guest_e = guest.clone();
    let epoch = lua.create_function(move |_, _: ()| -> LuaResult<i64> {
        Ok(guest_e.epoch.get() as i64)
    })?;
    k.set("get_epoch", epoch)?;

    let store_res = store.clone();
    let resources = lua.create_function(move |lua, _: ()| -> LuaResult<mlua::Table> {
        resources_table(lua, &store_res)
    })?;
    k.set("get_resources", resources)?;

    let guest_in = guest.clone();
    let read_line = lua.create_function(move |_, args: MultiValue| -> LuaResult<Option<String>> {
        Ok(read_line(&guest_in, &args))
    })?;
    k.set("read_line", read_line)?;

    let guest_cls = guest.clone();
    let clear = lua.create_function(move |_, _: MultiValue| -> LuaResult<()> {
        clear_screen(&guest_cls);
        Ok(())
    })?;
    k.set("clear_screen", clear)?;

    let sleep_fn = lua.create_function(|_, args: MultiValue| -> LuaResult<()> {
        let sec = arg_number(args.iter().next()).unwrap_or(1.0);
        host_sleep(sec);
        Ok(())
    })?;
    k.set("sleep", sleep_fn)?;

    let store_cl = store.clone();
    let guest_cl = guest.clone();
    let clone = lua.create_function(move |lua, args: MultiValue| -> LuaResult<Value> {
        clone_atom(lua, &store_cl, &guest_cl, &args)
    })?;
    k.set("clone_atom", clone)?;

    let store_t = store.clone();
    let temperature = lua.create_function(move |_, _: ()| -> LuaResult<f64> {
        let st = store_t.stats();
        let total = st.total.max(1) as f64;
        Ok(st.alive as f64 / total)
    })?;
    k.set("get_temperature", temperature)?;

    let store_b = store.clone();
    let bubbles = lua.create_function(move |lua, _: ()| -> LuaResult<mlua::Table> {
        Ok(list_bubbles(lua, &store_b)?)
    })?;
    k.set("list_bubbles", bubbles)?;

    let store_k = store.clone();
    let guest_k = guest.clone();
    let consolidate = lua.create_function(move |lua, id: String| -> LuaResult<Value> {
        consolidate_atom(lua, &store_k, &guest_k, &id)
    })?;
    k.set("consolidate", consolidate)?;

    let store_r = store.clone();
    let guest_r = guest.clone();
    let recall = lua.create_function(move |lua, args: MultiValue| -> LuaResult<mlua::Table> {
        Ok(recall_atoms(lua, &store_r, &guest_r, &args)?)
    })?;
    k.set("recall", recall)?;

    let store_sim = store.clone();
    let guest_sim = guest.clone();
    let similarity = lua.create_function(move |_, args: MultiValue| -> LuaResult<f64> {
        Ok(similarity_of(&store_sim, &guest_sim, &args))
    })?;
    k.set("get_similarity", similarity)?;

    let idea = lua.create_function(|_, _: MultiValue| -> LuaResult<Value> { Ok(Value::Nil) })?;
    k.set("generate_from_idea", idea)?;

    let guest_tty = guest.clone();
    let interactive = lua.create_function(move |_, _: ()| -> LuaResult<bool> {
        Ok(guest_tty.stdin_on.get())
    })?;
    k.set("interactive", interactive)?;

    let guest_ag = guest.clone();
    let list_ag = lua.create_function(move |lua, _: ()| -> LuaResult<mlua::Table> {
        list_agents(lua, &guest_ag)
    })?;
    k.set("list_agents", list_ag)?;

    let guest_sp = guest.clone();
    let spawn = lua.create_function(move |_, args: MultiValue| -> LuaResult<i64> {
        Ok(spawn_agent(&guest_sp, &args))
    })?;
    k.set("spawn_agent", spawn)?;

    let guest_da = guest.clone();
    let del_ag = lua.create_function(move |_, args: MultiValue| -> LuaResult<bool> {
        Ok(delete_agent(&guest_da, &args))
    })?;
    k.set("delete_agent", del_ag)?;

    let guest_lh = guest.clone();
    let list_h = lua.create_function(move |lua, _: ()| -> LuaResult<mlua::Table> {
        list_holograms(lua, &guest_lh)
    })?;
    k.set("list_holograms", list_h)?;

    let guest_ch = guest.clone();
    let make_h = lua.create_function(move |_, args: MultiValue| -> LuaResult<String> {
        Ok(create_hologram(&guest_ch, &args))
    })?;
    k.set("create_hologram", make_h)?;

    let ui = lua.create_table()?;
    let bar = lua.create_function(|_, args: MultiValue| -> LuaResult<String> {
        Ok(progress_bar(&args))
    })?;
    ui.set("progress_bar", bar)?;
    let frame = lua.create_function(|lua, args: MultiValue| -> LuaResult<String> {
        draw_frame(lua, &args)
    })?;
    ui.set("draw_frame", frame)?;
    k.set("ui", ui)?;

    let guest_fs = guest.clone();
    let fs_tbl = lua.create_table()?;
    let fs_read = lua.create_function(move |lua, args: MultiValue| -> LuaResult<Value> {
        fs_read(lua, &guest_fs, &args)
    })?;
    fs_tbl.set("read", fs_read)?;
    let guest_fw = guest.clone();
    let fs_write = lua.create_function(move |_, args: MultiValue| -> LuaResult<bool> {
        fs_write(&guest_fw, &args);
        Ok(true)
    })?;
    fs_tbl.set("write", fs_write)?;
    k.set("fs", fs_tbl)?;

    let guest_cr = guest.clone();
    let cache_tbl = lua.create_table()?;
    let cache_read = lua.create_function(move |lua, args: MultiValue| -> LuaResult<Value> {
        cache_read(lua, &guest_cr, &args)
    })?;
    cache_tbl.set("read", cache_read)?;
    let guest_cw = guest.clone();
    let cache_write = lua.create_function(move |_, args: MultiValue| -> LuaResult<bool> {
        cache_write(&guest_cw, &args);
        Ok(true)
    })?;
    cache_tbl.set("write", cache_write)?;
    k.set("cache", cache_tbl)?;

    lua.globals().set("karmazyn", k)?;
    Ok(())
}

fn sorted_ids(guest: &Guest) -> Vec<String> {
    let mut ids: Vec<String> = guest.aliases.borrow().keys().cloned().collect();
    ids.sort();
    ids
}

fn create_atom(lua: &Lua, store: &Store, guest: &Rc<Guest>, args: &MultiValue) -> LuaResult<Value> {
    let mut it = args.iter();
    let id = match it.next() {
        Some(Value::String(s)) => match s.to_str() {
            Ok(s) if !s.is_empty() => s.to_string(),
            _ => return lua_text(lua, "brak id"),
        },
        _ => return lua_text(lua, "brak id"),
    };
    if is_engine_sid(&id) {
        return lua_text(
            lua,
            &format!("id '{id}' zarezerwowane dla silnika (atom_new); użyj innej nazwy"),
        );
    }
    if guest.aliases.borrow().contains_key(&id) {
        return lua_text(lua, &format!("atom o id '{id}' już istnieje"));
    }
    let s = arg_string(it.next());
    let e = arg_string(it.next());
    let t = clamp_host_t(arg_number(it.next()).unwrap_or(T_INIT));
    // Fifth argument is tracer energy. The native Store has no tracer; ignore it.
    let aid = store.atom_new(&s, &e, t);
    let _ = store.bind(guest.env.get(), &id, aid);
    remember_alias(guest, &id, aid);
    atom_proxy(lua, store, guest, &id)
}

fn remember_alias(guest: &Guest, id: &str, aid: AtomId) {
    guest.aliases.borrow_mut().insert(id.to_string(), aid);
    guest.born.borrow_mut().insert(id.to_string(), guest.epoch.get());
}

fn atom_proxy(lua: &Lua, store: &Store, guest: &Rc<Guest>, id: &str) -> LuaResult<Value> {
    let Some(aid) = guest.aliases.borrow().get(id).copied() else {
        return Ok(Value::Nil);
    };
    if store.atom_se(aid).is_none() {
        guest.aliases.borrow_mut().remove(id);
        return Ok(Value::Nil);
    }
    let row = lua.create_table()?;
    let id_owned = id.to_string();
    row.set("id", id_owned.clone())?;
    row.set("store_id", i64::from(aid))?;

    let store_t = store.clone();
    let guest_t = Rc::clone(guest);
    let id_t = id_owned.clone();
    row.set(
        "get_T",
        lua.create_function(move |_, _: MultiValue| -> LuaResult<f64> {
            Ok(live_t(&store_t, &guest_t, &id_t).unwrap_or(0.0))
        })?,
    )?;

    let store_f = store.clone();
    let guest_f = Rc::clone(guest);
    let id_f = id_owned.clone();
    row.set(
        "get_T_frac",
        lua.create_function(move |_, _: MultiValue| -> LuaResult<f64> {
            let t = live_t(&store_f, &guest_f, &id_f).unwrap_or(0.0);
            let max = if T_MAX <= 0.0 { 100.0 } else { T_MAX };
            Ok((t / max).clamp(0.0, 1.0))
        })?,
    )?;

    let store_e = store.clone();
    let guest_e = Rc::clone(guest);
    let id_e = id_owned.clone();
    row.set(
        "set_E",
        lua.create_function(move |_, args: MultiValue| -> LuaResult<bool> {
            Ok(set_emanation(&store_e, &guest_e, &id_e, &args))
        })?,
    )?;

    let store_st = store.clone();
    let guest_st = Rc::clone(guest);
    let id_st = id_owned.clone();
    row.set(
        "set_state",
        lua.create_function(move |_, args: MultiValue| -> LuaResult<bool> {
            Ok(set_state(&store_st, &guest_st, &id_st, &args))
        })?,
    )?;

    let store_r = store.clone();
    let guest_r = Rc::clone(guest);
    let id_r = id_owned.clone();
    row.set(
        "refresh",
        lua.create_function(move |_, _: MultiValue| -> LuaResult<bool> {
            let Some(aid) = guest_r.aliases.borrow().get(&id_r).copied() else {
                return Ok(false);
            };
            Ok(store_r.heat(aid))
        })?,
    )?;

    let store_k = store.clone();
    let guest_k = Rc::clone(guest);
    let id_k = id_owned.clone();
    row.set(
        "consolidate",
        lua.create_function(move |lua, _: MultiValue| -> LuaResult<Value> {
            consolidate_atom(lua, &store_k, &guest_k, &id_k)
        })?,
    )?;

    let store_i = store.clone();
    let guest_i = Rc::clone(guest);
    let id_i = id_owned;
    let index = lua.create_function(move |lua, args: MultiValue| -> LuaResult<Value> {
        let mut it = args.iter();
        let _tbl = it.next();
        let key = match it.next() {
            Some(Value::String(s)) => lua_string(s),
            _ => return Ok(Value::Nil),
        };
        proxy_field(lua, &store_i, &guest_i, &id_i, &key)
    })?;
    let mt = lua.create_table()?;
    mt.set("__index", index)?;
    row.set_metatable(Some(mt));
    Ok(Value::Table(row))
}

fn proxy_field(lua: &Lua, store: &Store, guest: &Guest, id: &str, key: &str) -> LuaResult<Value> {
    let Some(aid) = guest.aliases.borrow().get(id).copied() else {
        return Ok(Value::Nil);
    };
    let Some((s, e)) = store.atom_se(aid) else {
        return Ok(Value::Nil);
    };
    let t = store.get_atom_t(aid).unwrap_or(0.0);
    match key {
        "s" | "S" => lua_text(lua, &s),
        "e" | "E" => lua_text(lua, &e),
        "state" => {
            let state = store
                .get_atom_state(aid)
                .unwrap_or_else(|| state_for_t(t).to_string());
            lua_text(lua, &state)
        }
        "t" | "T_raw" => Ok(Value::Number(t)),
        "age" => {
            let born = guest.born.borrow().get(id).copied().unwrap_or(guest.epoch.get());
            Ok(Value::Integer(guest.epoch.get().saturating_sub(born) as i64))
        }
        _ => Ok(Value::Nil),
    }
}

fn lua_text(lua: &Lua, s: &str) -> LuaResult<Value> {
    Ok(Value::String(lua.create_string(s)?))
}

fn clamp_host_t(t: f64) -> f64 {
    if !t.is_finite() {
        T_INIT
    } else {
        t.clamp(0.0, T_MAX)
    }
}

fn live_t(store: &Store, guest: &Guest, id: &str) -> Option<f64> {
    let aid = guest.aliases.borrow().get(id).copied()?;
    store.get_atom_t(aid)
}

fn payload_string(args: &MultiValue) -> Option<String> {
    for v in args.iter() {
        match v {
            Value::Table(_) | Value::Nil => continue,
            other => return Some(arg_string(Some(other))),
        }
    }
    None
}

fn set_emanation(store: &Store, guest: &Guest, id: &str, args: &MultiValue) -> bool {
    let Some(aid) = guest.aliases.borrow().get(id).copied() else {
        return false;
    };
    let Some((s, _)) = store.atom_se(aid) else {
        return false;
    };
    let Some(new_e) = payload_string(args) else {
        return true;
    };
    let t = store.get_atom_t(aid).unwrap_or(T_INIT);
    let tok = store.atom_value_token(aid).unwrap_or(0);
    store.atom_upsert(aid, &s, &new_e, t, tok)
}

fn state_setpoint(layer: &str) -> Option<f64> {
    match layer.to_ascii_uppercase().as_str() {
        "HOT" => Some(T_HOT),
        "WARM" => Some(T_WARM),
        "COLD" => Some(T_TOMB + 3.0),
        "TOMB" => Some((T_TOMB * 0.5).max(0.001)),
        _ => None,
    }
}

fn set_state(store: &Store, guest: &Guest, id: &str, args: &MultiValue) -> bool {
    let Some(aid) = guest.aliases.borrow().get(id).copied() else {
        return false;
    };
    let Some(layer) = payload_string(args) else {
        return false;
    };
    let Some(t) = state_setpoint(&layer) else {
        return false;
    };
    store.atom_set_t(aid, t)
}

fn atom_state(store: &Store, guest: &Guest, id: &str) -> Option<String> {
    let aid = guest.aliases.borrow().get(id).copied()?;
    store.get_atom_state(aid)
}

fn list_atoms(lua: &Lua, store: &Store, guest: &Rc<Guest>, args: &MultiValue) -> LuaResult<mlua::Table> {
    let filter = match args.iter().next() {
        Some(Value::String(s)) => {
            let text = lua_string(s);
            if text.is_empty() {
                None
            } else {
                Some(text)
            }
        }
        _ => None,
    };
    let want = match filter.as_deref() {
        Some(s) if s.eq_ignore_ascii_case("ALL") => None,
        Some(s) => Some(s.to_ascii_uppercase()),
        None => None,
    };
    let rows = lua.create_table()?;
    let mut n = 1i64;
    for id in sorted_ids(guest) {
        if let Some(want_state) = want.as_deref() {
            match atom_state(store, guest, &id) {
                Some(st) if st == want_state => {}
                _ => continue,
            }
        }
        if let Value::Table(proxy) = atom_proxy(lua, store, guest, &id)? {
            rows.set(n, proxy)?;
            n += 1;
        }
    }
    Ok(rows)
}

fn resources_table(lua: &Lua, store: &Store) -> LuaResult<mlua::Table> {
    let st = store.stats();
    let t = lua.create_table()?;
    t.set("total", st.total as i64)?;
    t.set("alive", st.alive as i64)?;
    t.set("hot", st.hot as i64)?;
    t.set("warm", st.warm as i64)?;
    t.set("cold", st.cold as i64)?;
    t.set("tomb", st.tomb as i64)?;
    t.set("dead", st.dead as i64)?;
    t.set("reaped", st.reaped as i64)?;
    t.set("retained_tomb", st.retained_tomb as i64)?;
    t.set("bubbles", st.bubbles as i64)?;
    t.set("HOT", st.hot as i64)?;
    t.set("WARM", st.warm as i64)?;
    t.set("COLD", st.cold as i64)?;
    t.set("TOMB", st.tomb as i64)?;
    Ok(t)
}

fn read_line(guest: &Guest, args: &MultiValue) -> Option<String> {
    if let Some(line) = guest.input.borrow_mut().pop_front() {
        return Some(line);
    }
    if !guest.stdin_on.get() {
        return Some(String::new());
    }
    let prompt = match args.iter().next() {
        Some(Value::String(s)) => lua_string(s),
        _ => String::new(),
    };
    if !prompt.is_empty() {
        print!("{prompt}");
        let _ = io::stdout().flush();
    }
    let mut buf = String::new();
    match io::stdin().read_line(&mut buf) {
        Ok(0) | Err(_) => None,
        Ok(_) => {
            if buf.ends_with('\n') {
                buf.pop();
                if buf.ends_with('\r') {
                    buf.pop();
                }
            }
            Some(buf)
        }
    }
}

fn clear_screen(guest: &Guest) {
    if guest.stdin_on.get() && io::stdout().is_terminal() {
        print!("\x1b[2J\x1b[H");
        let _ = io::stdout().flush();
    }
}

fn host_sleep(sec: f64) {
    if matches!(
        std::env::var("KARMAZYN_NOSLEEP").ok().as_deref(),
        Some("1") | Some("true") | Some("yes")
    ) {
        return;
    }
    if !sec.is_finite() || sec <= 0.0 {
        return;
    }
    let ms = (sec * 1000.0) as u64;
    if ms > 0 {
        thread::sleep(Duration::from_millis(ms));
    }
}

fn clone_atom(lua: &Lua, store: &Store, guest: &Rc<Guest>, args: &MultiValue) -> LuaResult<Value> {
    let mut it = args.iter();
    let src = match it.next() {
        Some(Value::String(s)) => lua_string(s),
        _ => return lua_text(lua, "złe id"),
    };
    let dst = match it.next() {
        Some(Value::String(s)) => lua_string(s),
        _ => return lua_text(lua, "złe id"),
    };
    if src.is_empty() || dst.is_empty() {
        return lua_text(lua, "złe id");
    }
    if is_engine_sid(&dst) {
        return lua_text(lua, &format!("id '{dst}' zarezerwowane dla silnika"));
    }
    let Some(aid) = guest.aliases.borrow().get(&src).copied() else {
        return lua_text(lua, &format!("brak źródła {src}"));
    };
    let Some((s, e)) = store.atom_se(aid) else {
        return lua_text(lua, &format!("brak źródła {src}"));
    };
    let t = store.get_atom_t(aid).unwrap_or(T_INIT);
    if guest.aliases.borrow().contains_key(&dst) {
        delete_atom(store, guest, &dst);
    }
    let new_id = store.atom_new(&s, &e, t);
    let _ = store.bind(guest.env.get(), &dst, new_id);
    remember_alias(guest, &dst, new_id);
    atom_proxy(lua, store, guest, &dst)
}

fn seq_strings(t: &mlua::Table, cap: i64) -> Vec<String> {
    let mut out = Vec::new();
    for i in 1..=cap {
        let v: Value = match t.get(i) {
            Ok(v) => v,
            Err(_) => break,
        };
        if matches!(v, Value::Nil) {
            break;
        }
        out.push(match &v {
            Value::String(s) => lua_string(s),
            other => fmt_value(other),
        });
    }
    out
}

fn list_agents(lua: &Lua, guest: &Guest) -> LuaResult<mlua::Table> {
    let snap: Vec<(i64, String, String, String, Vec<String>)> = {
        let map = guest.agents.borrow();
        let mut v: Vec<_> = map
            .iter()
            .map(|(pid, a)| {
                (
                    *pid,
                    a.name.clone(),
                    a.task.clone(),
                    a.status.clone(),
                    a.prisms.clone(),
                )
            })
            .collect();
        v.sort_by_key(|row| row.0);
        v
    };
    let rows = lua.create_table()?;
    for (i, (pid, name, task, status, prisms)) in snap.into_iter().enumerate() {
        let row = lua.create_table()?;
        row.set("pid", pid)?;
        row.set("name", name)?;
        row.set("task", task)?;
        row.set("status", status)?;
        let p = lua.create_table()?;
        for (j, prism) in prisms.into_iter().enumerate() {
            p.set(j + 1, prism)?;
        }
        row.set("prisms", p)?;
        rows.set(i + 1, row)?;
    }
    Ok(rows)
}

fn spawn_agent(guest: &Guest, args: &MultiValue) -> i64 {
    let mut it = args.iter();
    let name = arg_string(it.next());
    let task = arg_string(it.next());
    let prisms = match it.next() {
        Some(Value::Table(t)) => seq_strings(t, 32),
        _ => Vec::new(),
    };
    let prisms = if prisms.is_empty() {
        vec!["phi".to_string()]
    } else {
        prisms
    };
    let mut map = guest.agents.borrow_mut();
    let mut pid = 1i64;
    while map.contains_key(&pid) {
        pid += 1;
    }
    map.insert(
        pid,
        AgentRec {
            name: if name.is_empty() {
                format!("agent_{pid}")
            } else {
                name
            },
            task: if task.is_empty() {
                "idle".into()
            } else {
                task
            },
            status: "running".into(),
            prisms,
        },
    );
    pid
}

fn delete_agent(guest: &Guest, args: &MultiValue) -> bool {
    let Some(n) = arg_number(first_scalar(args)) else {
        return false;
    };
    if n.fract() != 0.0 {
        return false;
    }
    guest.agents.borrow_mut().remove(&(n as i64)).is_some()
}

fn first_scalar(args: &MultiValue) -> Option<&Value> {
    args.iter().find(|v| !matches!(v, Value::Table(_) | Value::Nil))
}

fn list_holograms(lua: &Lua, guest: &Guest) -> LuaResult<mlua::Table> {
    let snap: Vec<(String, String, Vec<String>, u64)> = {
        let map = guest.holograms.borrow();
        let mut v: Vec<_> = map
            .iter()
            .map(|(id, h)| (id.clone(), h.topic.clone(), h.labels.clone(), h.epoch))
            .collect();
        v.sort_by(|a, b| a.0.cmp(&b.0));
        v
    };
    let rows = lua.create_table()?;
    for (i, (id, topic, labels, epoch)) in snap.into_iter().enumerate() {
        let row = lua.create_table()?;
        row.set("id", id.clone())?;
        row.set("label", id)?;
        row.set("topic", topic)?;
        row.set("epoch_created", epoch as i64)?;
        let arr = lua.create_table()?;
        for (j, lab) in labels.into_iter().enumerate() {
            arr.set(j + 1, lab)?;
        }
        row.set("atom_labels", arr)?;
        rows.set(i + 1, row)?;
    }
    Ok(rows)
}

fn create_hologram(guest: &Guest, args: &MultiValue) -> String {
    let mut it = args.iter();
    let mut hid = arg_string(it.next());
    let topic_raw = arg_string(it.next());
    let labels = match it.next() {
        Some(Value::Table(t)) => seq_strings(t, 64),
        _ => Vec::new(),
    };
    if hid.is_empty() {
        hid = format!("idea_{}", guest.holograms.borrow().len() + 1);
    }
    let topic = if topic_raw.is_empty() {
        hid.clone()
    } else {
        topic_raw
    };
    let epoch = guest.epoch.get();
    guest.holograms.borrow_mut().insert(
        hid.clone(),
        HoloRec {
            topic,
            labels,
            epoch,
        },
    );
    hid
}

fn pair_key(args: &MultiValue) -> (String, String) {
    let mut it = args.iter();
    (arg_string(it.next()), arg_string(it.next()))
}

fn fs_read(lua: &Lua, guest: &Guest, args: &MultiValue) -> LuaResult<Value> {
    let key = pair_key(args);
    match guest.fs.borrow().get(&key).cloned() {
        Some(text) => lua_text(lua, &text),
        None => Ok(Value::Nil),
    }
}

fn fs_write(guest: &Guest, args: &MultiValue) {
    let mut it = args.iter();
    let bubble = arg_string(it.next());
    let file_id = arg_string(it.next());
    let _kind = it.next();
    let content = arg_string(it.next());
    guest.fs.borrow_mut().insert((bubble, file_id), content);
}

fn cache_read(lua: &Lua, guest: &Guest, args: &MultiValue) -> LuaResult<Value> {
    let name = arg_string(args.iter().next());
    let Some((s, e)) = guest.cache.borrow().get(&name).cloned() else {
        return Ok(Value::Nil);
    };
    let row = lua.create_table()?;
    row.set("S", s)?;
    row.set("E", e)?;
    Ok(Value::Table(row))
}

fn cache_write(guest: &Guest, args: &MultiValue) {
    let mut it = args.iter();
    let name = arg_string(it.next());
    let s = arg_string(it.next());
    let content = arg_string(it.next());
    guest.cache.borrow_mut().insert(name, (s, content));
}

fn progress_bar(args: &MultiValue) -> String {
    let mut it = args.iter();
    let Some(value) = arg_number(it.next()) else {
        return "[?]".into();
    };
    let maximum = arg_number(it.next()).unwrap_or(100.0);
    let width = arg_number(it.next()).unwrap_or(20.0);
    if !value.is_finite() || !maximum.is_finite() || !width.is_finite() {
        return "[?]".into();
    }
    let w = (width as i64).max(1) as usize;
    let frac = if maximum <= 0.0 {
        0.0
    } else {
        (value / maximum).clamp(0.0, 1.0)
    };
    let filled = ((frac * w as f64).round() as usize).min(w);
    format!("[{}{}]", "#".repeat(filled), "-".repeat(w - filled))
}

fn draw_frame(lua: &Lua, args: &MultiValue) -> LuaResult<String> {
    let mut it = args.iter();
    let title = arg_string(it.next());
    let lines = match it.next() {
        Some(Value::Table(t)) => seq_strings(t, 500),
        Some(Value::Nil) | None => Vec::new(),
        Some(other) => vec![fmt_value(other)],
    };
    let _style = it.next();
    let _ = lua;
    let lines = flatten_frame_lines(lines);
    let width = title
        .chars()
        .count()
        .saturating_add(4)
        .max(20)
        .max(lines.iter().map(|l| l.chars().count()).max().unwrap_or(20));
    let bar = format!("+{}+", "-".repeat(width + 2));
    let mut out = vec![
        bar.clone(),
        format!("| {} |", center_text(&title, width)),
        bar.clone(),
    ];
    for line in &lines {
        out.push(format!("| {} |", pad_right(line, width)));
    }
    out.push(bar);
    Ok(out.join("\n"))
}

fn flatten_frame_lines(lines: Vec<String>) -> Vec<String> {
    let mut rows = Vec::new();
    for line in lines {
        let norm = line.replace("\r\n", "\n").replace('\r', "\n");
        if norm.contains('\n') {
            rows.extend(norm.split('\n').map(|part| part.to_string()));
        } else {
            rows.push(norm);
        }
    }
    rows
}

fn center_text(s: &str, width: usize) -> String {
    let n = s.chars().count();
    if n >= width {
        return s.to_string();
    }
    let pad = width - n;
    let left = pad / 2;
    format!("{}{}{}", " ".repeat(left), s, " ".repeat(pad - left))
}

fn pad_right(s: &str, width: usize) -> String {
    let n = s.chars().count();
    if n >= width {
        s.to_string()
    } else {
        format!("{s}{}", " ".repeat(width - n))
    }
}

fn delete_atom(store: &Store, guest: &Guest, id: &str) -> bool {
    let Some(aid) = guest.aliases.borrow_mut().remove(id) else {
        return false;
    };
    guest.born.borrow_mut().remove(id);
    store.unbind(guest.env.get(), id);
    store.delete_atom(aid)
}

const BUBBLE_SKIP: &[&str] = &[
    "lua", "table", "call", "chunk", "preload", "load", "lib", "var", "field", "builtin", "param",
];

fn list_bubbles(lua: &Lua, store: &Store) -> LuaResult<mlua::Table> {
    let rows = lua.create_table()?;
    let mut labels: Vec<(BubbleId, String)> = store
        .bubble_ids()
        .into_iter()
        .filter_map(|id| store.bubble_label(id).map(|lab| (id, lab)))
        .filter(|(_, lab)| !lab.is_empty() && !skip_bubble(lab))
        .collect();
    labels.sort_by(|a, b| a.1.cmp(&b.1));
    labels.dedup_by(|a, b| a.1 == b.1);
    for (i, (id, lab)) in labels.into_iter().enumerate() {
        let binds = store.bubble_bindings(id).unwrap_or_default();
        let n = binds.len();
        let parts: Vec<String> = binds
            .iter()
            .take(5)
            .map(|(name, aid)| {
                let text = store
                    .atom_se(*aid)
                    .map(|(_, e)| if e.is_empty() { name.clone() } else { e })
                    .unwrap_or_else(|| name.clone());
                text.chars().take(20).collect()
            })
            .collect();
        let content = if parts.is_empty() {
            "(pusto)".to_string()
        } else {
            parts.join(", ")
        };
        let row = lua.create_table()?;
        row.set("id", lab.clone())?;
        row.set("label", lab)?;
        row.set("n", n)?;
        row.set("content", content)?;
        rows.set(i + 1, row)?;
    }
    Ok(rows)
}

fn skip_bubble(lab: &str) -> bool {
    BUBBLE_SKIP.contains(&lab) || lab.starts_with("i:") || lab.starts_with("s:")
}

fn consolidate_atom(lua: &Lua, store: &Store, guest: &Guest, id: &str) -> LuaResult<Value> {
    let Some(aid) = guest.aliases.borrow().get(id).copied() else {
        return Ok(Value::Nil);
    };
    if !store.has_atom(aid) {
        return Ok(Value::Nil);
    }
    let label = format!("bubble_{id}");
    let bid = store.bubble_new(&label, None);
    store.set_root(bid);
    let _ = store.bind(bid, id, aid);
    Ok(Value::String(lua.create_string(&label)?))
}

fn recall_atoms(
    lua: &Lua,
    store: &Store,
    guest: &Guest,
    args: &MultiValue,
) -> LuaResult<mlua::Table> {
    let mut it = args.iter();
    let q = match it.next() {
        Some(Value::String(s)) => lua_string(s),
        Some(Value::Nil) | None => String::new(),
        Some(other) => fmt_value(other),
    };
    let k = arg_number(it.next()).unwrap_or(5.0).max(0.0) as usize;
    let rows = lua.create_table()?;
    if q.is_empty() || k == 0 {
        return Ok(rows);
    }
    let mut n = 0usize;
    for id in sorted_ids(guest) {
        if n >= k {
            break;
        }
        let Some(aid) = guest.aliases.borrow().get(&id).copied() else {
            continue;
        };
        let Some((s, e)) = store.atom_se(aid) else {
            continue;
        };
        let blob = format!("{e}{s}{id}");
        if !blob.contains(&q) {
            continue;
        }
        let row = lua.create_table()?;
        row.set("score", 0.5)?;
        row.set("sim", 0.5)?;
        row.set("id", id.clone())?;
        row.set("S", s)?;
        row.set("E", e.clone())?;
        let label = if e.is_empty() {
            id.clone()
        } else {
            let cut = e.chars().take(24).collect::<String>();
            format!("{id}:{cut}")
        };
        row.set("label", label)?;
        row.set("layer", "substr")?;
        n += 1;
        rows.set(n, row)?;
    }
    Ok(rows)
}

fn similarity_of(store: &Store, guest: &Guest, args: &MultiValue) -> f64 {
    let mut it = args.iter();
    let Some(Value::String(a)) = it.next() else {
        return 0.0;
    };
    let Some(Value::String(b)) = it.next() else {
        return 0.0;
    };
    let (Ok(a), Ok(b)) = (a.to_str(), b.to_str()) else {
        return 0.0;
    };
    let Some(sa) = face_text(store, guest, a.as_ref()) else {
        return 0.0;
    };
    let Some(sb) = face_text(store, guest, b.as_ref()) else {
        return 0.0;
    };
    if sa.is_empty() || sb.is_empty() {
        return 0.0;
    }
    if sa == sb {
        return 1.0;
    }
    if sa.contains(&sb) || sb.contains(&sa) {
        0.2
    } else {
        0.0
    }
}

fn face_text(store: &Store, guest: &Guest, id: &str) -> Option<String> {
    let aid = guest.aliases.borrow().get(id).copied()?;
    let (s, e) = store.atom_se(aid)?;
    Some(if e.is_empty() { s } else { e })
}

fn is_engine_sid(id: &str) -> bool {
    let rest = id.strip_prefix('a').unwrap_or("");
    !rest.is_empty() && rest.chars().all(|c| c.is_ascii_digit()) && id.starts_with('a')
}

fn arg_string(v: Option<&Value>) -> String {
    match v {
        Some(Value::String(s)) => lua_string(s),
        Some(Value::Integer(n)) => n.to_string(),
        Some(Value::Number(n)) => fmt_num(*n),
        Some(Value::Boolean(b)) => b.to_string(),
        _ => String::new(),
    }
}

fn arg_number(v: Option<&Value>) -> Option<f64> {
    match v {
        Some(Value::Integer(n)) => Some(*n as f64),
        Some(Value::Number(n)) => Some(*n),
        Some(Value::String(s)) => s.to_str().ok().and_then(|t| t.parse().ok()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::fs;

    fn guest() -> (Store, Evaluator) {
        let store = Store::new(true);
        let ev = Evaluator::new(&store);
        (store, ev)
    }

    #[test]
    fn one_plus_one() {
        let (store, ev) = guest();
        assert_eq!(ev.eval_line(&store, "return 1+1"), "2");
    }

    #[test]
    fn empty_line() {
        let (store, ev) = guest();
        assert_eq!(ev.eval_line(&store, "   "), "");
    }

    #[test]
    fn local_does_not_leak() {
        let (store, ev) = guest();
        assert_eq!(ev.eval_line(&store, "local x = 1"), "");
        assert_eq!(ev.eval_line(&store, "return x"), "nil");
    }

    #[test]
    fn syntax_is_text() {
        let (store, ev) = guest();
        let s = ev.eval_line(&store, "return (");
        assert!(s.starts_with("blad:"), "{s}");
    }

    #[test]
    fn endless_loop_hits_budget() {
        let (store, ev) = guest();
        ev.set_budget(Some(1_000_000));
        let s = ev.eval_line(&store, "while true do end");
        assert!(s.starts_with("blad:") && s.contains("limit instrukcji"), "{s}");
        // licznik od nowa: następny chunk działa
        assert_eq!(ev.eval_line(&store, "return 6*7"), "42");
    }

    #[test]
    fn pcall_cannot_swallow_budget() {
        let (store, ev) = guest();
        ev.set_budget(Some(1_000_000));
        let s = ev.eval_line(
            &store,
            "while true do pcall(function() while true do end end) end",
        );
        assert!(s.contains("limit instrukcji"), "{s}");
    }

    #[test]
    fn coroutine_loop_hits_budget() {
        let (store, ev) = guest();
        ev.set_budget(Some(1_000_000));
        let s = ev.eval_line(
            &store,
            "local co = coroutine.create(function() while true do end end)              local ok, e = coroutine.resume(co) error(e, 0)",
        );
        assert!(s.contains("limit instrukcji"), "{s}");
    }

    #[test]
    fn xpcall_cannot_swallow_budget() {
        let (store, ev) = guest();
        ev.set_budget(Some(1_000_000));
        let s = ev.eval_line(
            &store,
            "while true do xpcall(function() while true do end end, function(e) return e end) end",
        );
        assert!(s.contains("limit instrukcji"), "{s}");
    }

    #[test]
    fn coroutine_survives_into_next_chunk() {
        // wątek, który przekroczył limit, zostaje na kroku 1; nowy chunk go nie karze
        let (store, ev) = guest();
        ev.set_budget(Some(1_000_000));
        ev.eval_line(
            &store,
            "co = coroutine.wrap(function() local n = 0 \
               while true do n = n + 1 if n % 1000 == 0 then coroutine.yield(n) end end end)",
        );
        let s = ev.eval_line(&store, "local s = 0 for i = 1, 500 do s = co() end return s");
        assert!(s.contains("limit instrukcji"), "{s}");
        let s = ev.eval_line(&store, "local s = 0 for i = 1, 20 do s = s + 1 end return s");
        assert_eq!(s, "20");
    }

    #[test]
    fn budget_can_be_lifted() {
        let (store, ev) = guest();
        assert_eq!(ev.budget(), Some(DEFAULT_BUDGET));
        ev.set_budget(Some(100_000));
        let work = "local s = 0 for i = 1, 200000 do s = s + i end return s";
        assert!(ev.eval_line(&store, work).contains("limit instrukcji"));
        ev.set_budget(None);
        assert_eq!(ev.eval_line(&store, work), "20000100000");
    }

    #[test]
    fn no_ambient_io() {
        let (store, ev) = guest();
        assert_eq!(ev.eval_line(&store, "return io"), "nil");
        assert_eq!(
            ev.eval_line(&store, "return os.execute"),
            "nil"
        );
        assert_eq!(ev.eval_line(&store, "return string.dump"), "nil");
        assert_eq!(ev.eval_line(&store, "return debug"), "nil");
    }

    #[test]
    fn version_and_atoms() {
        let (store, ev) = guest();
        assert_eq!(ev.eval_line(&store, "return karmazyn._VERSION"), "1.1.0");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.create_atom('x', 'sig', 'emb').id"),
            "x"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('x').s"), "sig");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('x').S"), "sig");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('x').e"), "emb");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('x').E"), "emb");
        assert_eq!(ev.eval_line(&store, "return karmazyn.list_atoms()[1].id"), "x");
        assert_eq!(ev.eval_line(&store, "return karmazyn.delete_atom('x')"), "true");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('x')"), "nil");
        assert_eq!(store.atom_count(), 0);
    }

    #[test]
    fn reserved_id_and_idea() {
        let (store, ev) = guest();
        let s = ev.eval_line(&store, "return karmazyn.create_atom('a0', 's', 'e')");
        assert!(s.contains("zarezerwowane"), "{s}");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.generate_from_idea()"),
            "nil"
        );
    }

    #[test]
    fn step_ticks() {
        let (store, ev) = guest();
        assert_eq!(ev.eval_line(&store, "return karmazyn.step(1)"), "1");
        assert_eq!(ev.eval_line(&store, "return karmazyn.T_MAX") , fmt_num(T_MAX));
    }

    #[test]
    fn rooted_atom_survives_settle_and_recall() {
        let (store, ev) = guest();
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.create_atom('n1', 'sig', 'hello').id"),
            "n1"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_temperature()"), "1");
        assert_eq!(ev.eval_line(&store, "return karmazyn.step(80)"), "80");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('n1').e"), "hello");
        assert!(store.has_atom(
            ev.guest.aliases.borrow().get("n1").copied().unwrap()
        ));
        assert_eq!(ev.eval_line(&store, "return karmazyn.recall('hello', 1)[1].id"), "n1");
        assert_eq!(ev.eval_line(&store, "return karmazyn.recall('hello', 1)[1].layer"), "substr");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.create_atom('n2', 'sig', 'hello-world').id"),
            "n2"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_similarity('n1', 'n2')"), "0.2");
        assert_eq!(ev.eval_line(&store, "return karmazyn.consolidate('n1')"), "bubble_n1");
        assert_eq!(ev.eval_line(&store, "return karmazyn.list_bubbles()[1].label"), "bubble_n1");
        let before = store.atom_count();
        assert_eq!(ev.eval_line(&store, "local t = {}; for i=1,1000 do t[i]=i end; t=nil; collectgarbage('collect'); return 'ok'"), "ok");
        assert_eq!(store.atom_count(), before);
    }

    #[test]
    fn session_bubble_is_lua() {
        let (store, ev) = guest();
        assert_eq!(store.bubble_label(ev.env()).as_deref(), Some("lua"));
        assert!(store.is_root(ev.env()));
    }

    #[test]
    fn preload_and_project_and_no_disk_io() {
        let (store, ev) = guest();
        let dir = env::temp_dir().join(format!("karmazyn_lua_proj_{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let bin = dir.join("bin");
        fs::create_dir_all(&bin).unwrap();
        fs::write(bin.join("greet.lua"), "return function(n) return 'hi '..n end").unwrap();
        assert_eq!(ev.install_preload_dir(&bin).unwrap(), 1);
        assert_eq!(
            ev.eval_line(&store, "return require('greet')('Karmazyn')"),
            "hi Karmazyn"
        );
        fs::create_dir_all(dir.join("lib")).unwrap();
        fs::write(dir.join("util.lua"), "return { n = 40 }").unwrap();
        fs::write(dir.join("lib").join("greeter.lua"), "return { hello = 'ok' }").unwrap();
        ev.set_project_root(&dir);
        assert_eq!(ev.eval_line(&store, "return require('util').n"), "40");
        assert_eq!(
            ev.eval_line(&store, "return require('lib.greeter').hello"),
            "ok"
        );
        let denied = ev.eval_line(
            &store,
            "local ok = pcall(function() return io.open('x') end); return ok",
        );
        assert_eq!(denied, "false");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn golden_language() {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/golden");
        let gaps = fs::read_to_string(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("GAPS.md"))
            .unwrap_or_default();
        let (store, ev) = guest();
        let mut n = 0;
        for ent in fs::read_dir(&dir).unwrap() {
            let ent = ent.unwrap();
            let path = ent.path();
            if path.extension().and_then(|s| s.to_str()) != Some("lua") {
                continue;
            }
            let stem = path.file_stem().unwrap().to_string_lossy();
            if gaps.contains(&format!("`{stem}.lua`")) {
                continue;
            }
            let src = fs::read_to_string(&path).unwrap();
            let expected = fs::read_to_string(dir.join(format!("{stem}.out"))).unwrap();
            let got = ev.eval_line(&store, &src);
            assert_eq!(got, expected.trim_end_matches(['\r', '\n']), "{stem}");
            n += 1;
        }
        assert!(n >= 6, "golden cases: {n}");
    }

    #[test]
    fn proxy_ui_epoch_and_session_maps() {
        let (store, ev) = guest();
        assert_eq!(
            ev.eval_line(
                &store,
                "local a = karmazyn.create_atom('p','sig','old', 50); a.set_E('new'); a.set_state('HOT'); local b = karmazyn.get_atom('p'); return b.E .. '|' .. b.state .. '|' .. b.get_T()"
            ),
            "new|HOT|70.0"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.list_atoms('HOT')[1].id"),
            "p"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.list_atoms('WARM')[1]"),
            "nil"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_epoch()"), "0");
        assert_eq!(ev.eval_line(&store, "return karmazyn.step(3)"), "3");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_epoch()"), "3");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.get_resources().total"),
            "1"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.get_resources().HOT"),
            ev.eval_line(&store, "return karmazyn.get_resources().hot")
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.ui.progress_bar(50, 100, 10)"),
            "[#####-----]"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.ui.draw_frame('Hi', {'ab'})"),
            "\
+----------------------+
|          Hi          |
+----------------------+
| ab                   |
+----------------------+"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.read_line('? ')"), "");
        ev.push_input("queued");
        assert_eq!(ev.eval_line(&store, "return karmazyn.read_line('? ')"), "queued");
        assert_eq!(
            ev.eval_line(
                &store,
                "karmazyn.fs.write('notatki','dokument','nano','ala'); return karmazyn.fs.read('notatki','dokument')"
            ),
            "ala"
        );
        assert_eq!(
            ev.eval_line(
                &store,
                "karmazyn.cache.write('n','sig','eman',1); return karmazyn.cache.read('n').E"
            ),
            "eman"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.spawn_agent('io','scan')"),
            "1"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.list_agents()[1].name"),
            "io"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.delete_agent(1)"), "true");
        assert_eq!(ev.eval_line(&store, "return #karmazyn.list_agents()"), "0");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.create_hologram('h1','topic', {'p'})"),
            "h1"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.list_holograms()[1].topic"),
            "topic"
        );
        assert_eq!(
            ev.eval_line(&store, "return type(karmazyn.create_atom('a1','s','e'))"),
            "string"
        );
        let dup = ev.eval_line(&store, "return karmazyn.create_atom('p','s','e')");
        assert!(dup.contains("już istnieje"), "{dup}");
    }

    fn with_bin() -> (Store, Evaluator) {
        let (store, ev) = guest();
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../lua_bin");
        let n = ev.install_preload_dir(&dir).expect("lua_bin");
        assert!(n >= 30, "narzędzi: {n}");
        (store, ev)
    }

    fn require_ok(ev: &Evaluator, store: &Store, name: &str) -> String {
        let out = ev.run_tool(store, name).expect("tool");
        assert!(!out.starts_with("blad:"), "{name}: {out}");
        out
    }

    #[test]
    fn lua_bin_status_tools() {
        let (store, ev) = with_bin();
        let up = require_ok(&ev, &store, "uptime");
        assert!(up.contains("Uptime: 0 epok"), "{up}");
        let who = require_ok(&ev, &store, "whoami");
        assert!(who.contains("Phi State: 0 atoms"), "{who}");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.create_atom('n1','sig','hello').id"),
            "n1"
        );
        let ls = require_ok(&ev, &store, "ls");
        assert!(ls.contains("Φ-LIST"), "{ls}");
        assert!(ls.contains("n1"), "{ls}");
        assert!(ls.contains("WARM"), "{ls}");
        assert!(ls.contains("hello"), "{ls}");
        let df = require_ok(&ev, &store, "df");
        assert!(df.contains("SYSTEM STATISTICS"), "{df}");
        assert!(df.contains("Atomy w WARM: 1"), "{df}");
        assert!(df.contains("STABILNY"), "{df}");
        let free = require_ok(&ev, &store, "free");
        assert!(free.contains("RESOURCES"), "{free}");
        assert!(free.contains("Store.total"), "{free}");
        let du = require_ok(&ev, &store, "du");
        assert!(du.contains("EMANATION USAGE"), "{du}");
        let lsb = require_ok(&ev, &store, "lsb");
        assert!(lsb.contains("Brak trwałych bąbli"), "{lsb}");
        let idea = require_ok(&ev, &store, "idea");
        assert!(idea.contains("wycofane"), "{idea}");
        let ps = require_ok(&ev, &store, "ps");
        assert!(ps.contains("Brak aktywnych agentów"), "{ps}");
        let lsh = require_ok(&ev, &store, "lsh");
        assert!(lsh.contains("Brak etykiet hologramu"), "{lsh}");
        let star = require_ok(&ev, &store, "starlink");
        assert!(star.contains("STARLINK"), "{star}");
        let probe = require_ok(&ev, &store, "bubble_probe");
        assert!(probe.contains("bubble_probe"), "{probe}");
        let clear = require_ok(&ev, &store, "clear");
        assert_eq!(clear, "");
    }

    #[test]
    fn lua_bin_queued_tools() {
        let (store, ev) = with_bin();
        ev.push_input("n1");
        ev.push_input("sig");
        ev.push_input("hello");
        ev.push_input("");
        let touch = require_ok(&ev, &store, "touch");
        assert!(touch.contains("Stworzono atom: n1"), "{touch}");

        ev.push_input("n1");
        let cat = require_ok(&ev, &store, "cat");
        assert!(cat.contains("hello"), "{cat}");

        ev.push_input("n1");
        let stat = require_ok(&ev, &store, "stat");
        assert!(stat.contains("METADATA"), "{stat}");
        assert!(stat.contains("WARM"), "{stat}");

        ev.push_input("n1");
        ev.push_input("HOT");
        let mv = require_ok(&ev, &store, "mv");
        assert!(mv.contains("Przeniesiono do HOT"), "{mv}");

        ev.push_input("hello");
        let grep = require_ok(&ev, &store, "grep");
        assert!(grep.contains("Znaleziono 1"), "{grep}");

        ev.push_input("HOT");
        ev.push_input("0");
        let find = require_ok(&ev, &store, "find");
        assert!(find.contains("FIND RESULTS"), "{find}");
        assert!(find.contains("n1"), "{find}");

        ev.push_input("n1");
        ev.push_input("n2");
        let cp = require_ok(&ev, &store, "cp");
        assert!(cp.contains("n1 → n2"), "{cp}");

        ev.push_input("n1");
        ev.push_input("n2");
        let ping = require_ok(&ev, &store, "ping");
        assert!(ping.contains("SEMANTIC PING"), "{ping}");

        ev.push_input("hello");
        let recall = require_ok(&ev, &store, "recall");
        assert!(recall.contains("RECALL:"), "{recall}");

        ev.push_input("2");
        let step = require_ok(&ev, &store, "step");
        assert!(step.contains("2 epok"), "{step}");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_epoch()"), "2");

        ev.push_input("n1");
        let cons = require_ok(&ev, &store, "consolidate");
        assert!(cons.contains("bubble_n1"), "{cons}");
        let lsb = require_ok(&ev, &store, "lsb");
        assert!(lsb.contains("bubble_n1"), "{lsb}");

        ev.push_input("n1");
        ev.push_input("4");
        let kedit = require_ok(&ev, &store, "kedit");
        assert!(kedit.contains("KEDIT"), "{kedit}");

        ev.push_input("");
        let man = require_ok(&ev, &store, "man");
        assert!(man.contains("DOSTĘPNE NARZĘDZIA"), "{man}");

        ev.push_input("9");
        let kill = require_ok(&ev, &store, "kill");
        assert!(kill.contains("Nie znaleziono"), "{kill}");

        ev.push_input("n1");
        let rm = require_ok(&ev, &store, "rm");
        assert!(rm.contains("usunięty"), "{rm}");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('n1')"), "nil");
    }

    #[test]
    fn lua_bin_memviz() {
        let (store, ev) = with_bin();
        let out = require_ok(&ev, &store, "memviz");
        assert!(out.contains("MEMVIZ DONE"), "{out}");
        assert!(out.contains("delta_copy"), "{out}");
        assert!(!out.contains("! create"), "{out}");
    }

    #[test]
    fn live_proxy_print_remount_and_tool_args() {
        let (store, ev) = guest();
        assert_eq!(
            ev.eval_line(
                &store,
                "local a = karmazyn.create_atom('k','s','old'); a.set_E('nowe'); a.set_state('COLD'); return a.E .. '|' .. a.state .. '|' .. a.age"
            ),
            "nowe|COLD|0"
        );
        assert_eq!(ev.eval_line(&store, "return karmazyn.step(4)"), "4");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('k').age"), "4");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('k').E"), "nowe");
        assert_eq!(ev.eval_line(&store, "print('hi'); return 2"), "hi\n2");
        assert_eq!(ev.eval_line(&store, "return karmazyn.interactive()"), "false");
        ev.enable_stdin(true);
        assert_eq!(ev.eval_line(&store, "return karmazyn.interactive()"), "true");
        ev.enable_stdin(false);

        let snap = store.export_snapshot();
        store.import_snapshot(&snap);
        ev.guest.aliases.borrow_mut().clear();
        ev.guest.born.borrow_mut().clear();
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('k')"), "nil");
        ev.remount_session(&store);
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('k').E"), "nowe");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('k').age"), "0");

        ev.install_preload(
            "echoargs",
            "local a,b = ...; print(tostring(a)..':'..tostring(b))",
        )
        .unwrap();
        assert_eq!(ev.run_tool(&store, "echoargs foo bar").unwrap(), "foo:bar");
        let missing = ev.run_tool(&store, "brak_takiego").unwrap();
        assert!(missing.starts_with("blad:"), "{missing}");
        assert!(ev.run_tool(&store, "../x").is_err());
        assert!(ev.run_tool(&store, "echoargs a'b").is_err());
        assert!(ev.run_tool(&store, "  ").is_err());
    }

    #[test]
    fn frame_splits_newlines() {
        let (store, ev) = guest();
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.ui.draw_frame('Hi', {'a\\nb'})"),
            "\
+----------------------+
|          Hi          |
+----------------------+
| a                    |
| b                    |
+----------------------+"
        );
    }

    #[test]
    fn add_epoch_ages_alias() {
        let (store, ev) = guest();
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.create_atom('z','s','e').id"),
            "z"
        );
        ev.add_epoch(5);
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_epoch()"), "5");
        assert_eq!(ev.eval_line(&store, "return karmazyn.get_atom('z').age"), "5");
    }

    #[test]
    fn lua_bin_nano_top_and_starlink_hot() {
        let (store, ev) = with_bin();
        assert_eq!(
            ev.eval_line(
                &store,
                "return karmazyn.create_atom('nano_arch','nano','z-atomu', karmazyn.T_INIT).id"
            ),
            "nano_arch"
        );
        ev.push_input(".abort");
        let restored = require_ok(&ev, &store, "nano arch");
        assert!(restored.contains("z-atomu"), "{restored}");
        ev.eval_line(
            &store,
            "karmazyn.fs.write('arch','dokument','nano','z-fs'); return 1",
        );
        ev.push_input(".abort");
        let prefer_fs = require_ok(&ev, &store, "nano arch");
        assert!(prefer_fs.contains("z-fs"), "{prefer_fs}");

        ev.push_input("linia");
        ev.push_input(".save");
        let nano = require_ok(&ev, &store, "nano");
        assert!(nano.contains("Zapisano"), "{nano}");
        assert!(nano.contains("nano_notatki"), "{nano}");
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.fs.read('notatki','dokument')"),
            "linia"
        );
        assert_eq!(
            ev.eval_line(&store, "return karmazyn.get_atom('nano_notatki').E"),
            "linia"
        );

        ev.push_input(".abort");
        let named = require_ok(&ev, &store, "nano brudnopis");
        assert!(named.contains("brudnopis"), "{named}");
        assert!(named.contains("Anulowano"), "{named}");

        let top = require_ok(&ev, &store, "top");
        assert!(top.contains("KARMAZYN TOP"), "{top}");

        let hot = require_ok(&ev, &store, "starlink_hot");
        assert!(hot.contains("STARLINK HOT"), "{hot}");
    }
}
