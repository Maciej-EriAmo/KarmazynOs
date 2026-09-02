-- Tworzy atom Φ. Opcjonalnie energia tracer (Enter = 1.0).
local id = karmazyn.read_line("ID Atomu: ")
if id == "" then return end

local s = karmazyn.read_line("Sygnatura (S): ")
local e = karmazyn.read_line("Emanacja (E): ")
local tr = karmazyn.read_line("Tracer energy [1.0]: ")
local energy = 1.0
if tr ~= nil and tr ~= "" then
    energy = tonumber(tr) or 1.0
end

local atom = karmazyn.create_atom(id, s, e, karmazyn.T_INIT, energy)
if type(atom) == "table" then
    print("✓ Stworzono atom: " .. tostring(atom.id) .. "  tracer.energy=" .. tostring(energy))
    print("  podpowiedź: :tool ls   potem :tool ping")
else
    print("✗ Błąd: " .. tostring(atom))
end
