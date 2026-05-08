local id = karmazyn.read_line("Stat - ID Atomu: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if atom then
    local lines = {
        "ID:        " .. atom.id,
        "Wiek:      " .. atom.age .. " epok",
        "Stan:      " .. atom.state,
        "Energia T: " .. string.format("%.4f", atom.T_raw),
        "Emanacja:  " .. string.sub(atom.E, 1, 30),
        "Sygnatura: " .. string.sub(atom.S, 1, 30)
    }
    print(karmazyn.ui.draw_frame("METADATA: " .. atom.id, lines, "phi_signal"))
else
    print("✗ Atom " .. id .. " nie istnieje.")
end
