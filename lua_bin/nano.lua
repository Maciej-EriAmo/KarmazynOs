-- nano.lua – edytor tekstu dla KarmazynOS (wersja fs/cache)
-- Użycie: nano [nazwa_bąbla] [--temp]
--         nano <katalog>/<plik>     np. nano bin/hej, nano lib/mat
-- Domyślnie zapisuje trwale w bąblu. Flaga --temp używa tymczasowego cache (atomy).
-- Tryb pliku czyta i pisze karmazyn.fs(katalog, plik), zachowuje puste linie,
-- a w bin/ i lib/ przed zapisem sprawdza składnię Lua.

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
-- nano katalog/plik: plik w fs zamiast domyślnego "dokument"
local file_mode = false
if not temp_mode then
    local d, f = bubble_name:match("^([^/]+)/([^/]+)$")
    if d then
        bubble_name, file_id, file_mode = d, f, true
    end
end
local code_mode = file_mode and (bubble_name == "bin" or bubble_name == "lib")
local title = file_mode and (bubble_name .. "/" .. file_id) or bubble_name

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
        if file_mode then
            return ""
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
        return karmazyn.fs.write(bubble_name, file_id, code_mode and "lua" or "nano-editor", content)
    end
end

-- Wczytaj istniejącą treść
local content = load_content()
local lines = {}
if file_mode then
    -- puste linie zostają (kod); końcowy \n nie tworzy pustej linii
    if content ~= "" then
        local text = content:gsub("\r", "")
        if text:sub(-1) ~= "\n" then
            text = text .. "\n"
        end
        for line in text:gmatch("(.-)\n") do
            table.insert(lines, line)
        end
    end
else
    for line in content:gmatch("[^\r\n]+") do
        table.insert(lines, line)
    end
end

-- Wyświetl aktualny bufor
local function list_lines()
    print("\n===== " .. title .. (temp_mode and " (tymcz.)" or "") .. " =====")
    for i, line in ipairs(lines) do
        print(string.format("%02d | %s", i, line))
    end
    if not file_mode then
        print(karmazyn.ui.draw_frame(bubble_name, lines, "phi_signal"))
    end
end

local function persist()
    local text = table.concat(lines, "\n")
    if code_mode and load then
        local _, err = load(text, "=" .. title)
        if err then
            print("⚠ Błąd składni (zapisuję mimo to): " .. tostring(err))
        end
    end
    local ok = save_content(text)
    if file_mode then
        return ok, nil
    end
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
print("Komendy: .save, .abort, .del N, .ins N tekst, .set N tekst, .list")

-- Główna pętla edycji
while true do
    local input = karmazyn.read_line("> ")
    if input == nil or (input == "" and not karmazyn.interactive()) then break end

    if input == ".save" then
        local ok, atom = persist()
        if ok == true or (type(ok) == "string" and ok:match("^True")) then
            if file_mode then
                print("✓ Zapisano " .. title .. " (" .. #lines .. " linii). `sync` zapisze na dysk.")
            else
                print("✓ Zapisano w " .. bubble_name .. " (" .. tostring(type(atom) == "table" and atom.id or "?") .. ").")
            end
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
    elseif input:match("^%.set (%d+) (.*)$") then
        local n, text = input:match("^%.set (%d+) (.*)$")
        n = tonumber(n)
        if n and lines[n] then
            lines[n] = text
            print("Zmieniono linię " .. n)
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