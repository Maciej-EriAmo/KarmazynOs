local atoms = karmazyn.list_atoms()
local temp = 0
if #atoms > 0 then
    local sum = 0
    for i = 1, #atoms do
        local a = atoms[i]
        sum = sum + (a.get_T_frac and a.get_T_frac() or 0)
    end
    temp = sum / #atoms
end
local status = "STABILNY"
if temp > 0.7 then status = "KRYTYCZNY" elseif temp < 0.3 then status = "ZAMARZAJĄCY" end

local stats = {
    "Temperatura Systemu: " .. string.format("%.2f", temp),
    "Status: " .. status,
    "-------------------",
    "Atomy w HOT:  " .. #karmazyn.list_atoms("HOT"),
    "Atomy w WARM: " .. #karmazyn.list_atoms("WARM"),
    "Atomy w COLD: " .. #karmazyn.list_atoms("COLD"),
    "Atomy w TOMB: " .. #karmazyn.list_atoms("TOMB")
}

print(karmazyn.ui.draw_frame("SYSTEM STATISTICS (df)", stats, "phi_core"))
