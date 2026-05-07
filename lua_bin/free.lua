local res = karmazyn.get_resources()
local lines = {
    "Zasoby systemowe:",
    "-------------------"
}

for k, v in pairs(res) do
    table.insert(lines, string.format("%-10s: %d", k, v))
end

local atoms = karmazyn.list_atoms()
table.insert(lines, "-------------------")
table.insert(lines, "Aktywne atomy Φ: " .. #atoms)

print(karmazyn.ui.draw_frame("RESOURCES (free)", lines, "phi_core"))
