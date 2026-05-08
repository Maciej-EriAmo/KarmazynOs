local atoms = karmazyn.list_atoms()
local lines = {}

for i = 1, #atoms do
    local a = atoms[i]
    local T_percent = a.get_T() * 100
    local bar = karmazyn.ui.progress_bar(T_percent, 100, 20, "phi_ember")
    local line = string.format("%-10s %s %5.1f%% %-6s", a.id, bar, T_percent, a.state)
    table.insert(lines, line)
end

if #lines == 0 then
    print("Pustka. Brak aktywnych atomów w Φ.")
else
    print(karmazyn.ui.draw_frame("Φ-LIST (LUA)", lines, "phi_signal"))
end
