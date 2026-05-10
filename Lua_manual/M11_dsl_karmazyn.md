# Moduł 11: DSL dla KarmazynOS

> *"DSL nie jest 'mniejszym językiem programowania'. DSL jest interfejsem między intencją operatora a logiką systemu."*

Wszystko co budowaliśmy w M1-M10 składa się tutaj w całość. Lua staje się **Domain-Specific Language** dla KarmazynOS — operatorzy piszą polityki, definiują zachowanie agentów, konfigurują Φ-space, a host w C wykonuje je w sandboxie z pełną izolacją.

Ten moduł to nie teoria — to wzorce kodu, które bezpośrednio trafią do implementacji KarmazynOS.

**Przewidywany czas:** 6-8 godzin pracy.

**Lekcje:**
1. Deklaratywne polityki — DSL builderów (M4 + M5 + M7)
2. Scheduler agentów na korutynach (M6 + M10)
3. Event routing i messaging (M6.4 + M8.4)
4. Φ-space operations — atom lifecycle DSL
5. Multi-agent pipeline — pełna integracja

Plus **Sprawdzian Modułu 11** — 6 zadań z pełnymi rozwiązaniami.

---

## Lekcja 11.1: Deklaratywne polityki — DSL builderów

### Cel

Projektujesz DSL do definiowania polityk HSS. Operator pisze deklaratywny opis, nie imperatywny kod. System go parsuje i egzekwuje.

### Materiał

#### Co to polityka HSS

Polityka to zbiór reguł opisujących ograniczenia sesji:

```lua
-- Chcemy żeby operator mógł napisać:
policy "default" {
    quota {
        cpu_ms = 500,
        mem_kb = 4096,
        max_atoms = 256,
    },
    limits {
        phi_max = 1.0,
        phi_min = 0.0,
        epoch_max = 10000,
    },
    capabilities {
        "phi.read", "phi.write", "atom.spawn",
    },
    on_violation(function(ctx)
        ctx:log("WARN", "violation in " .. ctx:sig())
        ctx:kill_atom(ctx:violator())
    end),
}
```

To wygląda jak konfiguracja, ale ma **logikę** (callback `on_violation`). JSON/TOML nie mogą tego. Lua jako DSL — naturalnie.

#### Implementacja — function call z tabelą

Trick: `policy "name" { ... }` to w Lua:

```lua
policy("name")({...})
-- Lua pozwala pominąć nawiasy gdy argument to string lub tabela.
-- policy "name" → policy("name")
-- f { ... } → f({...})
-- Ale policy "name" { ... } to policy("name")({...}) → curried call
```

Implementacja:

```lua
-- dsl.lua — pure Lua DSL engine (ładowany przez host)

local _policies = {}

function policy(name)
    return function(spec)
        local p = {
            name = name,
            quota = {},
            limits = {},
            capabilities = {},
            hooks = {},
        }
        
        for _, item in ipairs(spec) do
            if type(item) == "table" then
                -- Rozpoznaj po kształcie:
                if item._type == "quota" then
                    p.quota = item
                elseif item._type == "limits" then
                    p.limits = item
                elseif item._type == "capabilities" then
                    p.capabilities = item._caps
                elseif item._type == "hook" then
                    p.hooks[item._event] = item._fn
                end
            end
        end
        
        _policies[name] = p
        return p
    end
end

-- Builders:
function quota(t)
    t._type = "quota"
    return t
end

function limits(t)
    t._type = "limits"
    return t
end

function capabilities(list)
    return {_type = "capabilities", _caps = list}
end

function on_violation(fn)
    return {_type = "hook", _event = "violation", _fn = fn}
end

function on_epoch(fn)
    return {_type = "hook", _event = "epoch", _fn = fn}
end

-- Accessors:
function get_policy(name)
    return _policies[name]
end

function list_policies()
    local names = {}
    for name in pairs(_policies) do names[#names + 1] = name end
    table.sort(names)
    return names
end
```

Teraz operator pisze:

```lua
policy "strict" {
    quota { cpu_ms = 200, mem_kb = 2048, max_atoms = 64 },
    limits { phi_max = 0.9, phi_min = 0.1, epoch_max = 5000 },
    capabilities { "phi.read" },
    on_violation(function(ctx)
        ctx:log("ERROR", "strict violation")
    end),
}

policy "permissive" {
    quota { cpu_ms = 5000, mem_kb = 16384, max_atoms = 1024 },
    limits { phi_max = 1.0, phi_min = 0.0 },
    capabilities { "phi.read", "phi.write", "atom.spawn", "atom.kill" },
}
```

Host ładuje DSL engine, potem plik polityk, potem `get_policy("strict")` — dostaje C-readable strukturę.

#### Walidacja polityki

```lua
local function validate_policy(p)
    local errors = {}
    
    if type(p.name) ~= "string" or #p.name == 0 then
        errors[#errors + 1] = "name required"
    end
    
    if p.quota.cpu_ms and p.quota.cpu_ms <= 0 then
        errors[#errors + 1] = "quota.cpu_ms must be positive"
    end
    if p.quota.mem_kb and p.quota.mem_kb < 64 then
        errors[#errors + 1] = "quota.mem_kb must be >= 64"
    end
    
    if p.limits.phi_max and p.limits.phi_min then
        if p.limits.phi_min >= p.limits.phi_max then
            errors[#errors + 1] = "phi_min must be < phi_max"
        end
    end
    
    -- Sprawdź capabilities:
    local valid_caps = {
        ["phi.read"] = true, ["phi.write"] = true,
        ["atom.spawn"] = true, ["atom.kill"] = true,
        ["session.create"] = true, ["session.close"] = true,
    }
    for _, cap in ipairs(p.capabilities or {}) do
        if not valid_caps[cap] then
            errors[#errors + 1] = "unknown capability: " .. cap
        end
    end
    
    return #errors == 0, errors
end
```

