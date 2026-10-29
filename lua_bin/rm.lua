local id = karmazyn.read_line("ID Atomu do usunięcia: ") or ""
if id == "" then return end

local ok = karmazyn.delete_atom(id)
if ok then
    print("✓ Atom " .. id .. " usunięty.")
else
    print("✗ Nie udało się usunąć atomu " .. id .. " (może nie istnieje?)")
end
