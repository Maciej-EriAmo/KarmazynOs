local layer = string.upper(karmazyn.read_line("Warstwa (HOT/WARM/COLD/TOMB) [ALL]: "))
local min_t_str = karmazyn.read_line("Minimalna temperatura (0-100) [0]: ")
local min_t = tonumber(min_t_str) or 0

local atoms = karmazyn.list_atoms()
local results = {}

for i = 1, #atoms do
    local a = atoms[i]
    local match = true

    if layer ~= "" and a.state ~= layer then match = false end
    if a.T_raw < min_t then match = false end

    if match then
        table.insert(results, string.format("[%s] T=%.1f | %s", a.id, a.T_raw, a.state))
    end
end

if #results > 0 then
    print(karmazyn.ui.draw_frame("FIND RESULTS", results, "phi_signal"))
else
    print("Brak atomów spełniających kryteria.")
end
