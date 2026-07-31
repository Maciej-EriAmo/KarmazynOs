local id = karmazyn.read_line("ID Atomu/Bąbla: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if atom then
    local lines = {
        "Sygnatura (S): " .. atom.S,
        "Emanacja   (E): " .. atom.E,
        "Stan: " .. atom.state .. " (T=" .. string.format("%.1f", atom.get_T())
            .. " / " .. tostring(karmazyn.T_MAX or 100) .. " → "
            .. string.format("%.0f%%", (atom.get_T_frac and atom.get_T_frac() or 0) * 100) .. ")"
    }
    print(karmazyn.ui.draw_frame("ATOM: " .. atom.id, lines, "phi_signal"))
else
    -- Spróbujmy poszukać bąbla jeśli nie ma atomu
    print("✗ Nie znaleziono atomu " .. id .. ". Sprawdzam bąble...")
    -- Tu moglibyśmy dodać obsługę bąbli jeśli API na to pozwala
end
