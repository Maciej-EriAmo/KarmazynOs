local pid_str = karmazyn.read_line("PID Agenta do usunięcia: ")
local pid = tonumber(pid_str)

if pid then
    if karmazyn.delete_agent(pid) then
        print("✓ Agent [" .. pid .. "] usunięty.")
    else
        print("✗ Nie znaleziono agenta o PID: " .. pid)
    end
else
    print("Nieprawidłowy PID.")
end
