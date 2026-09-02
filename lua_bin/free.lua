-- Zasoby — liczniki powierzchni Φ (nie całego heapu silnika / native u32)
local function count(state)
    return #karmazyn.list_atoms(state)
end

local n_hot = count("HOT")
local n_warm = count("WARM")
local n_cold = count("COLD")
local n_tomb = count("TOMB")
local n_phi = #karmazyn.list_atoms()

local lines = {
    "Powierzchnia Φ (lua_bin):",
    "-------------------",
    "Φ razem   : " .. tostring(n_phi),
    "HOT       : " .. tostring(n_hot),
    "WARM      : " .. tostring(n_warm),
    "COLD      : " .. tostring(n_cold),
    "TOMB      : " .. tostring(n_tomb),
}

-- opcjonalnie surowy store.stats (debug)
local res = karmazyn.get_resources()
if res then
    table.insert(lines, "-------------------")
    table.insert(lines, "Store.total : " .. tostring(res.total or res.alive or "?"))
    if res.lorentz_bridge then
        table.insert(lines, "Lorentz     : on")
    end
    if res.mrc then
        table.insert(lines, "MRC         : on")
    end
end

print(karmazyn.ui.draw_frame("RESOURCES (free)", lines, "phi_core"))
