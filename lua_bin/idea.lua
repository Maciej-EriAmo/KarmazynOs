local hid = karmazyn.read_line("ID Hologramu: ")
if hid == "" then return end

local prompt = karmazyn.read_line("Prompt do generowania: ")
if prompt == "" then return end

local vec = karmazyn.generate_from_idea(hid, prompt, 0.3)

if type(vec) == "table" then
    print("✓ Wygenerowano syntetyczny wektor z idei: " .. hid)
    print("Wymiar: " .. #vec)
    -- Tutaj moglibyśmy dodać manifestację wektora jako nowego atomu
else
    print("✗ Błąd generowania (hologram może być wygasły lub nie istnieć).")
end
