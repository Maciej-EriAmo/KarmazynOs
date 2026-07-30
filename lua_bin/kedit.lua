-- kedit.lua — edycja atomu w Φ (host API karmazyn.*)
local id = karmazyn.read_line("ID Atomu do edycji: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if not atom then
    print("✗ Atom " .. id .. " nie istnieje.")
    return
end

while true do
    local menu = {
        "1. Zmień Emanację (E)",
        "2. Stabilizuj (Refresh)",
        "3. Skonsoliduj do bąbla",
        "4. Wyjdź"
    }
    print(karmazyn.ui.draw_frame("KEDIT: " .. atom.id, menu, "phi_core"))

    local choice = karmazyn.read_line("Wybór: ")

    if choice == "1" then
        print("Aktualna E: " .. tostring(atom.E))
        local new_e = karmazyn.read_line("Nowa Emanacja: ")
        if new_e ~= "" then
            atom.set_E(new_e)
            print("✓ Zaktualizowano w pamięci operacyjnej Φ.")
        end
    elseif choice == "2" then
        atom.refresh()
        print("✓ Energia atomu przywrócona w Φ.")
    elseif choice == "3" then
        local bid = atom.consolidate()
        if bid then
            print("✓ Pomyślnie zapisano do trwałego Bąbla: " .. tostring(bid))
            print("  [Informacja przetrwa restart systemu i Vacuum Decay]")
        else
            print("✗ Błąd utrwalania informacji.")
        end
    elseif choice == "4" or choice == "" then
        break
    else
        print("Nieprawidłowy wybór.")
    end
end
