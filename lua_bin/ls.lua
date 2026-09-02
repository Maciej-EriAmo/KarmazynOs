-- Lista atomów powierzchni Φ (logiczne id, nie u32 native / nie heap aN)
local atoms = karmazyn.list_atoms()
local lines = {}
local tmax = karmazyn.T_MAX or 100

for i = 1, #atoms do
    local a = atoms[i]
    local T_percent = (a.get_T_frac and a.get_T_frac() or (a.get_T() / tmax)) * 100
    local bar = karmazyn.ui.progress_bar(T_percent, 100, 20, "phi_ember")
    local id = tostring(a.id)
    -- ukryj szum I/O jeśli kiedyś wpadnie na listę
    if string.sub(id, 1, 3) == "io:" then
        -- skip
    else
        local e = tostring(a.E or "")
        if #e > 18 then e = string.sub(e, 1, 18) .. "…" end
        local line = string.format("%-12s %s %5.1f%% %-6s %s", id, bar, T_percent, a.state, e)
        table.insert(lines, line)
    end
end

if #lines == 0 then
    print("Pustka. Brak aktywnych atomów w Φ.")
    print("Utwórz: :tool touch   (potem :tool ping)")
else
    print(karmazyn.ui.draw_frame("Φ-LIST (LUA)", lines, "phi_signal"))
end
