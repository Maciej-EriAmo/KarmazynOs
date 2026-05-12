-- nano.lua – edytor bąbla (trwały)
-- Użycie: nano [nazwa_bąbla]
local args = {...}
local bubble_name = args[1] or "notatki"

-- Pobierz lub utwórz bąbel
local bubble = karmazyn.get_bubble(bubble_name)
if not bubble then
    bubble = karmazyn.create_bubble(bubble_name, "document")
    print("🫧 Utworzono nowy bąbel: " .. bubble_name)
end

-- Wczytaj istniejącą zawartość (pierwszy atom w bąblu)
local lines = {}
local atoms = bubble:get_atoms() or {}
local main_atom = atoms[1]
if main_atom then
    local content = main_atom:get_content() or ""
    for line in content:gmatch("[^\r\n]+") do
        table.insert(lines, line)
    end
end

local function list_lines()
    local display = {}
    for i, line in ipairs(lines) do
        table.insert(display, string.format("%02d | %s", i, line))
    end
    print(karmazyn.ui.draw_frame(bubble_name, display, "phi_signal"))
end

local function save_to_bubble()
    -- Usuń stare atomy
    for _, a in ipairs(bubble:get_atoms() or {}) do
        bubble:remove_atom(a.id)
    end
    -- Utwórz nowy atom z zawartością
    local new_atom = karmazyn.create_atom("doc_" .. os.time(), "nano", "dokument", 1.0)
    new_atom:set_content(table.concat(lines, "\n"))
    bubble:add_atom(new_atom)
    print("✓ Zapisano w bąblu: " .. bubble_name)
end

list_lines()
print("Komendy: .save, .abort, .del N, .ins N tekst, .list")

while true do
    local input = karmazyn.read_line("> ")
    if not input then break end

    if input == ".save" then
        save_to_bubble()
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
            print("❌ Nieprawidłowy numer.")
        end
    elseif input:match("^%.ins (%d+) (.*)$") then
        local n, text = input:match("^%.ins (%d+) (.*)$")
        n = tonumber(n)
        if n and n >= 1 and n <= #lines+1 then
            table.insert(lines, n, text)
            print("Wstawiono linię " .. n)
        else
            print("❌ Nieprawidłowe miejsce.")
        end
    else
        table.insert(lines, input)
        print("→ Dodano linię " .. #lines)
    end
end
