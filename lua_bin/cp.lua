local src = karmazyn.read_line("ID Źródłowe: ")
if src == "" then return end

local dst = karmazyn.read_line("ID Docelowe: ")
if dst == "" then return end

local res = karmazyn.clone_atom(src, dst)
if type(res) == "table" then
    print("✓ Skopiowano: " .. src .. " → " .. res.id)
else
    print("✗ Błąd kopiowania: " .. tostring(res))
end
