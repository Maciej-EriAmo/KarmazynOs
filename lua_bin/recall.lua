local query = karmazyn.read_line("Zapytanie asocjacyjne: ")
if query == "" then return end

local results = karmazyn.recall(query, 5)
local lines = {}

for i = 1, #results do
    local r = results[i]
    local icon = "⚛"
    if r.layer == "bubble" then icon = "🫧" end

    local bar = karmazyn.ui.progress_bar(r.score * 100, 100, 10, "phi_bright")
    table.insert(lines, string.format("%s %-12s | Sim: %.2f | Score: %s %.1f", icon, r.label, r.sim, bar, r.score * 100))
end

if #lines == 0 then
    print("Pustka semantyczna.")
else
    print(karmazyn.ui.draw_frame("RECALL: " .. query, lines, "phi_stable"))
end
