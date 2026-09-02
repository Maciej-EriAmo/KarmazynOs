-- Recall — rezonans Lorentza (R); pasek znormalizowany min(R,1)
local query = karmazyn.read_line("Zapytanie asocjacyjne: ")
if query == "" then return end

local results = karmazyn.recall(query, 5)
local lines = {}

for i = 1, #results do
    local r = results[i]
    local icon = "⚛"
    if r.layer == "bubble" then icon = "🫧" end
    if r.layer == "lorentz" then icon = "◈" end

    local score = tonumber(r.score) or tonumber(r.sim) or 0
    -- R Lorentza bywa > 1; pasek 0..100% z ucięciem, obok surowe R
    local bar_v = math.min(score, 1.0) * 100
    local bar = karmazyn.ui.progress_bar(bar_v, 100, 10, "phi_bright")
    local label = tostring(r.label or r.id or "?")
    table.insert(lines, string.format(
        "%s %-14s | R: %.4f | %s",
        icon, label, score, bar
    ))
end

if #lines == 0 then
    print("Pustka semantyczna.")
else
    print(karmazyn.ui.draw_frame("RECALL: " .. query, lines, "phi_stable"))
end
