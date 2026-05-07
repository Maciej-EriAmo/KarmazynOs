local id = karmazyn.read_line("ID Atomu do konsolidacji: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if not atom then
    print("✗ Atom " .. id .. " nie istnieje.")
    return
end

print("Konsolidacja atomu: " .. atom.id)
local res = karmazyn.consolidate(atom.id)

if string.find(res, "^bubble_") then
    print("✓ Pomyślnie skonsolidowano do bąbla: " .. res)
else
    print("✗ Błąd konsolidacji: " .. res)
end
