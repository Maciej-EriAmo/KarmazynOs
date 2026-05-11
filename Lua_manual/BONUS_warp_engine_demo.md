# Moduł Bonus: KarmazynOS Warp Engine — Demo

> *"Entropia nie pyta o pozwolenie. Atom się rozpada, bąbel się kurczy, demon rodzi się z błędnego rytuału."*

Ten moduł to **działające demo** — nie teoria, nie ćwiczenia. Uruchamiasz jednym poleceniem i widzisz KarmazynOS w akcji: atomy z temperaturą, entropijny rozpad, rytuały warp, skażenie chaosu, rój agentów z reakcjami łańcuchowymi.

Demo integruje wzorce z całego kursu: korutyny (M6), moduły (M7), metatable (M4), DSL (M11), error handling (M5). Ale nie musisz znać kursu — kod jest samowystarczalny.

**Uruchomienie:**
```bash
lua5.4 karmazyn_demo.lua
```

---

## Architektura demo

```
karmazyn_demo.lua          — main: symulacja + output
├── karmazyn_core.lua      — mock karmazyn.cache / karmazyn.fs
├── warp_engine.lua        — silnik przejść i entropii (Twój kod)
└── swarm.lua              — rój agentów z chain reactions
```

Dla wygody — **wszystko w jednym pliku** (`karmazyn_demo.lua`). W produkcji rozbijesz na moduły.

---

## Pełny kod demo

