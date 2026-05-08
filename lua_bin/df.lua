local temp = karmazyn.get_temperature()
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
