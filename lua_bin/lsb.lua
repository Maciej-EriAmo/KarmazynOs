local bubbles = karmazyn.list_bubbles()
local lines = {}

for i = 1, #bubbles do
    local b = bubbles[i]
    table.insert(lines, string.format("%-15s | %-20s | Content: %s", b.id, b.label, string.sub(b.content, 1, 40)))
end

if #lines == 0 then
    print("Brak trwałych bąbli w systemie.")
else
    print(karmazyn.ui.draw_frame("PERSISTENT BUBBLES (lsb)", lines, "phi_core"))
end
