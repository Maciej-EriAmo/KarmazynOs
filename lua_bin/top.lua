print("Termodynamiczny podgląd systemowy (naciśnij Ctrl+C aby przerwać)")
karmazyn.sleep(1)

while true do
    karmazyn.clear_screen()
    local atoms = karmazyn.list_atoms()
    local lines = {}

    for i = 1, math.min(#atoms, 20) do
        local a = atoms[i]
        local tmax = karmazyn.T_MAX or 100
        local T_percent = (a.get_T_frac and a.get_T_frac() or (a.get_T() / tmax)) * 100
        local bar = karmazyn.ui.progress_bar(T_percent, 100, 15, "phi_ember")
        table.insert(lines, string.format("%-10s %s %5.1f%% %-6s", a.id, bar, T_percent, a.state))
    end

    local stats = {
        "Epoka: " .. karmazyn.get_epoch(),
        "Atomy: " .. #atoms,
        "-------------------"
    }
    for _, l in ipairs(lines) do table.insert(stats, l) end

    print(karmazyn.ui.draw_frame("KARMAZYN TOP", stats, "phi_thermal"))
    karmazyn.sleep(2)
end
