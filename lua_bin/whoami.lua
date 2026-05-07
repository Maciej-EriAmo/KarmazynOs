print("KarmazynOS Node Identity")
print("------------------------")
-- SanctuaryRuntime doesn't have a direct get_phi_id like KarmazynOS kernel yet
-- but we can show some basic info
local epoch = karmazyn.get_epoch()
print("System Epoch: " .. epoch)
local atoms = karmazyn.list_atoms()
print("Phi State: " .. #atoms .. " atoms active")
