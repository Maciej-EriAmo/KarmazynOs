-- nano.lua – edytor tekstu dla KarmazynOS (wersja fs/cache)
-- Użycie: nano [nazwa_bąbla] [--temp]
-- Domyślnie zapisuje trwale w bąblu. Flaga --temp używa tymczasowego cache (atomy).

local args = {...}
local bubble_name = "notatki"
local temp_mode = false

for i, a in ipairs(args) do
    if a == "--temp" then
        temp_mode = true
    elseif not temp_mode and not a:match("^%-") then
        bubble_name = a
    end
end

local file_id = "dokument"

-- Funkcja do odczytu treści
local function load_content()
    if temp_mode then
        -- Tryb tymczasowy: odczyt z cache (atom)
        local atom = karmazyn.cache.read(bubble_name)
        return atom and atom.E or ""
    else
        -- Tryb trwały: odczyt z bąbla
        return karmazyn.fs.read(bubble_name, file_id) or ""
    end
end

-- Funkcja do zapisu treści
local function save_content(content)
    if temp_mode then
        -- Zapis do cache (atom)
        return karmazyn.cache.write(bubble_name, "nano", content, 1.0)
    else
        -- Zapis do bąbla
        return karmazyn.fs.write(bubble_name, file_id, "nano-editor", content)
    end
end

-- Wczytaj istniejącą treść
local content = load_content()
local lines = {}
for line in content:gmatch("[^\r\n]+") do
    table.insert(lines, line)
end

-- Wyświetl aktualny bufor
local function list_lines()
    print("\n===== " .. bubble_name .. (temp_mode and " (tymcz.)" or "") .. " =====")
    for i, line in ipairs(lines) do
        print(string.format("%02d | %s", i, line))
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
    print("==================")
end

list_lines()
print("Komendy: .save, .abort, .del N, .ins N tekst, .list")

-- Główna pętla edycji
while true do
    local input = karmazyn.read_line("> ")
    if not input then break end

    if input == ".save" then
        save_to_bubble()
        local new_content = table.concat(lines, "\n")
        local ok = save_content(new_content)
        if ok == true or (type(ok) == "string" and ok:match("^True")) then
            print("✓ Zapisano.")
        else
            print("✗ Błąd zapisu: " .. tostring(ok))
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