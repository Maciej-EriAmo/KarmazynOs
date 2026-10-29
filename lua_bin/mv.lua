local id = karmazyn.read_line("ID Atomu: ") or ""
if id == "" then return end

local atom = karmazyn.get_atom(id)
if not atom then
    print("✗ Atom nie istnieje.")
    return
end

print("Bieżąca warstwa: " .. atom.state)
local layer_raw = karmazyn.read_line("Nowa warstwa (HOT/WARM/COLD): ")
if layer_raw == nil then return end
local new_layer = string.upper(layer_raw)

if new_layer == "HOT" or new_layer == "WARM" or new_layer == "COLD" then
    if atom.set_state(new_layer) then
        print("✓ Przeniesiono do " .. new_layer)
    else
        print("✗ Błąd przenoszenia.")
    end
else
    print("Nieprawidłowa warstwa.")
end
