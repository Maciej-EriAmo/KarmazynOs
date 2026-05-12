

#!/usr/bin/env lua5.4
-- karmazyn_demo.lua -- KarmazynOS Warp Engine Demo — thermodynamic mechanics + multi-agent swarm -- Run: lua5.4 karmazyn_demo.lua

math.randomseed(os.time())

-- ================================================================
-- LAYER 0: Terminal colors (optional, degrade gracefully)
-- ================================================================

local C = {
    RESET = "\27[0m", RED = "\27[31m", GREEN = "\27[32m",
    YELLOW = "\27[33m", BLUE = "\27[34m", MAGENTA= "\27[35m",
    CYAN = "\27[36m", DIM = "\27[2m", BOLD = "\27[1m",
}

local function colored(color, text)
    return color .. text .. C.RESET
end

-- ================================================================
-- LAYER 1: KarmazynOS Core — cache + filesystem mock
-- ================================================================

karmazyn = {}

-- Cache: fast bubble working memory (RAM atoms)
karmazyn.cache = {}
local _cache_store = {}

function karmazyn.cache.write(id, sig, content, temp)
    _cache_store[id] = {
        id = id,
        S = sig,      -- signature (atom type)
        E = content,  -- emanation (informational entropy)
        T = temp or 0 -- temperature (0 = cold/fresh, 100 = decay)
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
    for _ in pairs(_cache_store) do
        n = n + 1
    end
    return n
end

-- Filesystem: persistent bubble memory
karmazyn.fs = {}
local _fs_store = {}

function karmazyn.fs.write(bubble, key, data)
    if not _fs_store[bubble] then
        _fs_store[bubble] = {}
    end
    _fs_store[bubble][key] = data
end

function karmazyn.fs.read(bubble, key)
    if not _fs_store[bubble] then return nil end
    return _fs_store[bubble][key]
end

-- ================================================================
-- LAYER 2: Warp Engine — transitions and entropy engine
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
        return { text = "The artifact has decayed utterly. It has been reclaimed by the Void.", status = "vacuum", alive = false, }
    end 
    
    if is_critical(item) then 
        return { text = "The artifact has reached critical mass. It disintegrates in your hands.", status = "critical_decay", alive = false, exploded = true, }
    end 
    
    if not item.E or item.E == "" then 
        return { text = "The artifact exists, but its data-vaults are corrupted. Entropy has devoured its meaning.", status = "empty", alive = true, }
    end 
    
    local result = {alive = true, exploded = false} 
    
    if item.T < 10 then 
        result.text = "The damp parchment crumbles in your hands. You barely register: " .. string.sub(item.E, 1, 2) .. "..." 
        result.status = "decayed"
    elseif item.T < 40 then 
        result.text = "The paper is yellowed and brittle: " .. string.sub(item.E, 1, math.floor(#item.E / 2)) .. "[UNINTELLIGIBLE]" 
        result.status = "degraded"
    elseif item.T < CRITICAL_TEMP then 
        local new_temp = math.min(item.T + 20, MAX_TEMP - 1) 
        karmazyn.cache.write(atom_id, item.S, item.E, new_temp) 
        result.text = "You read the clear data-slate: " .. item.E 
        result.status = "readable"
    else 
        result.text = "The glyphs tremble and blur: " .. item.E .. " [UNSTABLE DATA]" 
        result.status = "unstable"
    end 
    
    return result 
end

function warp.perform_ritual(target_bubble, ritual_elements)
    if type(ritual_elements) ~= "table" or #ritual_elements == 0 then
        return { success = false, message = "Ritual nullified. Insufficient elements — the void consumes your intent.", anomaly_id = nil, destination = nil, }
    end

    local ritual_key = table.concat(ritual_elements, "_")
    local warp_space = karmazyn.fs.read(target_bubble, ritual_key) 
    
    if not warp_space then 
        local anomaly_id = "demon_" .. tostring(math.random(1000, 9999)) 
        karmazyn.cache.write(anomaly_id, "HOSTILE", "Anomaly spawned from erroneous projection!", MAX_TEMP) 
        return { success = false, message = "Ritual aborted! Corruption bleeds from the open rift.", anomaly_id = anomaly_id, destination = nil, }
    end 
    
    return { success = true, message = "Ritual successful. The spatial geometry stabilizes.", anomaly_id = nil, destination = warp_space,} 
end

-- MECHANIC 3: Spread chaos to neighbors
function warp.spread_chaos(neighbor_ids, intensity)
    intensity = intensity or 25
    local contaminated = {}

    for _, nid in ipairs(neighbor_ids) do 
        local atom = karmazyn.cache.read(nid) 
        if atom and atom.T < MAX_TEMP then 
            local new_temp = math.min(atom.T + intensity, MAX_TEMP) 
            karmazyn.cache.write(nid, atom.S, atom.E, new_temp) 
            contaminated[#contaminated + 1] = { id = nid, new_temp = new_temp, critical = new_temp >= MAX_TEMP, } 
        end
    end 
    return contaminated 
end

-- ================================================================
-- LAYER 3: Game World — grid with adjacency
-- ================================================================

local World = {}
World.__index = World

function World.new(width, height)
    local self = setmetatable({
        width = width,
        height = height,
        grid = {}, -- [x][y] = atom_id or nil
        atoms = {}, -- atom_id → {x, y}
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

-- Render grid with temperatures:
function World:render()
    local lines = {}
    lines[#lines + 1] = colored(C.DIM, " " .. string.rep("----", self.width) .. "-")

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
                    row = row .. colored(C.DIM, " · ") -- removed 
                end 
            else 
                row = row .. colored(C.DIM, " · ") -- empty 
            end 
        end 
        lines[#lines + 1] = row
    end 
    
    lines[#lines + 1] = colored(C.DIM, " " .. string.rep("----", self.width) .. "-")
    lines[#lines + 1] = colored(C.DIM, " ") .. (function() 
        local s = "" 
        for x = 1, self.width do 
            s = s .. string.format(" %2d ", x) 
        end 
        return s 
    end)() 
    
    return table.concat(lines, "\n") 
end

-- ================================================================
-- LAYER 4: Agents — coroutines with behavior
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

    self.co = coroutine.create(function() behavior_fn(self) end) 
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
    return string.format("Agent<%s, %s, ticks=%d>", self.id, self.alive and "alive" or "dead", self.ticks)
end

-- yield helper:
local function wait()
    coroutine.yield()
end

-- ================================================================
-- LAYER 5: Behaviors — agent logic
-- ================================================================

-- Agent: Entropy Tick — raises the temperature of random atoms every turn
local function entropy_agent_behavior(self)
    while true do
        local atoms = karmazyn.cache.list()
        if #atoms == 0 then return end

        -- Heat a random atom by 5-15: 
        local target = atoms[math.random(#atoms)] 
        if target.T < MAX_TEMP then 
            local heat = math.random(5, 15) 
            local new_temp = math.min(target.T + heat, MAX_TEMP) 
            karmazyn.cache.write(target.id, target.S, target.E, new_temp) 
            self.world:log_event("entropy_heat", { atom = target.id, old_temp = target.T, new_temp = new_temp, heat = heat, }) 
        end 
        wait()
    end 
end

-- Agent: Chain Reactor — handles pending explosions
local function chain_reactor_behavior(self)
    while true do
        local exploded_any = false

        for atom_id in pairs(self.world.pending_explosions) do 
            self.world.pending_explosions[atom_id] = nil 
            exploded_any = true 
            local neighbors = self.world:get_neighbors(atom_id) 
            local contaminated = warp.spread_chaos(neighbors, 30) 
            self.world:log_event("chain_reaction", { source = atom_id, affected = #contaminated, }) 
            
            -- Check if new neighbors are critical: 
            for _, c in ipairs(contaminated) do 
                if c.critical then 
                    self.world:mark_pending_explosion(c.id) 
                end 
            end 
            
            -- Remove the decayed atom: 
            self.world:remove_atom(atom_id) 
            self.world:log_event("atom_removed", {atom = atom_id}) 
        end 
        
        if not exploded_any then wait() end
    end 
end

-- Agent: Reader — reads a random atom every few turns
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
        self.world:log_event("read", { atom = target.id, status = result.status, reads_total = reads, }) 
        
        if result.exploded then 
            self.world:mark_pending_explosion(target.id) 
        end
    end 
end

-- Agent: Ritualist — attempts a warp ritual every few turns
local function ritualist_behavior(self)
    local rituals = {
        {bubble = "dimension_alpha", elements = {"fire", "water"}},
        {bubble = "dimension_alpha", elements = {"earth", "air"}},
        {bubble = "dimension_beta", elements = {"void", "light"}},
        {bubble = "dimension_alpha", elements = {"fire", "void"}}, -- this one will succeed
    }

    for _, ritual in ipairs(rituals) do 
        for _ = 1, 5 do wait() end -- wait a few turns 
        local result = warp.perform_ritual(ritual.bubble, ritual.elements) 
        self.world:log_event("ritual", { bubble = ritual.bubble, elements = ritual.elements, success = result.success, anomaly = result.anomaly_id, destination = result.destination, }) 
        
        if result.anomaly_id then 
            -- Demon appears on a random empty tile: 
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
-- LAYER 6: Simulation
-- ================================================================

local function run_simulation()

    print(colored(C.MAGENTA .. C.BOLD, "\n╔════════════════════════════════════╗"))
    print(colored(C.MAGENTA .. C.BOLD, " ║ KarmazynOS — Warp Engine Demo      ║"))
    print(colored(C.MAGENTA .. C.BOLD, " ║ Thermodynamic Game Mechanics       ║"))
    print(colored(C.MAGENTA .. C.BOLD, " ╚════════════════════════════════════╝\n")) 
    
    -- Prepare 6x6 world:
    local world = World.new(6, 6) 
    
    -- Load dimensions into filesystem (correct key for warp):
    karmazyn.fs.write("dimension_alpha", "fire_void", "Chamber of the Burning Void") 
    
    -- Place atoms — items in the world:
    local items = { 
        {x=1, y=1, id="gazeta", sig="DOC", text="Emperor's Decree from year 40.312", temp=5}, 
        {x=2, y=1, id="zwoj", sig="DOC", text="Map of the Underground Tunnels", temp=15}, 
        {x=3, y=1, id="list", sig="DOC", text="Last letter from Sigma Fortress", temp=35}, 
        {x=4, y=1, id="kodeks", sig="RELIC",text="Fragment of the Machine Codex", temp=50}, 
        {x=1, y=2, id="pismo", sig="DOC", text="Protectorate's Missive to the Governor", temp=25}, 
        {x=2, y=2, id="relikwia", sig="RELIC",text="Psi-Modulator Core", temp=70}, 
        {x=3, y=2, id="crystal", sig="GEM", text="Memory Crystal Φ", temp=40}, 
        {x=4, y=2, id="amulet", sig="RELIC",text="Warp Navigational Amulet", temp=60}, 
        {x=1, y=3, id="moneta", sig="MISC", text="Coin with the image of the Omnissiah", temp=10}, 
        {x=2, y=3, id="chip", sig="TECH", text="Damaged neural chip", temp=80}, 
        {x=3, y=3, id="mapa", sig="DOC", text="Holographic map of sector 7G", temp=45}, 
        {x=4, y=3, id="klucz", sig="KEY", text="Key to the Eternity Chamber", temp=55}, 
        {x=5, y=2, id="core", sig="TECH", text="Active plasma core", temp=88}, 
        {x=5, y=3, id="paliwo", sig="FUEL", text="Warp fuel canister", temp=30}, 
        {x=6, y=1, id="log_stary", sig="DOC", text="Ship's log — final entry", temp=92},
    } 
    
    for _, item in ipairs(items) do 
        world:place_atom(item.x, item.y, item.id, item.sig, item.text, item.temp)
    end 
    
    -- Create agents:
    local agents = { 
        Agent.new("entropy", entropy_agent_behavior, world), 
        Agent.new("chain_reactor", chain_reactor_behavior, world), 
        Agent.new("reader", reader_agent_behavior, world), 
        Agent.new("ritualist", ritualist_behavior, world),
    } 
    
    -- === Simulation Loop === 
    local MAX_TICKS = 40
    local display_interval = 5 
    
    print(colored(C.BOLD, "Initial State:"))
    print(colored(C.DIM, "(numbers = atom temperature, XX = decay)\n"))
    print(world:render())
    print() 
    
    for tick = 1, MAX_TICKS do 
        world.tick_count = tick 
        
        -- Tick all agents: 
        for _, agent in ipairs(agents) do 
            agent:tick() 
        end 
        
        -- Check critical atoms (T >= MAX_TEMP): 
        for id, atom_data in pairs(_cache_store) do 
            if atom_data.T >= MAX_TEMP and world.atoms[id] then 
                world:mark_pending_explosion(id) 
            end 
        end 
        
        -- Display grid every display_interval turns: 
        if tick % display_interval == 0 then 
            print(colored(C.BOLD, string.format("\n═══ Turn %d ═══", tick))) 
            
            -- Summary of events since last display: 
            local recent = {} 
            for _, ev in ipairs(world.event_log) do 
                if ev.tick > tick - display_interval then 
                    recent[#recent + 1] = ev 
                end 
            end 
            
            if #recent > 0 then 
                for _, ev in ipairs(recent) do 
                    if ev.type == "entropy_heat" then 
                        print(colored(C.YELLOW, string.format(" ♨ Entropy: %s T:%d→%d (+%d)", ev.data.atom, ev.data.old_temp, ev.data.new_temp, ev.data.heat))) 
                    elseif ev.type == "chain_reaction" then 
                        print(colored(C.RED .. C.BOLD, string.format(" ⚡ Chain reaction from %s → %d neighbors corrupted!", ev.data.source, ev.data.affected))) 
                    elseif ev.type == "atom_removed" then 
                        print(colored(C.RED, string.format(" ✕ Atom %s — decayed (Vacuum Decay)", ev.data.atom))) 
                    elseif ev.type == "read" then 
                        print(colored(C.CYAN, string.format(" 📖 Read %s: %s (total %d reads)", ev.data.atom, ev.data.status, ev.data.reads_total))) 
                    elseif ev.type == "ritual" then 
                        if ev.data.success then 
                            print(colored(C.GREEN .. C.BOLD, string.format(" ✦ Ritual SUCCESSFUL → %s", ev.data.destination))) 
                        else 
                            if ev.data.anomaly then 
                                print(colored(C.RED .. C.BOLD, string.format(" ☠ Ritual FAILED → demon %s!", ev.data.anomaly))) 
                            else 
                                print(colored(C.YELLOW, " ✧ Ritual invalid — no effect")) 
                            end 
                        end 
                    elseif ev.type == "agent_error" then 
                        print(colored(C.RED, string.format(" ⚠ Agent %s error: %s", ev.data.id, ev.data.error))) 
                    end 
                end 
            end 
            
            print() 
            print(world:render()) 
            
            local alive = karmazyn.cache.count() 
            print(colored(C.DIM, string.format("\n Atoms: %d | Tick: %d/%d | Agents: %d", alive, tick, MAX_TICKS, 
            (function() 
                local n = 0 
                for _, a in ipairs(agents) do 
                    if a.alive then n = n + 1 end 
                end 
                return n 
            end)() ))) 
        end 
        
        -- End if no atoms remain: 
        if karmazyn.cache.count() == 0 then 
            print(colored(C.RED .. C.BOLD, "\n ████ VACUUM DECAY — all atoms have decayed ████")) 
            break 
        end
    end 
    
    -- === Final Report === 
    print(colored(C.MAGENTA .. C.BOLD, "\n╔══════════════════════════════════════╗"))
    print(colored(C.MAGENTA .. C.BOLD, " ║ FINAL REPORT                         ║"))
    print(colored(C.MAGENTA .. C.BOLD, " ╚══════════════════════════════════════╝\n")) 
    
    -- Event statistics:
    local stats = {}
    for _, ev in ipairs(world.event_log) do 
        stats[ev.type] = (stats[ev.type] or 0) + 1
    end 
    
    print(colored(C.BOLD, "Events:"))
    local stat_order = {"entropy_heat", "read", "chain_reaction", "atom_removed", "ritual", "agent_error"}
    local stat_labels = { 
        entropy_heat = "♨ Entropy heatings", 
        read = "📖 Atom reads", 
        chain_reaction = "⚡ Chain reactions", 
        atom_removed = "✕ Decayed atoms", 
        ritual = "✦ Warp rituals", 
        agent_error = "⚠ Agent errors",
    }
    
    for _, key in ipairs(stat_order) do 
        if stats[key] then 
            print(string.format(" %s: %d", stat_labels[key], stats[key])) 
        end
    end 
    
    -- Surviving atoms:
    local survivors = karmazyn.cache.list()
    if #survivors > 0 then 
        print(colored(C.BOLD, "\nSurviving atoms:")) 
        for _, atom in ipairs(survivors) do 
            local temp_color 
            if atom.T >= CRITICAL_TEMP then 
                temp_color = C.RED 
            elseif atom.T >= 60 then 
                temp_color = C.YELLOW 
            else 
                temp_color = C.GREEN 
            end 
            print(string.format(" %s [%s] T=%s \"%s\"", atom.id, atom.S, colored(temp_color, string.format("%d", atom.T)), #atom.E > 40 and string.sub(atom.E, 1, 40) .. "..." or atom.E)) 
        end
    else 
        print(colored(C.RED, "\nNo survivors. The void consumed everything."))
    end 
    
    -- Agents:
    print(colored(C.BOLD, "\nAgents:"))
    for _, agent in ipairs(agents) do 
        print(string.format(" %s: %s, %d ticks", agent.id, agent.alive and colored(C.GREEN, "alive") or colored(C.RED, "dead"), agent.ticks))
    end 
    print() 
end

-- ================================================================
-- LAYER 7: Standalone mechanics tests (run with --test)
-- ================================================================

local function run_tests() 
    print(colored(C.BOLD, "=== KarmazynOS Mechanics Tests ===\n"))

    local pass, fail = 0, 0
    local function check(name, cond) 
        if cond then 
            pass = pass + 1 
            print(colored(C.GREEN, " ✓ " .. name)) 
        else 
            fail = fail + 1 
            print(colored(C.RED, " ✗ " .. name)) 
        end
    end 
    
    -- Test 1: Cache CRUD
    karmazyn.cache.write("t1", "SIG", "content", 50)
    local a = karmazyn.cache.read("t1")
    check("cache write/read", a and a.S == "SIG" and a.E == "content" and a.T == 50) 
    karmazyn.cache.delete("t1")
    check("cache delete", karmazyn.cache.read("t1") == nil) 
    
    -- Test 2: read_item — decay stages
    karmazyn.cache.write("cold", "DOC", "Full text of the document", 5)
    local r = warp.read_item("cold")
    check("read cold (T=5): partial", r.status == "decayed") 
    
    karmazyn.cache.write("warm", "DOC", "Warm text", 35)
    r = warp.read_item("warm")
    check("read warm (T=35): degraded", r.status == "degraded") 
    
    karmazyn.cache.write("hot", "DOC", "Hot text", 50)
    r = warp.read_item("hot")
    check("read hot (T=50): readable + temp rises", r.status == "readable")
    local after = karmazyn.cache.read("hot")
    check("read hot: temp increased", after.T == 70) 
    
    karmazyn.cache.write("unstable", "DOC", "Unstable", 92)
    r = warp.read_item("unstable")
    check("read unstable (T=92): unstable", r.status == "unstable") 
    
    karmazyn.cache.write("dead", "DOC", "Dead", 100)
    r = warp.read_item("dead")
    check("read critical (T=100): exploded", r.exploded == true) 
    
    r = warp.read_item("nonexistent")
    check("read nonexistent: vacuum", r.status == "vacuum") 
    
    -- Test 3: Ritual — correct key
    karmazyn.fs.write("dim_a", "fire_water", "Steam Sanctuary")
    local rr = warp.perform_ritual("dim_a", {"fire", "water"})
    check("ritual correct key: success", rr.success == true)
    check("ritual correct: destination", rr.destination == "Steam Sanctuary") 
    
    -- Test 4: Ritual — wrong key (demon)
    rr = warp.perform_ritual("dim_a", {"wrong", "key"})
    check("ritual wrong key: fail", rr.success == false)
    check("ritual wrong: anomaly spawned", rr.anomaly_id ~= nil)
    local demon = karmazyn.cache.read(rr.anomaly_id)
    check("demon exists in cache", demon ~= nil)
    check("demon is hostile", demon and demon.S == "HOSTILE")
    check("demon is critical (T=100)", demon and demon.T == MAX_TEMP) 
    
    -- Test 5: Ritual — no elements
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
    _cache_store = {} -- reset
    local w = World.new(3, 3)
    w:place_atom(2, 2, "center", "C", "x", 10)
    w:place_atom(1, 1, "corner", "C", "y", 20)
    w:place_atom(3, 2, "right", "C", "z", 30)
    local nbrs = w:get_neighbors("center")
    check("world neighbors: 2 found", #nbrs == 2) 
    
    -- Cleanup:
    _cache_store = {} 
    print(string.format("\n%s: %d passed, %d failed", fail == 0 and colored(C.GREEN .. C.BOLD, "ALL PASS") or colored(C.RED .. C.BOLD, "FAILURES"), pass, fail)) 
end

-- ================================================================
-- MAIN
-- ================================================================

if arg and arg[1] == "--test" then 
    run_tests() 
else 
    run_simulation() 
end