```lua
#!/usr/bin/env lua5.4
-- karmazyn_demo.lua
-- KarmazynOS Warp Engine Demo — termodynamiczna mechanika + multi-agent swarm
-- Uruchom: lua5.4 karmazyn_demo.lua

math.randomseed(os.time())

-- ================================================================
-- WARSTWA 0: Kolory terminala (opcjonalne, degradują gracefully)
-- ================================================================

local C = {
    RESET  = "\27[0m",
    RED    = "\27[31m",
    GREEN  = "\27[32m",
    YELLOW = "\27[33m",
    BLUE   = "\27[34m",
    MAGENTA= "\27[35m",
    CYAN   = "\27[36m",
    DIM    = "\27[2m",
    BOLD   = "\27[1m",
}

local function colored(color, text)
    return color .. text .. C.RESET
end

-- ================================================================
-- WARSTWA 1: KarmazynOS Core — cache + filesystem mock
-- ================================================================

karmazyn = {}

-- Cache: szybka pamięć robocza bąbla (RAM atoms)
karmazyn.cache = {}
local _cache_store = {}

function karmazyn.cache.write(id, sig, content, temp)
    _cache_store[id] = {
        id = id,
        S = sig,          -- sygnatura (typ atomu)
        E = content,      -- zawartość (entropia informacyjna)
        T = temp or 0,    -- temperatura (0 = zimny/świeży, 100 = rozpad)
    }
end

function karmazyn.cache.read(id)
    return _cache_store[id]
end

function karmazyn.cache.delete(id)
    _cache_store[id] = nil
end

function karmazyn.cache.list()
    local result = {}
    for id, atom in pairs(_cache_store) do
        result[#result + 1] = atom
    end
    table.sort(result, function(a, b) return a.id < b.id end)
    return result
end

function karmazyn.cache.count()
    local n = 0
    for _ in pairs(_cache_store) do n = n + 1 end
    return n
end

-- Filesystem: trwała pamięć bąbli (bubble persistence)
karmazyn.fs = {}
local _fs_store = {}

function karmazyn.fs.write(bubble, key, data)
    if not _fs_store[bubble] then _fs_store[bubble] = {} end
    _fs_store[bubble][key] = data
end

function karmazyn.fs.read(bubble, key)
    if not _fs_store[bubble] then return nil end
    return _fs_store[bubble][key]
end

-- ================================================================
-- WARSTWA 2: Warp Engine — silnik przejść i entropii
-- ================================================================

local warp = {}

local MAX_TEMP = 100
local CRITICAL_TEMP = 90

local function is_critical(item)
    return item.T >= MAX_TEMP
end

function warp.read_item(atom_id)
    local item = karmazyn.cache.read(atom_id)

    if not item then
        return {
            text = "Przedmiot całkowicie zbutwiał. Został wchłonięty przez Próżnię.",
            status = "vacuum",
            alive = false,
        }
    end

    if is_critical(item) then
        return {
            text = "Przedmiot osiągnął punkt krytyczny. Rozpada się w twoich dłoniach.",
            status = "critical_decay",
            alive = false,
            exploded = true,
        }
    end

    if not item.E or item.E == "" then
        return {
            text = "Przedmiot istnieje, ale jego zawartość jest nieczytelna. Entropia pochłonęła sens.",
            status = "empty",
            alive = true,
        }
    end

    local result = {alive = true, exploded = false}

    if item.T < 10 then
        result.text = "Mokry papier rozpada się w dłoniach. Ledwo dostrzegasz: "
            .. string.sub(item.E, 1, 2) .. "..."
        result.status = "decayed"
    elseif item.T < 40 then
        result.text = "Gazeta jest żółta i krucha: "
            .. string.sub(item.E, 1, math.floor(#item.E / 2)) .. "[NIECZYTELNE]"
        result.status = "degraded"
    elseif item.T < CRITICAL_TEMP then
        local new_temp = math.min(item.T + 20, MAX_TEMP - 1)
        karmazyn.cache.write(atom_id, item.S, item.E, new_temp)
        result.text = "Czytasz wyraźny tekst: " .. item.E
        result.status = "readable"
    else
        result.text = "Tekst drży i rozmazuje się: " .. item.E .. " [NIESTABILNE]"
        result.status = "unstable"
    end

    return result
end

function warp.perform_ritual(target_bubble, ritual_elements)
    if type(ritual_elements) ~= "table" or #ritual_elements == 0 then
        return {
            success = false,
            message = "Rytuał nieważny. Brak elementów — próżnia pochłania zamiar.",
            anomaly_id = nil,
            destination = nil,
        }
    end

    local ritual_key = table.concat(ritual_elements, "_")
    local warp_space = karmazyn.fs.read(target_bubble, ritual_key)

    if not warp_space then
        local anomaly_id = "demon_" .. tostring(math.random(1000, 9999))
        karmazyn.cache.write(anomaly_id, "HOSTILE", "Anomalia z błędnego rzutowania!", MAX_TEMP)

        return {
            success = false,
            message = "Ceremoniał przerwany! Z otwartej szczeliny wylewa się Skażenie.",
            anomaly_id = anomaly_id,
            destination = nil,
        }
    end

    return {
        success = true,
        message = "Ceremoniał udany. Przestrzeń stabilizuje się.",
        anomaly_id = nil,
        destination = warp_space,
    }
end

-- MECHANIKA 3: Rozprzestrzenianie skażenia na sąsiadów
function warp.spread_chaos(neighbor_ids, intensity)
    intensity = intensity or 25
    local contaminated = {}

    for _, nid in ipairs(neighbor_ids) do
        local atom = karmazyn.cache.read(nid)
        if atom and atom.T < MAX_TEMP then
            local new_temp = math.min(atom.T + intensity, MAX_TEMP)
            karmazyn.cache.write(nid, atom.S, atom.E, new_temp)
            contaminated[#contaminated + 1] = {
                id = nid,
                new_temp = new_temp,
                critical = new_temp >= MAX_TEMP,
            }
        end
    end

    return contaminated
end

-- ================================================================
-- WARSTWA 3: Świat gry — grid z sąsiedztwem
-- ================================================================

local World = {}
World.__index = World

function World.new(width, height)
    local self = setmetatable({
        width = width,
        height = height,
        grid = {},              -- [x][y] = atom_id lub nil
        atoms = {},             -- atom_id → {x, y}
        pending_explosions = {},
        tick_count = 0,
        event_log = {},
    }, World)

    for x = 1, width do
        self.grid[x] = {}
    end

    return self
end

function World:place_atom(x, y, atom_id, sig, content, temp)
    self.grid[x][y] = atom_id
    self.atoms[atom_id] = {x = x, y = y}
    karmazyn.cache.write(atom_id, sig, content, temp or 0)
end

function World:get_neighbors(atom_id)
    local pos = self.atoms[atom_id]
    if not pos then return {} end

    local neighbors = {}
    local dirs = {{-1,0},{1,0},{0,-1},{0,1},{-1,-1},{1,-1},{-1,1},{1,1}}

    for _, d in ipairs(dirs) do
        local nx, ny = pos.x + d[1], pos.y + d[2]
        if nx >= 1 and nx <= self.width and ny >= 1 and ny <= self.height then
            local nid = self.grid[nx][ny]
            if nid then
                neighbors[#neighbors + 1] = nid
            end
        end
    end

    return neighbors
end

function World:mark_pending_explosion(atom_id)
    self.pending_explosions[atom_id] = true
end

function World:log_event(event_type, data)
    self.event_log[#self.event_log + 1] = {
        tick = self.tick_count,
        type = event_type,
        data = data,
    }
end

function World:remove_atom(atom_id)
    local pos = self.atoms[atom_id]
    if pos then
        self.grid[pos.x][pos.y] = nil
        self.atoms[atom_id] = nil
    end
    karmazyn.cache.delete(atom_id)
end

-- Render grid z temperaturami:
function World:render()
    local lines = {}
    lines[#lines + 1] = colored(C.DIM, "    " ..
        string.rep("----", self.width) .. "-")

    for y = 1, self.height do
        local row = string.format(" %d |", y)
        for x = 1, self.width do
            local aid = self.grid[x][y]
            if aid then
                local atom = karmazyn.cache.read(aid)
                if atom then
                    local temp = atom.T
                    local ch
                    if temp >= MAX_TEMP then
                        ch = colored(C.RED .. C.BOLD, " XX")
                    elseif temp >= CRITICAL_TEMP then
                        ch = colored(C.RED, string.format("%3d", temp))
                    elseif temp >= 60 then
                        ch = colored(C.YELLOW, string.format("%3d", temp))
                    elseif temp >= 30 then
                        ch = colored(C.GREEN, string.format("%3d", temp))
                    else
                        ch = colored(C.CYAN, string.format("%3d", temp))
                    end
                    row = row .. ch .. "|"
                else
                    row = row .. colored(C.DIM, "  · ") -- removed
                end
            else
                row = row .. colored(C.DIM, "  · ") -- empty
            end
        end
        lines[#lines + 1] = row
    end

    lines[#lines + 1] = colored(C.DIM, "    " ..
        string.rep("----", self.width) .. "-")
    lines[#lines + 1] = colored(C.DIM, "    ")
        .. (function()
            local s = ""
            for x = 1, self.width do
                s = s .. string.format(" %2d ", x)
            end
            return s
        end)()

    return table.concat(lines, "\n")
end

-- ================================================================
-- WARSTWA 4: Agenci — korutyny z zachowaniem
-- ================================================================

local Agent = {}
Agent.__index = Agent

function Agent.new(id, behavior_fn, world)
    local self = setmetatable({
        id = id,
        world = world,
        alive = true,
        ticks = 0,
    }, Agent)

    self.co = coroutine.create(function()
        behavior_fn(self)
    end)

    return self
end

function Agent:tick()
    if not self.alive then return end
    if coroutine.status(self.co) == "dead" then
        self.alive = false
        return
    end

    local ok, err = coroutine.resume(self.co)
    self.ticks = self.ticks + 1

    if not ok then
        self.alive = false
        self.world:log_event("agent_error", {id = self.id, error = err})
    end
end

function Agent:__tostring()
    return string.format("Agent<%s, %s, ticks=%d>",
        self.id, self.alive and "alive" or "dead", self.ticks)
end

-- yield helper:
local function wait() coroutine.yield() end

-- ================================================================
-- WARSTWA 5: Behaviors — logika agentów
-- ================================================================

-- Agent: Entropy Tick — co turę podnosi temperaturę losowych atomów
local function entropy_agent_behavior(self)
    while true do
        local atoms = karmazyn.cache.list()
        if #atoms == 0 then return end

        -- Podgrzej losowy atom o 5-15:
        local target = atoms[math.random(#atoms)]
        if target.T < MAX_TEMP then
            local heat = math.random(5, 15)
            local new_temp = math.min(target.T + heat, MAX_TEMP)
            karmazyn.cache.write(target.id, target.S, target.E, new_temp)
            self.world:log_event("entropy_heat", {
                atom = target.id,
                old_temp = target.T,
                new_temp = new_temp,
                heat = heat,
            })
        end

        wait()
    end
end

-- Agent: Chain Reactor — obsługuje pending explosions
local function chain_reactor_behavior(self)
    while true do
        local exploded_any = false

        for atom_id in pairs(self.world.pending_explosions) do
            self.world.pending_explosions[atom_id] = nil
            exploded_any = true

            local neighbors = self.world:get_neighbors(atom_id)
            local contaminated = warp.spread_chaos(neighbors, 30)

            self.world:log_event("chain_reaction", {
                source = atom_id,
                affected = #contaminated,
            })

            -- Sprawdź czy nowi sąsiedzi są krytyczni:
            for _, c in ipairs(contaminated) do
                if c.critical then
                    self.world:mark_pending_explosion(c.id)
                end
            end

            -- Usuń rozpadnięty atom:
            self.world:remove_atom(atom_id)
            self.world:log_event("atom_removed", {atom = atom_id})
        end

        if not exploded_any then wait() end
    end
end

-- Agent: Reader — co kilka tur czyta losowy atom
local function reader_agent_behavior(self)
    local read_interval = 3
    local reads = 0

    while true do
        for _ = 1, read_interval do wait() end

        local atoms = karmazyn.cache.list()
        if #atoms == 0 then return end

        local target = atoms[math.random(#atoms)]
        local result = warp.read_item(target.id)
        reads = reads + 1

        self.world:log_event("read", {
            atom = target.id,
            status = result.status,
            reads_total = reads,
        })

        if result.exploded then
            self.world:mark_pending_explosion(target.id)
        end
    end
end

-- Agent: Ritualist — co kilka tur próbuje rytuał warp
local function ritualist_behavior(self)
    local rituals = {
        {bubble = "dimension_alpha", elements = {"fire", "water"}},
        {bubble = "dimension_alpha", elements = {"earth", "air"}},
        {bubble = "dimension_beta",  elements = {"void", "light"}},
        {bubble = "dimension_alpha", elements = {"fire", "void"}},     -- ten zadziała
    }

    for _, ritual in ipairs(rituals) do
        for _ = 1, 5 do wait() end    -- czekaj kilka tur

        local result = warp.perform_ritual(ritual.bubble, ritual.elements)

        self.world:log_event("ritual", {
            bubble = ritual.bubble,
            elements = ritual.elements,
            success = result.success,
            anomaly = result.anomaly_id,
            destination = result.destination,
        })

        if result.anomaly_id then
            -- Demon pojawia się na losowym wolnym polu:
            for x = 1, self.world.width do
                for y = 1, self.world.height do
                    if not self.world.grid[x][y] then
                        self.world.grid[x][y] = result.anomaly_id
                        self.world.atoms[result.anomaly_id] = {x = x, y = y}
                        goto placed
                    end
                end
            end
            ::placed::
        end
    end
end

-- ================================================================
-- WARSTWA 6: Symulacja
-- ================================================================

local function run_simulation()
    print(colored(C.MAGENTA .. C.BOLD, "\n╔══════════════════════════════════════╗"))
    print(colored(C.MAGENTA .. C.BOLD, "║  KarmazynOS — Warp Engine Demo      ║"))
    print(colored(C.MAGENTA .. C.BOLD, "║  Termodynamiczna mechanika gry       ║"))
    print(colored(C.MAGENTA .. C.BOLD, "╚══════════════════════════════════════╝\n"))

    -- Przygotuj świat 6x6:
    local world = World.new(6, 6)

    -- Załaduj wymiary do filesystem (poprawny klucz dla warp):
    karmazyn.fs.write("dimension_alpha", "fire_void", "Komnata Płonącej Pustki")

    -- Rozmieść atomy — przedmioty w świecie:
    local items = {
        {x=1, y=1, id="gazeta",     sig="DOC",  text="Dekret Cesarza z roku 40.312",      temp=5},
        {x=2, y=1, id="zwoj",       sig="DOC",  text="Mapa Podziemnych Tuneli",            temp=15},
        {x=3, y=1, id="list",       sig="DOC",  text="Ostatni list z Fortecy Sigma",       temp=35},
        {x=4, y=1, id="kodeks",     sig="RELIC",text="Fragment Kodeksu Maszynowego",       temp=50},
        {x=1, y=2, id="pismo",      sig="DOC",  text="Pismo Protektoratu do Gubernatora",  temp=25},
        {x=2, y=2, id="relikwia",   sig="RELIC",text="Rdzeń Psi-Modulatora",               temp=70},
        {x=3, y=2, id="crystal",    sig="GEM",  text="Kryształ Pamięci Φ",                 temp=40},
        {x=4, y=2, id="amulet",     sig="RELIC",text="Amulet Nawigacyjny Warpa",            temp=60},
        {x=1, y=3, id="moneta",     sig="MISC", text="Moneta z wizerunkiem Omnizjasza",    temp=10},
        {x=2, y=3, id="chip",       sig="TECH", text="Uszkodzony chip neuralny",            temp=80},
        {x=3, y=3, id="mapa",       sig="DOC",  text="Holograficzna mapa sektora 7G",      temp=45},
        {x=4, y=3, id="klucz",      sig="KEY",  text="Klucz do Komory Wieczności",         temp=55},
        {x=5, y=2, id="core",       sig="TECH", text="Aktywny rdzeń plazmowy",              temp=88},
        {x=5, y=3, id="paliwo",     sig="FUEL", text="Kanister paliwa warpowego",           temp=30},
        {x=6, y=1, id="log_stary",  sig="DOC",  text="Dziennik pokładowy — wpis ostatni",  temp=92},
    }

    for _, item in ipairs(items) do
        world:place_atom(item.x, item.y, item.id, item.sig, item.text, item.temp)
    end

    -- Stwórz agentów:
    local agents = {
        Agent.new("entropy",       entropy_agent_behavior,       world),
        Agent.new("chain_reactor", chain_reactor_behavior,       world),
        Agent.new("reader",        reader_agent_behavior,        world),
        Agent.new("ritualist",     ritualist_behavior,           world),
    }

    -- === Pętla symulacji ===

    local MAX_TICKS = 40
    local display_interval = 5

    print(colored(C.BOLD, "Stan początkowy:"))
    print(colored(C.DIM, "(liczby = temperatura atomu, XX = rozpad)\n"))
    print(world:render())
    print()

    for tick = 1, MAX_TICKS do
        world.tick_count = tick

        -- Tick wszystkich agentów:
        for _, agent in ipairs(agents) do
            agent:tick()
        end

        -- Sprawdź krytyczne atomy (T >= MAX_TEMP):
        for id, atom_data in pairs(_cache_store) do
            if atom_data.T >= MAX_TEMP and world.atoms[id] then
                world:mark_pending_explosion(id)
            end
        end

        -- Wyświetl grid co display_interval tur:
        if tick % display_interval == 0 then
            print(colored(C.BOLD, string.format("\n═══ Tura %d ═══", tick)))

            -- Podsumowanie eventów od ostatniego display:
            local recent = {}
            for _, ev in ipairs(world.event_log) do
                if ev.tick > tick - display_interval then
                    recent[#recent + 1] = ev
                end
            end

            if #recent > 0 then
                for _, ev in ipairs(recent) do
                    if ev.type == "entropy_heat" then
                        print(colored(C.YELLOW, string.format(
                            "  ♨ Entropia: %s  T:%d→%d (+%d)",
                            ev.data.atom, ev.data.old_temp, ev.data.new_temp, ev.data.heat)))
                    elseif ev.type == "chain_reaction" then
                        print(colored(C.RED .. C.BOLD, string.format(
                            "  ⚡ Reakcja łańcuchowa z %s → %d sąsiadów skażonych!",
                            ev.data.source, ev.data.affected)))
                    elseif ev.type == "atom_removed" then
                        print(colored(C.RED, string.format(
                            "  ✕ Atom %s — rozpadł się (Vacuum Decay)",
                            ev.data.atom)))
                    elseif ev.type == "read" then
                        print(colored(C.CYAN, string.format(
                            "  📖 Odczyt %s: %s (łącznie %d odczytów)",
                            ev.data.atom, ev.data.status, ev.data.reads_total)))
                    elseif ev.type == "ritual" then
                        if ev.data.success then
                            print(colored(C.GREEN .. C.BOLD, string.format(
                                "  ✦ Rytuał UDANY → %s", ev.data.destination)))
                        else
                            if ev.data.anomaly then
                                print(colored(C.RED .. C.BOLD, string.format(
                                    "  ☠ Rytuał BŁĘDNY → demon %s!", ev.data.anomaly)))
                            else
                                print(colored(C.YELLOW,
                                    "  ✧ Rytuał nieważny — brak efektu"))
                            end
                        end
                    elseif ev.type == "agent_error" then
                        print(colored(C.RED, string.format(
                            "  ⚠ Agent %s error: %s", ev.data.id, ev.data.error)))
                    end
                end
            end

            print()
            print(world:render())

            local alive = karmazyn.cache.count()
            print(colored(C.DIM, string.format(
                "\n  Atomów: %d | Tick: %d/%d | Agentów: %d",
                alive, tick, MAX_TICKS,
                (function()
                    local n = 0
                    for _, a in ipairs(agents) do if a.alive then n = n + 1 end end
                    return n
                end)()
            )))
        end

        -- Koniec jeśli brak atomów:
        if karmazyn.cache.count() == 0 then
            print(colored(C.RED .. C.BOLD, "\n  ████ VACUUM DECAY — wszystkie atomy rozpadły się ████"))
            break
        end
    end

    -- === Raport końcowy ===

    print(colored(C.MAGENTA .. C.BOLD, "\n╔══════════════════════════════════════╗"))
    print(colored(C.MAGENTA .. C.BOLD, "║         RAPORT KOŃCOWY              ║"))
    print(colored(C.MAGENTA .. C.BOLD, "╚══════════════════════════════════════╝\n"))

    -- Statystyki eventów:
    local stats = {}
    for _, ev in ipairs(world.event_log) do
        stats[ev.type] = (stats[ev.type] or 0) + 1
    end

    print(colored(C.BOLD, "Zdarzenia:"))
    local stat_order = {"entropy_heat", "read", "chain_reaction", "atom_removed", "ritual", "agent_error"}
    local stat_labels = {
        entropy_heat = "♨ Podgrzania entropijne",
        read = "📖 Odczyty atomów",
        chain_reaction = "⚡ Reakcje łańcuchowe",
        atom_removed = "✕ Atomy rozpądłe",
        ritual = "✦ Rytuały warp",
        agent_error = "⚠ Błędy agentów",
    }
    for _, key in ipairs(stat_order) do
        if stats[key] then
            print(string.format("  %s: %d", stat_labels[key], stats[key]))
        end
    end

    -- Ocalałe atomy:
    local survivors = karmazyn.cache.list()
    if #survivors > 0 then
        print(colored(C.BOLD, "\nOcalałe atomy:"))
        for _, atom in ipairs(survivors) do
            local temp_color
            if atom.T >= CRITICAL_TEMP then temp_color = C.RED
            elseif atom.T >= 60 then temp_color = C.YELLOW
            else temp_color = C.GREEN end

            print(string.format("  %s [%s] T=%s  \"%s\"",
                atom.id, atom.S,
                colored(temp_color, string.format("%d", atom.T)),
                #atom.E > 40 and string.sub(atom.E, 1, 40) .. "..." or atom.E))
        end
    else
        print(colored(C.RED, "\nBrak ocalałych. Próżnia pochłonęła wszystko."))
    end

    -- Agenci:
    print(colored(C.BOLD, "\nAgenci:"))
    for _, agent in ipairs(agents) do
        print(string.format("  %s: %s, %d ticków",
            agent.id,
            agent.alive and colored(C.GREEN, "żywy") or colored(C.RED, "martwy"),
            agent.ticks))
    end

    print()
end

-- ================================================================
-- WARSTWA 7: Standalone testy mechanik (uruchamiane z --test)
-- ================================================================

local function run_tests()
    print(colored(C.BOLD, "=== Testy mechanik KarmazynOS ===\n"))

    local pass, fail = 0, 0
    local function check(name, cond)
        if cond then
            pass = pass + 1
            print(colored(C.GREEN, "  ✓ " .. name))
        else
            fail = fail + 1
            print(colored(C.RED, "  ✗ " .. name))
        end
    end

    -- Test 1: Cache CRUD
    karmazyn.cache.write("t1", "SIG", "content", 50)
    local a = karmazyn.cache.read("t1")
    check("cache write/read", a and a.S == "SIG" and a.E == "content" and a.T == 50)

    karmazyn.cache.delete("t1")
    check("cache delete", karmazyn.cache.read("t1") == nil)

    -- Test 2: read_item — decay stages
    karmazyn.cache.write("cold", "DOC", "Pełny tekst dokumentu", 5)
    local r = warp.read_item("cold")
    check("read cold (T=5): partial", r.status == "decayed")

    karmazyn.cache.write("warm", "DOC", "Ciepły tekst", 35)
    r = warp.read_item("warm")
    check("read warm (T=35): degraded", r.status == "degraded")

    karmazyn.cache.write("hot", "DOC", "Gorący tekst", 50)
    r = warp.read_item("hot")
    check("read hot (T=50): readable + temp rises", r.status == "readable")
    local after = karmazyn.cache.read("hot")
    check("read hot: temp increased", after.T == 70)

    karmazyn.cache.write("unstable", "DOC", "Niestabilny", 92)
    r = warp.read_item("unstable")
    check("read unstable (T=92): unstable", r.status == "unstable")

    karmazyn.cache.write("dead", "DOC", "Martwy", 100)
    r = warp.read_item("dead")
    check("read critical (T=100): exploded", r.exploded == true)

    r = warp.read_item("nonexistent")
    check("read nonexistent: vacuum", r.status == "vacuum")

    -- Test 3: Rytuał — poprawny klucz
    karmazyn.fs.write("dim_a", "fire_water", "Sanktuarium Pary")
    local rr = warp.perform_ritual("dim_a", {"fire", "water"})
    check("ritual correct key: success", rr.success == true)
    check("ritual correct: destination", rr.destination == "Sanktuarium Pary")

    -- Test 4: Rytuał — błędny klucz (demon)
    rr = warp.perform_ritual("dim_a", {"wrong", "key"})
    check("ritual wrong key: fail", rr.success == false)
    check("ritual wrong: anomaly spawned", rr.anomaly_id ~= nil)
    local demon = karmazyn.cache.read(rr.anomaly_id)
    check("demon exists in cache", demon ~= nil)
    check("demon is hostile", demon and demon.S == "HOSTILE")
    check("demon is critical (T=100)", demon and demon.T == MAX_TEMP)

    -- Test 5: Rytuał — brak elementów
    rr = warp.perform_ritual("dim_a", {})
    check("ritual empty elements: fail", rr.success == false)
    check("ritual empty: no anomaly", rr.anomaly_id == nil)

    -- Test 6: spread_chaos
    karmazyn.cache.write("n1", "X", "a", 50)
    karmazyn.cache.write("n2", "X", "b", 85)
    local cc = warp.spread_chaos({"n1", "n2"}, 20)
    check("spread_chaos: 2 affected", #cc == 2)
    local n1 = karmazyn.cache.read("n1")
    check("n1 temp increased", n1 and n1.T == 70)
    local n2 = karmazyn.cache.read("n2")
    check("n2 clamped to MAX", n2 and n2.T == MAX_TEMP)
    check("n2 is critical", cc[2] and cc[2].critical == true)

    -- Test 7: World neighbors
    _cache_store = {}    -- reset
    local w = World.new(3, 3)
    w:place_atom(2, 2, "center", "C", "x", 10)
    w:place_atom(1, 1, "corner", "C", "y", 20)
    w:place_atom(3, 2, "right",  "C", "z", 30)
    local nbrs = w:get_neighbors("center")
    check("world neighbors: 2 found", #nbrs == 2)

    -- Cleanup:
    _cache_store = {}

    print(string.format("\n%s: %d passed, %d failed",
        fail == 0 and colored(C.GREEN .. C.BOLD, "ALL PASS")
                   or colored(C.RED .. C.BOLD, "FAILURES"),
        pass, fail))
end

-- ================================================================
-- MAIN
-- ================================================================

if arg and arg[1] == "--test" then
    run_tests()
else
    run_simulation()
end
```

