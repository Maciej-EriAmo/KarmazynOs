local agents = karmazyn.list_agents()
local lines = {}

for i = 1, #agents do
    local ag = agents[i]
    local p_list = ""
    for j = 1, #ag.prisms do
        p_list = p_list .. ag.prisms[j] .. " "
    end
    table.insert(lines, string.format("[%d] %-10s | Task: %-15s | Prisms: %s", ag.pid, ag.name, ag.task, p_list))
end

if #lines == 0 then
    print("Brak aktywnych agentów.")
else
    print(karmazyn.ui.draw_frame("ACTIVE AGENTS (ps)", lines, "phi_signal"))
end
