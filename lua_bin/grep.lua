local pattern = karmazyn.read_line("Wzór do wyszukania: ")
if pattern == "" then return end

local atoms = karmazyn.list_atoms()
local results = {}
local count = 0

for i = 1, #atoms do
    local a = atoms[i]
    if string.find(string.lower(a.S), string.lower(pattern)) or
       string.find(string.lower(a.E), string.lower(pattern)) then
        count = count + 1
        table.insert(results, string.format("[%s] S: %s | E: %s", a.id, a.S, a.E))
    end
end

if count > 0 then
    print(karmazyn.ui.draw_frame("GREP: " .. pattern, results, "phi_thermal"))
    print("Znaleziono " .. count .. " dopasowań.")
else
    print("Brak dopasowań dla: " .. pattern)
end
