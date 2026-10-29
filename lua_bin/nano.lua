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
local function saved_atom_text()
    local saved = karmazyn.get_atom("nano_" .. bubble_name)
    if type(saved) == "table" and type(saved.E) == "string" then
        return saved.E
    end
    return ""
end

local function load_content()
    if temp_mode then
        local cached = karmazyn.cache.read(bubble_name)
        if cached ~= nil then
            return cached.E or ""
        end
    else
        local text = karmazyn.fs.read(bubble_name, file_id)
        if text ~= nil then
            return text
        end
    end
    return saved_atom_text()
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
    print(karmazyn.ui.draw_frame(bubble_name, lines, "phi_signal"))
end

local function persist()
    local text = table.concat(lines, "\n")
    local ok = save_content(text)
    local id = "nano_" .. bubble_name
    local atom = karmazyn.get_atom(id)
    if type(atom) ~= "table" then
        atom = karmazyn.create_atom(id, "nano", text, karmazyn.T_INIT)
    end
    if type(atom) == "table" then
        atom.set_E(text)
    end
    return ok, atom
end

list_lines()
print("Komendy: .save, .abort, .del N, .ins N tekst, .list")

-- Główna pętla edycji
while true do
    local input = karmazyn.read_line("> ")
    if input == nil or (input == "" and not karmazyn.interactive()) then break end

    if input == ".save" then
        local ok, atom = persist()
        if ok == true or (type(ok) == "string" and ok:match("^True")) then
            print("✓ Zapisano w " .. bubble_name .. " (" .. tostring(type(atom) == "table" and atom.id or "?") .. ").")
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