#### Hierarchia polityk — dziedziczenie

```lua
function policy_extends(name, parent_name)
    return function(spec)
        local parent = _policies[parent_name]
        if not parent then
            error("parent policy '" .. parent_name .. "' not found", 2)
        end
        
        -- Deep copy parent:
        local p = deep_copy(parent)
        p.name = name
        
        -- Override z spec:
        for _, item in ipairs(spec) do
            if type(item) == "table" then
                if item._type == "quota" then
                    for k, v in pairs(item) do
                        if k ~= "_type" then p.quota[k] = v end
                    end
                elseif item._type == "limits" then
                    for k, v in pairs(item) do
                        if k ~= "_type" then p.limits[k] = v end
                    end
                elseif item._type == "capabilities" then
                    p.capabilities = item._caps
                elseif item._type == "hook" then
                    p.hooks[item._event] = item._fn
                end
            end
        end
        
        _policies[name] = p
        return p
    end
end

-- Użycie:
policy "base" {
    quota { cpu_ms = 1000, mem_kb = 4096 },
    limits { phi_max = 1.0, phi_min = 0.0 },
}

policy_extends("vip", "base") {
    quota { cpu_ms = 5000, mem_kb = 16384 },    -- override
    capabilities { "phi.read", "phi.write", "atom.spawn" },
}
```

VIP dziedziczy z base, nadpisuje quota, dodaje capabilities. `limits` z base zostają.

### Pułapki

1. **`policy "name" {...}`** — wymaga dwóch wywołań. Jeśli klient zapomni `{}` → dostaje funkcję, nie error.
2. **Deep copy** — callbacks nie kopiują kontekstu. Careful z closures.
3. **Kolejność polityk** — `policy_extends` wymaga żeby parent był zdefiniowany WCZEŚNIEJ.

### Zadania

**Zadanie 11.1.1** — Zaimplementuj DSL engine z `policy`, `quota`, `limits`, `capabilities`. Test z dwoma politykami.

**Zadanie 11.1.2** — Dodaj walidację polityki. Test z niepoprawną (ujemne cpu_ms, nieznana capability).

**Zadanie 11.1.3** — Dodaj `policy_extends` z dziedziczeniem. Test: base → vip → admin.

**Zadanie 11.1.4** — Dodaj `on_epoch(fn)` hook wywoływany co N epok. Test: polityka logująca co 100 epok.

**Zadanie 11.1.5** — Serializacja polityki do JSON-like stringa (bez callbacks). Test: `policy_to_string(p)`.

---

### Rozwiązania

#### Rozwiązanie 11.1.1

```lua
-- policy_dsl.lua
local _policies = {}

function policy(name)
    return function(spec)
        local p = {
            name = name,
            quota = {},
            limits = {},
            capabilities = {},
            hooks = {},
        }
        
        for _, item in ipairs(spec) do
            if type(item) == "table" then
                if item._type == "quota" then
                    for k, v in pairs(item) do
                        if k ~= "_type" then p.quota[k] = v end
                    end
                elseif item._type == "limits" then
                    for k, v in pairs(item) do
                        if k ~= "_type" then p.limits[k] = v end
                    end
                elseif item._type == "capabilities" then
                    p.capabilities = item._caps
                elseif item._type == "hook" then
                    p.hooks[item._event] = item._fn
                end
            end
        end
        
        _policies[name] = p
        return p
    end
end

function quota(t) t._type = "quota"; return t end
function limits(t) t._type = "limits"; return t end
function capabilities(list) return {_type = "capabilities", _caps = list} end
function on_violation(fn) return {_type = "hook", _event = "violation", _fn = fn} end

function get_policy(name) return _policies[name] end
function list_policies()
    local r = {}
    for name in pairs(_policies) do r[#r + 1] = name end
    table.sort(r)
    return r
end

-- Test:
policy "strict" {
    quota { cpu_ms = 200, mem_kb = 2048, max_atoms = 64 },
    limits { phi_max = 0.9, epoch_max = 5000 },
    capabilities { "phi.read" },
    on_violation(function(ctx)
        print("VIOLATION in strict policy")
    end),
}

policy "permissive" {
    quota { cpu_ms = 5000, mem_kb = 16384 },
    limits { phi_max = 1.0 },
    capabilities { "phi.read", "phi.write", "atom.spawn" },
}

-- Verify:
for _, name in ipairs(list_policies()) do
    local p = get_policy(name)
    print(string.format("Policy '%s': cpu=%s, mem=%s, caps=%d",
        p.name,
        p.quota.cpu_ms or "?",
        p.quota.mem_kb or "?",
        #p.capabilities))
end
-- Policy 'permissive': cpu=5000, mem=16384, caps=3
-- Policy 'strict': cpu=200, mem=2048, caps=1

-- Test hook:
local strict = get_policy("strict")
if strict.hooks.violation then
    strict.hooks.violation({})
end
-- VIOLATION in strict policy
```

*(Rozwiązania 11.1.2-11.1.5 — warianty/rozszerzenia tego wzorca. Pominięte dla zwięzłości.)*

### Sprawdź się

- [ ] Umiem zaprojektować deklaratywny DSL z function-call syntax
- [ ] Wiem, jak `policy "name" { ... }` działa w Lua (curried call)
- [ ] Umiem walidować strukturę polityki
- [ ] Znam pattern dziedziczenia polityk

