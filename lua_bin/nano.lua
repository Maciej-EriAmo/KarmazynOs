local id = karmazyn.read_line("nano - ID Atomu: ")
if id == "" then return end

local atom = karmazyn.get_atom(id)
if not atom then
    print("✗ Atom " .. id .. " nie istnieje.")
    return
end

-- Wczytaj istniejącą treść
local lines = {}
for line in string.gmatch(atom.E, "[^\r\n]+") do
    table.insert(lines, line)
end

print("Edycja Emanacji (E) dla " .. atom.id)
print("Komendy: .save, .abort, .del <n>, .ins <n> <tekst>, .list")
print("Wpisanie tekstu dodaje nową linię na końcu.")

local function list_lines()
    local display = {}
    for i, line in ipairs(lines) do
        table.insert(display, string.format("%02d | %s", i, line))
    end
    print(karmazyn.ui.draw_frame("BUFOR: " .. atom.id, display, "phi_signal"))
end

list_lines()

while true do
    local input = karmazyn.read_line("> ")

    if input == ".save" then
        atom.set_E(table.concat(lines, "\n"))
        print("✓ Zapisano.")
        break
    elseif input == ".abort" then
        print("Anulowano.")
        break
    elseif input == ".list" then
        list_lines()
    elseif string.match(input, "^.del %d+") then
        local n = tonumber(string.match(input, "%d+"))
        if lines[n] then
            table.remove(lines, n)
            print("Line " .. n .. " deleted.")
        else
            print("Invalid line number.")
        end
    elseif string.match(input, "^.ins %d+") then
        local n, text = string.match(input, "^.ins (%d+) (.*)")
        n = tonumber(n)
        if n and n >= 1 and n <= #lines + 1 then
            table.insert(lines, n, text or "")
            print("Line inserted.")
        else
            print("Invalid insertion point.")
        end
    else
        table.insert(lines, input)
    end
end
