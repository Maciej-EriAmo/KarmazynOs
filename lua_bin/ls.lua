local atoms = karmazyn.list_atoms()
local lines = {}
local tmax = karmazyn.T_MAX or 100

for i = 1, #atoms do
    local a = atoms[i]
    -- T substratu 0..T_MAX; pasek w %
    local T_percent = (a.get_T_frac and a.get_T_frac() or (a.get_T() / tmax)) * 100
    local bar = karmazyn.ui.progress_bar(T_percent, 100, 20, "phi_ember")
    local line = string.format("%-12s %s %5.1f%% %-6s T=%.1f", a.id, bar, T_percent, a.state, a.get_T())
    table.insert(lines, line)
end

if #lines == 0 then
    print("Pustka. Brak aktywnych atomów w Φ.")
else
    print(karmazyn.ui.draw_frame("Φ-LIST (LUA)", lines, "phi_signal"))
end