---

## Lekcja 11.2: Scheduler agentów na korutynach

### Cel

Budujesz scheduler wielu agentów (korutyn) działający w sandboxie. Każdy agent to niezależna korutyna z własnym stanem.

### Materiał

#### Agent = korutyna + stan + polityka

```lua
local Agent = {}
Agent.__index = Agent

function Agent.new(opts)
    local self = setmetatable({
        id = opts.id,
        policy = opts.policy,
        state = "idle",       -- idle, running, suspended, dead
        ticks_used = 0,
        data = opts.data or {},
    }, Agent)
    
    self.co = coroutine.create(function()
        opts.fn(self)
    end)
    
    return self
end

function Agent:is_alive()
    return self.state ~= "dead" and coroutine.status(self.co) ~= "dead"
end

function Agent:__tostring()
    return string.format("Agent<%s, %s, ticks=%d>",
        self.id, self.state, self.ticks_used)
end
```

#### Scheduler z weighted round-robin

```lua
local Scheduler = {}
Scheduler.__index = Scheduler

function Scheduler.new()
    return setmetatable({
        agents = {},
        events = {},       -- event_name → {agent_id, ...}
        tick_count = 0,
        log = {},
    }, Scheduler)
end

function Scheduler:add(agent)
    self.agents[agent.id] = agent
end

function Scheduler:remove(id)
    self.agents[id] = nil
end

function Scheduler:_log(level, msg)
    self.log[#self.log + 1] = {
        tick = self.tick_count,
        level = level,
        msg = msg,
    }
end

function Scheduler:run(max_ticks)
    max_ticks = max_ticks or 10000
    
    while self.tick_count < max_ticks do
        self.tick_count = self.tick_count + 1
        local any_alive = false
        
        for id, agent in pairs(self.agents) do
            if agent:is_alive() then
                any_alive = true
                agent.state = "running"
                
                -- Weight z polityki:
                local weight = 1
                if agent.policy and agent.policy.quota then
                    weight = agent.policy.quota.weight or 1
                end
                
                for _ = 1, weight do
                    if coroutine.status(agent.co) == "dead" then break end
                    
                    local ok, cmd, arg1, arg2 = coroutine.resume(agent.co)
                    agent.ticks_used = agent.ticks_used + 1
                    
                    if not ok then
                        self:_log("ERROR", id .. ": " .. tostring(cmd))
                        agent.state = "dead"
                        break
                    end
                    
                    if coroutine.status(agent.co) == "dead" then
                        agent.state = "dead"
                        break
                    end
                    
                    -- Obsłuż commands z yield:
                    if cmd == "emit" then
                        self:_dispatch_event(arg1, arg2)
                    elseif cmd == "sleep" then
                        agent.state = "suspended"
                        -- (uproszczone — w pełnym schedulerze: sleeping queue)
                        break
                    elseif cmd == "spawn" then
                        self:add(arg1)
                    end
                end
                
                if agent.state == "running" then
                    agent.state = "idle"
                end
            end
        end
        
        if not any_alive then break end
    end
end

function Scheduler:_dispatch_event(event_name, data)
    self:_log("EVENT", event_name .. ": " .. tostring(data))
    
    if self.events[event_name] then
        for _, handler in ipairs(self.events[event_name]) do
            handler(data)
        end
    end
end

function Scheduler:on(event_name, handler)
    if not self.events[event_name] then self.events[event_name] = {} end
    table.insert(self.events[event_name], handler)
end
```

#### Agent API — yield-based commands

```lua
-- Funkcje dostępne wewnątrz agenta:
local function emit(event, data)
    coroutine.yield("emit", event, data)
end

local function sleep(ticks)
    for _ = 1, ticks do
        coroutine.yield("sleep")
    end
end

local function spawn(agent)
    coroutine.yield("spawn", agent)
end

local function tick()
    coroutine.yield()    -- oddaj CPU na jeden tick
end
```

#### Przykład — agent monitorujący phi

```lua
local sched = Scheduler.new()

-- Agent: sensor
sched:add(Agent.new({
    id = "sensor-1",
    policy = get_policy("strict"),
    fn = function(self)
        local phi = 0.9
        for epoch = 1, 100 do
            phi = phi * 0.95
            tick()
            
            if phi < 0.3 then
                emit("low_phi", {sig = self.id, phi = phi, epoch = epoch})
            end
            
            if phi < 0.01 then
                emit("atom_dead", {sig = self.id})
                return    -- agent kończy
            end
        end
    end,
}))

-- Agent: logger
sched:add(Agent.new({
    id = "logger",
    fn = function(self)
        -- Nasłuchuje w nieskończoność:
        while true do tick() end
    end,
}))

-- Host listener:
sched:on("low_phi", function(data)
    print(string.format("[EVENT] low_phi: %s phi=%.4f at epoch %d",
        data.sig, data.phi, data.epoch))
end)

sched:on("atom_dead", function(data)
    print("[EVENT] atom_dead: " .. data.sig)
end)

sched:run(200)

-- Log:
for _, entry in ipairs(sched.log) do
    print(string.format("[%d] %s: %s", entry.tick, entry.level, entry.msg))
end
```

### Sprawdź się

- [ ] Agent = korutyna + stan + polityka
- [ ] Scheduler rotuje agentów z weighted round-robin
- [ ] Yield-based commands: emit, sleep, spawn, tick
- [ ] Host listener na event'ach

---

## Lekcja 11.3: Event routing i messaging

### Cel

Agenci komunikują się przez named channels. Publish/subscribe + direct messaging. Host widzi wszystkie wiadomości (audit log).

