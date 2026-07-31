local id = karmazyn.read_line("ID Atomu: ")
if id == "" then return end

local s = karmazyn.read_line("Sygnatura (S): ")
local e = karmazyn.read_line("Emanacja (E): ")

-- T_INIT ze skali jądra (nie ułamek 0..1)
local atom = karmazyn.create_atom(id, s, e, karmazyn.T_INIT)
if type(atom) == "table" then
    print("✓ Stworzono atom: " .. atom.id)
else
    print("✗ Błąd: " .. tostring(atom))
end