---

## Jak to działa — przewodnik dla programistów

### Architektura termodynamiczna

Każdy atom w KarmazynOS ma **temperaturę** (`T`). Temperatura to nie ciepło fizyczne — to miara **uwagi i użycia**:

| T | Znaczenie | Efekt odczytu |
|---|---|---|
| 0-9 | Zimny, zapomniany, mokry | Ledwo czytelny (2 znaki) |
| 10-39 | Degradujący | Częściowo czytelne |
| 40-89 | Aktywny, ciepły | Pełen odczyt, T rośnie o 20 |
| 90-99 | Niestabilny | Odczyt bez podgrzania, ostrzeżenie |
| 100 | Punkt krytyczny | **Rozpad** — atom exploduje |

**Paradoks:** czytanie atomu **podgrzewa** go (T += 20). Im częściej czytasz, tym bliżej rozpadu. Zapomniane atomy powoli degradują (entropia). Nie da się "zachować" informacji bez ryzyka.

### Rój agentów

Czterech agentów działa równolegle (korutyny z M6):

| Agent | Rola | Zachowanie |
|---|---|---|
| `entropy` | Entropijne podgrzewanie | Co turę losowy atom +5-15°T |
| `reader` | Odczyt informacji | Co 3 tury czyta losowy atom |
| `chain_reactor` | Reakcje łańcuchowe | Gdy atom exploduje → skaża sąsiadów |
| `ritualist` | Rytuały warp | Co 5 tur próbuje otworzyć wymiar |