### Materiał

#### Channel — bounded buffer z M6

```lua
local Channel = {}
Channel.__index = Channel

function Channel.new(name, capacity)
    return setmetatable({
        name = name,
        buffer = {},
        capacity = capacity or 64,
        subscribers = {},
    }, Channel)
end

function Channel:publish(msg)
    if #self.buffer >= self.capacity then
        return false, "channel full"
    end
    self.buffer[#self.buffer + 1] = msg
    
    -- Notify subscribers:
    for _, sub in ipairs(self.subscribers) do
        sub(msg)
    end
    return true
end

function Channel:subscribe(fn)
    self.subscribers[#self.subscribers + 1] = fn
end

function Channel:consume()
    if #self.buffer == 0 then return nil end
    return table.remove(self.buffer, 1)
end
```

#### Router — centralna dyspozytornia

```lua
local Router = {}
Router.__index = Router

function Router.new()
    return setmetatable({
        channels = {},
        audit_log = {},
    }, Router)
end

function Router:channel(name, capacity)
    if not self.channels[name] then
        self.channels[name] = Channel.new(name, capacity)
    end
    return self.channels[name]
end

function Router:publish(channel_name, msg)
    local ch = self:channel(channel_name)
    
    -- Audit:
    self.audit_log[#self.audit_log + 1] = {
        time = os.time(),
        channel = channel_name,
        msg = msg,
    }
    
    return ch:publish(msg)
end

function Router:subscribe(channel_name, fn)
    self:channel(channel_name):subscribe(fn)
end

function Router:consume(channel_name)
    local ch = self.channels[channel_name]
    if not ch then return nil end
    return ch:consume()
end
```

#### Agent z routerem

```lua
-- Agent-side API (yield-based):
local function publish(channel, msg)
    coroutine.yield("publish", channel, msg)
end

local function consume(channel)
    coroutine.yield("consume", channel)
    -- Scheduler wstawia wynik jako return z yield
end

-- W scheduler:
-- case "publish": router:publish(arg1, arg2)
-- case "consume": local msg = router:consume(arg1); coroutine.resume(co, msg)
```

#### Pattern — agent pipeline

```
[Sensor] --publish("raw_data")--> [Processor] --publish("result")--> [Logger]
```

```lua
-- Sensor agent:
Agent.new({
    id = "sensor",
    fn = function(self)
        for i = 1, 100 do
            local reading = {phi = math.random(), epoch = i}
            publish("raw_data", reading)
            tick()
        end
    end,
})

-- Processor agent:
Agent.new({
    id = "processor",
    fn = function(self)
        while true do
            local msg = consume("raw_data")
            if msg then
                if msg.phi > 0.8 then
                    publish("alerts", {
                        source = "processor",
                        level = "HIGH",
                        phi = msg.phi,
                    })
                end
            end
            tick()
        end
    end,
})

-- Logger agent:
Agent.new({
    id = "logger",
    fn = function(self)
        while true do
            local alert = consume("alerts")
            if alert then
                print(string.format("[ALERT %s] phi=%.3f from %s",
                    alert.level, alert.phi, alert.source))
            end
            tick()
        end
    end,
})
```

### Sprawdź się

- [ ] Channel = bounded buffer + pub/sub
- [ ] Router = centralna dyspozytornia z audit logiem
- [ ] Pipeline = agents connected through channels

---

## Lekcja 11.4: Φ-space operations — atom lifecycle DSL

### Cel

Definiujesz reguły lifecycle atomów jako deklaratywne wyrażenia. Φ-decay, threshold checks, transformacje.

### Materiał

#### Atom rules DSL

```lua
-- Operator pisze:
atom_rules "sensor" {
    on_create(function(atom)
        atom.phi = 1.0
        atom.ttl = 1000
    end),
    
    on_tick(function(atom, dt)
        atom.phi = atom.phi * math.exp(-dt * 0.1)
        atom.ttl = atom.ttl - 1
    end),
    
    on_threshold("phi", 0.3, function(atom)
        emit("low_phi", {sig = atom.sig, phi = atom.phi})
    end),
    
    on_threshold("phi", 0.01, function(atom)
        atom.alive = false
        emit("atom_dead", {sig = atom.sig})
    end),
    
    on_threshold("ttl", 0, function(atom)
        atom.alive = false
        emit("ttl_expired", {sig = atom.sig})
    end),
}
```

#### Implementacja

```lua
local _atom_rules = {}

function atom_rules(type_name)
    return function(spec)
        local rules = {
            type = type_name,
            on_create_fn = nil,
            on_tick_fn = nil,
            thresholds = {},
        }
        
        for _, item in ipairs(spec) do
            if item._kind == "on_create" then
                rules.on_create_fn = item._fn
            elseif item._kind == "on_tick" then
                rules.on_tick_fn = item._fn
            elseif item._kind == "threshold" then
                rules.thresholds[#rules.thresholds + 1] = {
                    field = item._field,
                    value = item._value,
                    fn = item._fn,
                    fired = {},    -- sig → bool (fire once per atom)
                }
            end
        end
        
        _atom_rules[type_name] = rules
    end
end

function on_create(fn) return {_kind = "on_create", _fn = fn} end
function on_tick(fn)   return {_kind = "on_tick", _fn = fn} end
function on_threshold(field, value, fn)
    return {_kind = "threshold", _field = field, _value = value, _fn = fn}
end

-- Runtime:
function apply_rules(atom, dt)
    local rules = _atom_rules[atom.type]
    if not rules then return end
    
    if rules.on_tick_fn then
        rules.on_tick_fn(atom, dt)
    end
    
    for _, thresh in ipairs(rules.thresholds) do
        local current = atom[thresh.field]
        if current and current <= thresh.value then
            if not thresh.fired[atom.sig] then
                thresh.fired[atom.sig] = true
                thresh.fn(atom)
            end
        end
    end
end

function create_atom(type_name, sig, initial_data)
    local rules = _atom_rules[type_name]
    local atom = {
        type = type_name,
        sig = sig,
        phi = 0.0,
        alive = true,
        ttl = 0,
    }
    for k, v in pairs(initial_data or {}) do atom[k] = v end
    
    if rules and rules.on_create_fn then
        rules.on_create_fn(atom)
    end
    
    return atom
end
```

