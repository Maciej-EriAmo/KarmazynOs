-- nano.lua – edytor atomów z opcją konsolidacji do bąbla
-- Użycie: nano [nazwa_atomu]
-- Jeśli atom nie istnieje, zostanie utworzony.
-- Komendy: .save (zapis do atomu), .bubble (konsoliduj do bąbla), .abort, .del N, .ins N tekst, .list

local args = {...}
local atom_name = args[1] or "notatka_" .. os.time()

local atom = karmazyn.get_atom(atom_name)
if not atom then
    print("Tworzę nowy atom: " .. atom_name)
    atom = karmazyn.create_atom(atom_name, "Edycja", "notatka", 0.9)
end

-- Pobierz treść (zakładam, że jest w polu S – sygnatura semantyczna)
local content = atom.S or ""
local lines = {}
for line in string.gmatch(content, "[^\r\n]+") do
    table.insert(lines, line)
end

local function list_lines()
    print("\n===== " .. atom_name .. " =====")
    for i, line in ipairs(lines) do
        print(string.format("%02d | %s", i, line))
    end
    print("==================")
end

list_lines()
print("Komendy: .save, .bubble, .abort, .del N, .ins N tekst, .list")

while true do
    local input = karmazyn.read_line("> ")
    if not input then break end

    if input == ".save" then
        atom.set_E(table.concat(lines, "\n"))
        print("✓ Zapisano w atomie (ulotny).")
        break
    elseif input == ".bubble" then
        atom.set_E(table.concat(lines, "\n"))
        local bid = atom.consolidate()
        if bid then
            print("✓ Skonsolidowano do bąbla: " .. tostring(bid))
        else
            print("✗ Błąd konsolidacji.")
        end
        break
    elseif input == ".abort" then
        print("Anulowano.")
        break
    elseif input == ".list" then
        list_lines()
    elseif input:match("^%.del (%d+)$") then
        local n = tonumber(input:match("%d+"))
        if n and lines[n] then
            table.remove(lines, n)
            print("Usunięto linię " .. n)
        else
            print("Nieprawidłowy numer.")
        end
    elseif input:match("^%.ins (%d+) (.*)$") then
        local n, text = input:match("^%.ins (%d+) (.*)$")
        n = tonumber(n)
        if n and n >= 1 and n <= #lines+1 then
            table.insert(lines, n, text)
            print("Wstawiono linię " .. n)
        else
            print("Nieprawidłowe miejsce.")
        end
    else
        table.insert(lines, input)
        print("Dodano linię " .. #lines)
    end
end
