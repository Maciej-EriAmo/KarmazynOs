local atoms = karmazyn.list_atoms()
local usage = {}

for i = 1, #atoms do
    local e = atoms[i].E
    usage[e] = (usage[e] or 0) + 1
end

local lines = {}
for e, count in pairs(usage) do
    table.insert(lines, string.format("%-20s: %d", e, count))
end
table.sort(lines)

if #lines == 0 then
    print("Brak danych o zajętości emanacji.")
else
    print(karmazyn.ui.draw_frame("EMANATION USAGE (du)", lines, "phi_signal"))
end