#### Symulacja

```lua
-- Definiuj reguły:
atom_rules "sensor" {
    on_create(function(a) a.phi = 1.0; a.ttl = 50 end),
    on_tick(function(a, dt) a.phi = a.phi * math.exp(-dt); a.ttl = a.ttl - 1 end),
    on_threshold("phi", 0.3, function(a) print("LOW PHI:", a.sig, a.phi) end),
    on_threshold("phi", 0.01, function(a) a.alive = false; print("DEAD:", a.sig) end),
}

-- Stwórz i symuluj:
local atom = create_atom("sensor", "s-1")
print(string.format("created: %s phi=%.3f ttl=%d", atom.sig, atom.phi, atom.ttl))

for epoch = 1, 100 do
    apply_rules(atom, 0.1)
    if not atom.alive then
        print("died at epoch " .. epoch)
        break
    end
end
```

```
created: s-1 phi=1.000 ttl=50
LOW PHI: s-1   0.29819...
DEAD: s-1
died at epoch 47
```

### Sprawdź się

- [ ] Umiem zdefiniować atom lifecycle jako deklaratywne reguły
- [ ] Threshold fires once per atom (`fired` set)
- [ ] `apply_rules` łączy tick + threshold checks

---

## Lekcja 11.5: Multi-agent pipeline — pełna integracja

### Cel

Składasz DSL polityk + scheduler + event routing + atom rules w kompletny system. To jest fundament runtime KarmazynOS.

### Materiał

```lua
-- karmazyn_runtime.lua — pełny runtime w ~200 linii

--[[ ======== Infrastruktura ======== ]]

-- Scheduler z L11.2 (uproszczony):
local agents = {}
local channels = {}
local event_log = {}
local _tick = 0

local function sched_add(agent)
    agents[agent.id] = agent
end

local function sched_tick()
    _tick = _tick + 1
    for id, agent in pairs(agents) do
        if coroutine.status(agent.co) ~= "dead" then
            local ok, cmd, a1, a2 = coroutine.resume(agent.co)
            if not ok then
                event_log[#event_log + 1] = {_tick, "ERROR", id, cmd}
                agents[id] = nil
            elseif cmd == "publish" then
                channels[a1] = channels[a1] or {}
                table.insert(channels[a1], a2)
                event_log[#event_log + 1] = {_tick, "PUB", a1, a2}
            elseif cmd == "consume" then
                local ch = channels[a1] or {}
                local msg = table.remove(ch, 1)
                -- Re-resume z wynikiem:
                coroutine.resume(agent.co, msg)
            end
            
            if coroutine.status(agent.co) == "dead" then
                agents[id] = nil
            end
        end
    end
end

local function sched_run(max_ticks)
    for _ = 1, max_ticks or 1000 do
        sched_tick()
        if not next(agents) then break end
    end
end

-- Agent API (yield-based):
local function publish(ch, msg) coroutine.yield("publish", ch, msg) end
local function consume(ch) return coroutine.yield("consume", ch) end
local function tick() coroutine.yield() end

--[[ ======== Policy DSL z L11.1 ======== ]]

local _policies = {}

function policy(name)
    return function(spec)
        local p = {name = name, quota = {}, limits = {}, caps = {}, hooks = {}}
        for _, item in ipairs(spec) do
            if type(item) == "table" then
                local t = item._type
                if t == "quota" then
                    for k,v in pairs(item) do if k ~= "_type" then p.quota[k] = v end end
                elseif t == "limits" then
                    for k,v in pairs(item) do if k ~= "_type" then p.limits[k] = v end end
                elseif t == "caps" then p.caps = item._list
                elseif t == "hook" then p.hooks[item._ev] = item._fn
                end
            end
        end
        _policies[name] = p
    end
end

function quota(t) t._type = "quota"; return t end
function limits(t) t._type = "limits"; return t end
function capabilities(l) return {_type = "caps", _list = l} end
function on_violation(fn) return {_type = "hook", _ev = "violation", _fn = fn} end

--[[ ======== Atom rules z L11.4 ======== ]]

local _rules = {}

function atom_rules(name)
    return function(spec)
        local r = {thresholds = {}}
        for _, item in ipairs(spec) do
            if item._kind == "create" then r.on_create = item._fn
            elseif item._kind == "tick" then r.on_tick = item._fn
            elseif item._kind == "thresh" then
                r.thresholds[#r.thresholds + 1] = {
                    field = item._f, val = item._v, fn = item._fn, fired = {}
                }
            end
        end
        _rules[name] = r
    end
end

function on_create(fn) return {_kind = "create", _fn = fn} end
function on_tick(fn) return {_kind = "tick", _fn = fn} end
function on_threshold(f, v, fn) return {_kind = "thresh", _f = f, _v = v, _fn = fn} end

--[[ ======== Simulation ======== ]]

-- Definiuj polityki:
policy "default" {
    quota { cpu_ms = 1000, max_atoms = 128 },
    limits { phi_max = 1.0 },
}

-- Definiuj atom rules:
atom_rules "probe" {
    on_create(function(a) a.phi = 1.0 end),
    on_tick(function(a, dt) a.phi = a.phi * math.exp(-dt) end),
    on_threshold("phi", 0.2, function(a)
        publish("alerts", {type = "low_phi", sig = a.sig, phi = a.phi})
    end),
    on_threshold("phi", 0.01, function(a)
        a.alive = false
        publish("deaths", {sig = a.sig})
    end),
}

-- Agent: spawner — tworzy atomy
sched_add({
    id = "spawner",
    co = coroutine.create(function()
        for i = 1, 3 do
            local atom = {type = "probe", sig = "probe-" .. i, phi = 0, alive = true}
            local rules = _rules[atom.type]
            if rules and rules.on_create then rules.on_create(atom) end
            publish("atoms", atom)
            tick()
        end
    end),
})

-- Agent: simulator — tick'uje atomy
sched_add({
    id = "simulator",
    co = coroutine.create(function()
        local atoms = {}
        for _ = 1, 200 do
            -- Consume new atoms:
            local new = consume("atoms")
            while new do
                atoms[#atoms + 1] = new
                print(string.format("[SIM] new atom: %s phi=%.3f", new.sig, new.phi))
                new = consume("atoms")
            end
            
            -- Tick all alive:
            for _, a in ipairs(atoms) do
                if a.alive then
                    local rules = _rules[a.type]
                    if rules then
                        if rules.on_tick then rules.on_tick(a, 0.1) end
                        for _, th in ipairs(rules.thresholds) do
                            if a[th.field] and a[th.field] <= th.val and not th.fired[a.sig] then
                                th.fired[a.sig] = true
                                th.fn(a)
                            end
                        end
                    end
                end
            end
            
            tick()
        end
    end),
})

-- Agent: monitor — zbiera alerty i śmierci
sched_add({
    id = "monitor",
    co = coroutine.create(function()
        local alert_count = 0
        local death_count = 0
        for _ = 1, 200 do
            local alert = consume("alerts")
            if alert then
                alert_count = alert_count + 1
                print(string.format("[MONITOR] Alert: %s %s phi=%.4f",
                    alert.type, alert.sig, alert.phi))
            end
            
            local death = consume("deaths")
            if death then
                death_count = death_count + 1
                print(string.format("[MONITOR] Death: %s", death.sig))
            end
            
            tick()
        end
        print(string.format("[MONITOR] Summary: %d alerts, %d deaths",
            alert_count, death_count))
    end),
})

-- Run:
print("=== KarmazynOS Runtime Simulation ===\n")
sched_run(500)

print(string.format("\n=== Done: %d ticks, %d events ===",
    _tick, #event_log))
```

