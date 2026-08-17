local holos = karmazyn.list_holograms()
local lines = {}

for i = 1, #holos do
    local h = holos[i]
    table.insert(lines, string.format("%-25s | Topic: %-15s | Atoms: %d | Epoch: %d", h.id, h.topic, #h.atom_labels, h.epoch_created))
end

if #lines == 0 then
    print("Brak etykiet hologramu w SESJI (nie są w Store).")
else
    print(karmazyn.ui.draw_frame("SESSION HOLOGRAMS (lsh) — nie Store", lines, "phi_stable"))
end
