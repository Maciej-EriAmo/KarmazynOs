-- Semantic ping — rezonans Lorentza R(a,b) przez karmazyn.get_similarity
local id1 = karmazyn.read_line("Atom A: ")
if id1 == "" then return end

local id2 = karmazyn.read_line("Atom B: ")
if id2 == "" then return end

local a = karmazyn.get_atom(id1)
local b = karmazyn.get_atom(id2)
if not a then
    print("✗ Brak atomu: " .. id1)
    return
end
if not b then
    print("✗ Brak atomu: " .. id2)
    return
end

local sim = karmazyn.get_similarity(id1, id2)
if sim == nil then
    print("✗ Błąd: get_similarity zwróciło nil")
    return
end

local lines = {
    "Rezonans Lorentza R między:",
    "  -> " .. id1 .. "  E=" .. tostring(a.E or ""),
    "  -> " .. id2 .. "  E=" .. tostring(b.E or ""),
    "-----------------------------",
    "R: " .. string.format("%.4f", sim)
}
local style = "phi_stable"
if sim > 0.8 then
    style = "phi_bright"
elseif sim < 0.2 then
    style = "phi_decay"
end
print(karmazyn.ui.draw_frame("SEMANTIC PING", lines, style))
