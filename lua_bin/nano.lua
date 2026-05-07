local id = karmazyn.read_line("nano - ID Atomu: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if not atom then
    print("✗ Atom " .. id .. " nie istnieje.")
    return
end

print("Edycja Emanacji (E) dla " .. atom.id)
print("Wpisz nową treść. Wpisz '.save' w nowej linii aby zapisać, '.abort' aby anulować.")

local lines = {}
while true do
    local line = karmazyn.read_line("> ")
    if line == ".save" then
        atom.set_E(table.concat(lines, "\n"))
        print("✓ Zapisano.")
        break
    elseif line == ".abort" then
        print("Anulowano.")
        break
    else
        table.insert(lines, line)
    end
end
