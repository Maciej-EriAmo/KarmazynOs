local id = karmazyn.read_line("ID Atomu: ")
if id == "" then return end

local s = karmazyn.read_line("Sygnatura (S): ")
local e = karmazyn.read_line("Emanacja (E): ")

local atom = karmazyn.create_atom(id, s, e, 0.8)
if type(atom) == "table" then
    print("✓ Stworzono atom: " .. atom.id)
else
    print("✗ Błąd: " .. tostring(atom))
end