Agenci nie wiedzą o sobie — komunikują się **pośrednio** przez stan świata (cache). Entropy podgrzewa atom → reader go czyta (jeszcze cieplej) → punkt krytyczny → chain_reactor propaguje skażenie na sąsiadów → ci też mogą explodować → kaskada.

### Rytuał Warp

Gracz składa rytuał z elementów (np. `{"fire", "water"}`). Silnik buduje klucz (`"fire_water"`) i szuka w filesystem bąbla. Jeśli klucz pasuje — teleport. Jeśli nie — **demon** rodzi się z T=100 (już krytyczny!). Pierwszy odczyt demona = natychmiastowy rozpad = reakcja łańcuchowa.

### Uruchomienie

```bash
# Symulacja:
lua5.4 karmazyn_demo.lua

# Testy mechanik:
lua5.4 karmazyn_demo.lua --test
```

### Rozszerzenia do eksploracji

1. **Healing agent** — agent który schładza gorące atomy (T -= 10). Walka entropii z porządkiem.
2. **Warp traveler** — agent który po udanym rytuale "przenosi" atomy do nowego gridu.
3. **Memory persistence** — zapis stanu do `.soul` JSONL po każdej turze.
4. **Interactive mode** — gracz wybiera akcję (read/ritual/wait) zamiast automatycznych agentów.
5. **HSS Φ-space** — temperatura jako phi, decay jako `exp(-dt)`, threshold rules z M11.4.
6. **Sandbox** — uruchom agentów w sandboxie z M10 (CPU/mem quota per agent).

---

## Mapowanie na kurs

| Element demo | Moduł kursu |
|---|---|
| Tabele `_cache_store`, `_fs_store` | M2 (tabele jako hash mapy) |
| `World` klasa z metatable | M4 (OOP prototypowy) |
| `warp.read_item` error handling | M5 (pcall, structured results) |
| Agenci na korutynach | M6 (coroutine.create/resume/yield) |
| `karmazyn` jako moduł | M7 (module pattern, namespace) |
| Grid render z `luaL_Buffer` pattern | M8 (string building) |
| W produkcji: Atom jako userdata | M9 (lua_newuserdata, __gc) |
| W produkcji: sandbox per agent | M10 (_ENV, hooks, allocator) |
| Atom rules, threshold checks | M11 (DSL, deklaratywne reguły) |
| Pełna integracja | M12 (capstone) |