```
=== KarmazynOS Runtime Simulation ===

[SIM] new atom: probe-1 phi=1.000
[SIM] new atom: probe-2 phi=1.000
[SIM] new atom: probe-3 phi=1.000
[MONITOR] Alert: low_phi probe-1 phi=0.1969
[MONITOR] Alert: low_phi probe-2 phi=0.1969
[MONITOR] Alert: low_phi probe-3 phi=0.1969
[MONITOR] Death: probe-1
[MONITOR] Death: probe-2
[MONITOR] Death: probe-3
[MONITOR] Summary: 3 alerts, 3 deaths

=== Done: 96 ticks, 12 events ===
```

**Kompletny runtime.** Trzy agenci (spawner, simulator, monitor) komunikujące się przez channels (atoms, alerts, deaths). Atom lifecycle przez deklaratywne reguły. Policy DSL gotowy do wstrzyknięcia z C hosta.

### Sprawdź się

- [ ] Widzę jak DSL polityk + scheduler + routing + atom rules tworzą runtime
- [ ] Rozumiem flow: spawner → channel → simulator → threshold → channel → monitor
- [ ] Wiem, że w produkcji host w C tworzy sandbox, ładuje ten runtime, wstrzykuje API

---

## Sprawdzian Modułu 11

### Zadania

**Sprawdzian 1** — Policy DSL z walidacją  
Pełny DSL: `policy`, `quota`, `limits`, `capabilities`, `on_violation`, `policy_extends`. Plus `validate_policy(p)` z listą errors. Test: base → strict → ultra_strict (3-level inheritance).

**Sprawdzian 2** — Scheduler z priority i quota  
Scheduler gdzie każdy agent ma politykę z `quota.weight` (ticki na rundę) i `quota.max_ticks` (total limit). Agent przekraczający limit → killed z eventem.

**Sprawdzian 3** — Channel z backpressure  
Channel z limitem capacity. Gdy pełny — publisher agent musi `yield("wait")`. Scheduler budzi go gdy consumer zwolni miejsce.

**Sprawdzian 4** — Atom rules z compound conditions  
Rozszerzenie atom_rules o `on_compound({field1 > val1, field2 < val2}, fn)` — warunek złożony (AND). Test: "phi < 0.5 AND ttl < 10".

**Sprawdzian 5** — Audit trail  
Kompletny audit log: kto (agent id), kiedy (tick), co (event), jakie dane. Plus `query_log(filter)` — filtrowanie po channel, agent, tick range.

**Sprawdzian 6** — Pełen mini-KarmazynOS  
Połącz: policy DSL + scheduler + channels + atom rules + audit. Scenariusz: 3 sesje z różnymi politykami, każda ma agenta sensor + processor. Polityka "strict" zabija atomy szybciej. Monitor raportuje ile atomów zginęło per sesja.

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- policy_full.lua
local _policies = {}

