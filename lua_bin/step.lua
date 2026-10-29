local n_str = karmazyn.read_line("Liczba kroków termodynamicznych [1]: ")
if n_str == nil then return end
local n = tonumber(n_str) or 1

karmazyn.step(n)
print("System przesunięty o " .. n .. " epok.")
