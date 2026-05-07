local id = karmazyn.read_line("ID Atomu do edycji: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if not atom then
    print("✗ Atom " .. id .. " nie istnieje.")
    return
end

print("Edycja atomu: " .. atom.id)
print("Aktualna Emanacja (E): " .. atom.E)

local new_e = karmazyn.read_line("Nowa Emanacja: ")
if new_e ~= "" then
    atom.set_E(new_e)
    print("✓ Emanacja zaktualizowana.")
else
    print("Anulowano.")
end
