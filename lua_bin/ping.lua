local id1 = karmazyn.read_line("Atom A: ")
if id1 == "" then return end

local id2 = karmazyn.read_line("Atom B: ")
if id2 == "" then return end

local sim = karmazyn.get_similarity(id1, id2)

if sim then
    local lines = {
        "Rezonans semantyczny między:",
        "  -> " .. id1,
        "  -> " .. id2,
        "-----------------------------",
        "Współczynnik: " .. string.format("%.4f", sim)
    }
    local style = "phi_stable"
    if sim > 0.8 then style = "phi_bright" elseif sim < 0.2 then style = "phi_decay" end
    print(karmazyn.ui.draw_frame("SEMANTIC PING", lines, style))
else
    print("✗ Błąd: Jeden z atomów nie istnieje.")
end