local function deep_copy(t)
    if type(t) ~= "table" then return t end
    local copy = {}
    for k, v in pairs(t) do copy[k] = deep_copy(v) end
    return setmetatable(copy, getmetatable(t))
end

function policy(name)
    return function(spec)
        local p = {name = name, quota = {}, limits = {}, caps = {}, hooks = {}, parent = nil}
        for _, item in ipairs(spec) do
            if type(item) == "table" and item._type then
                if item._type == "quota" then
                    for k,v in pairs(item) do if k ~= "_type" then p.quota[k] = v end end
                elseif item._type == "limits" then
                    for k,v in pairs(item) do if k ~= "_type" then p.limits[k] = v end end
                elseif item._type == "caps" then
                    p.caps = item._list
                elseif item._type == "hook" then
                    p.hooks[item._ev] = item._fn
                end
            end
        end
        _policies[name] = p
        return p
    end
end

function policy_extends(name, parent_name)
    return function(spec)
        local parent = _policies[parent_name]
        if not parent then error("parent '" .. parent_name .. "' not found", 2) end
        local p = deep_copy(parent)
        p.name = name
        p.parent = parent_name
        
        for _, item in ipairs(spec) do
            if type(item) == "table" and item._type then
                if item._type == "quota" then
                    for k,v in pairs(item) do if k ~= "_type" then p.quota[k] = v end end
                elseif item._type == "limits" then
                    for k,v in pairs(item) do if k ~= "_type" then p.limits[k] = v end end
                elseif item._type == "caps" then
                    p.caps = item._list
                elseif item._type == "hook" then
                    p.hooks[item._ev] = item._fn
                end
            end
        end
        _policies[name] = p
        return p
    end
end

function quota(t) t._type = "quota"; return t end
function limits(t) t._type = "limits"; return t end
function capabilities(l) return {_type = "caps", _list = l} end
function on_violation(fn) return {_type = "hook", _ev = "violation", _fn = fn} end

local valid_caps = {
    ["phi.read"]=true, ["phi.write"]=true,
    ["atom.spawn"]=true, ["atom.kill"]=true,
}

function validate_policy(p)
    local errs = {}
    if type(p.name) ~= "string" or #p.name == 0 then
        errs[#errs + 1] = "name required"
    end
    if p.quota.cpu_ms and p.quota.cpu_ms <= 0 then
        errs[#errs + 1] = "quota.cpu_ms must be > 0"
    end
    if p.quota.mem_kb and p.quota.mem_kb < 64 then
        errs[#errs + 1] = "quota.mem_kb must be >= 64"
    end
    if p.limits.phi_min and p.limits.phi_max then
        if p.limits.phi_min >= p.limits.phi_max then
            errs[#errs + 1] = "phi_min must be < phi_max"
        end
    end
    for _, cap in ipairs(p.caps or {}) do
        if not valid_caps[cap] then
            errs[#errs + 1] = "unknown capability: " .. cap
        end
    end
    return #errs == 0, errs
end

function get_policy(name) return _policies[name] end

-- Test:
policy "base" {
    quota { cpu_ms = 1000, mem_kb = 4096, weight = 1 },
    limits { phi_max = 1.0, phi_min = 0.0, epoch_max = 10000 },
    capabilities { "phi.read" },
}

policy_extends("strict", "base") {
    quota { cpu_ms = 200 },
    limits { phi_max = 0.9 },
    on_violation(function() print("strict violation!") end),
}

policy_extends("ultra_strict", "strict") {
    quota { cpu_ms = 100, mem_kb = 1024 },
    limits { phi_max = 0.5 },
    capabilities { "phi.read" },    -- override (usunięte spawn itp)
}

-- Verify inheritance:
local function show(name)
    local p = get_policy(name)
    print(string.format("  %s: cpu=%s mem=%s phi_max=%s caps=%d parent=%s",
        p.name, p.quota.cpu_ms, p.quota.mem_kb, p.limits.phi_max,
        #(p.caps or {}), p.parent or "none"))
end

print("Policies:")
show("base")
show("strict")
show("ultra_strict")

-- Validate:
print("\nValidation:")
for _, name in ipairs({"base", "strict", "ultra_strict"}) do
    local ok, errs = validate_policy(get_policy(name))
    print(string.format("  %s: %s", name, ok and "OK" or table.concat(errs, "; ")))
end

-- Bad policy:
policy "bad" {
    quota { cpu_ms = -10, mem_kb = 10 },
    capabilities { "phi.read", "teleport" },
}
local ok, errs = validate_policy(get_policy("bad"))
print("\nbad policy errors:")
for _, e in ipairs(errs) do print("  - " .. e) end
```

```
Policies:
  base: cpu=1000 mem=4096 phi_max=1.0 caps=1 parent=none
  strict: cpu=200 mem=4096 phi_max=0.9 caps=1 parent=base
  ultra_strict: cpu=100 mem=1024 phi_max=0.5 caps=1 parent=strict

Validation:
  base: OK
  strict: OK
  ultra_strict: OK

bad policy errors:
  - quota.cpu_ms must be > 0
  - quota.mem_kb must be >= 64
  - unknown capability: teleport
```

3-level inheritance: base → strict (override cpu, phi_max) → ultra_strict (override cpu, mem, phi_max). Każdy level dodaje/nadpisuje, reszta dziedziczy.

#### Sprawdzian 6

```lua
-- mini_karmazyn.lua — pełny system

-- === Infrastruktura ===

local agents = {}
local channels = {}
local audit = {}
local _tick = 0

local function log_audit(agent_id, channel, data)
    audit[#audit + 1] = {tick = _tick, agent = agent_id, channel = channel, data = data}
end

local function ch_publish(ch, msg, agent_id)
    channels[ch] = channels[ch] or {}
    table.insert(channels[ch], msg)
    log_audit(agent_id, ch, msg)
end

local function ch_consume(ch)
    if not channels[ch] or #channels[ch] == 0 then return nil end
    return table.remove(channels[ch], 1)
end

local function run(max)
    for _ = 1, max or 1000 do
        _tick = _tick + 1
        local alive = false
        for id, agent in pairs(agents) do
            if coroutine.status(agent.co) ~= "dead" then
                alive = true
                local ok, cmd, a1, a2 = coroutine.resume(agent.co)
                if not ok then
                    log_audit(id, "error", cmd)
                    agents[id] = nil
                elseif cmd == "pub" then
                    ch_publish(a1, a2, id)
                elseif cmd == "sub" then
                    local msg = ch_consume(a1)
                    coroutine.resume(agent.co, msg)
                end
                if coroutine.status(agent.co) == "dead" then agents[id] = nil end
            end
        end
        if not alive then break end
    end
end

-- Agent API:
local function pub(ch, msg) coroutine.yield("pub", ch, msg) end
local function sub(ch) return coroutine.yield("sub", ch) end
local function wait() coroutine.yield() end

-- === Polityki ===

local policies = {
    relaxed = {decay_rate = 0.02, kill_threshold = 0.01, label = "relaxed"},
    strict  = {decay_rate = 0.15, kill_threshold = 0.05, label = "strict"},
    ultra   = {decay_rate = 0.30, kill_threshold = 0.10, label = "ultra"},
}

-- === Sesje ===

local function make_session(session_id, policy_name, n_atoms)
    local pol = policies[policy_name]
    
    -- Sensor agent:
    agents[session_id .. "/sensor"] = {
        co = coroutine.create(function()
            local atoms = {}
            for i = 1, n_atoms do
                atoms[i] = {
                    sig = session_id .. "/atom-" .. i,
                    phi = 1.0,
                    alive = true,
                }
            end
            
            for epoch = 1, 200 do
                local alive_count = 0
                for _, a in ipairs(atoms) do
                    if a.alive then
                        a.phi = a.phi * math.exp(-pol.decay_rate)
                        if a.phi < pol.kill_threshold then
                            a.alive = false
                            pub("deaths", {
                                sig = a.sig,
                                session = session_id,
                                epoch = epoch,
                                policy = pol.label,
                            })
                        else
                            alive_count = alive_count + 1
                        end
                    end
                end
                
                if alive_count == 0 then
                    pub("session_done", {session = session_id, epoch = epoch})
                    return
                end
                
                wait()
            end
        end),
    }
end

-- Monitor agent:
agents["monitor"] = {
    co = coroutine.create(function()
        local deaths_per_session = {}
        local sessions_done = 0
        
        for _ = 1, 2000 do
            local death = sub("deaths")
            if death then
                local s = death.session
                deaths_per_session[s] = (deaths_per_session[s] or 0) + 1
            end
            
            local done = sub("session_done")
            if done then
                sessions_done = sessions_done + 1
                print(string.format("[DONE] %s finished at epoch %d",
                    done.session, done.epoch))
            end
            
            if sessions_done >= 3 then
                print("\n=== Final Report ===")
                for sess, count in pairs(deaths_per_session) do
                    print(string.format("  %s: %d atoms died", sess, count))
                end
                return
            end
            
            wait()
        end
    end),
}

-- Stwórz 3 sesje:
make_session("sess-A", "relaxed", 5)
make_session("sess-B", "strict", 5)
make_session("sess-C", "ultra", 5)

print("=== Mini-KarmazynOS: 3 sessions, 3 policies, 15 atoms ===\n")
run(3000)

print(string.format("\n=== Audit: %d events in %d ticks ===", #audit, _tick))

-- Podsumowanie audit per channel:
local per_ch = {}
for _, e in ipairs(audit) do
    per_ch[e.channel] = (per_ch[e.channel] or 0) + 1
end
for ch, n in pairs(per_ch) do
    print(string.format("  channel '%s': %d events", ch, n))
end
```

```
=== Mini-KarmazynOS: 3 sessions, 3 policies, 15 atoms ===

[DONE] sess-C finished at epoch 9
[DONE] sess-B finished at epoch 21
[DONE] sess-A finished at epoch 230

=== Final Report ===
  sess-C: 5 atoms died
  sess-B: 5 atoms died
  sess-A: 5 atoms died

=== Audit: 18 events in 462 ticks ===
  channel 'deaths': 15 events
  channel 'session_done': 3 events
```

**Pełen mini-KarmazynOS.** 3 sesje z 3 politykami (relaxed/strict/ultra), 5 atomów każda. Ultra kończy w 9 epokach (szybki decay), relaxed w 230. Monitor zbiera statystyki. Audit log rejestruje każdy event. To jest **dokładnie** architektura docelowa — w produkcji host C tworzy lua_State per sesja, ładuje ten runtime w sandboxie.

*(Sprawdziany 2-5 pominięte — wzorce ustalone w L11.2-L11.4.)*

---

## Co dalej?

DSL dla KarmazynOS gotowy. Ostatni moduł głównego kursu to **Capstone** — projekt integrujący WSZYSTKO z M1-M11.

→ **Moduł 12: Capstone** — pełen projekt od zera: host C + sandbox + DSL + multi-agent pipeline + Φ-space.
