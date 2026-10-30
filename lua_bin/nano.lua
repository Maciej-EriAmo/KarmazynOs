-- nano.lua – edytor bąbla kodu
-- Użycie: nano [etykieta] [--temp]
-- Domyślnie etykieta „notatki”. Zapis idzie w bąbel (atom src).
-- --temp trzyma tekst w cache sesji.
-- Puste linie zostają. Przed zapisem sprawdzenie składni Lua.

local args = {...}
local label = "notatki"
local temp_mode = false

for _, a in ipairs(args) do
    if a == "--temp" then
        temp_mode = true
    elseif not a:match("^%-") then
        label = a
    end
end

local function load_content()
    if temp_mode then
        local cached = karmazyn.cache.read(label)
        if cached ~= nil then
            return cached.E or ""
        end
        return ""
    end
    return karmazyn.code.read(label) or ""
end

local function save_content(content)
    if temp_mode then
        return karmazyn.cache.write(label, "nano", content, 1.0)
    end
    return karmazyn.code.write(label, content)
end

local content = load_content()
local lines = {}
if content ~= "" then
    local text = content:gsub("\r", "")
    if text:sub(-1) ~= "\n" then
        text = text .. "\n"
    end
    for line in text:gmatch("(.-)\n") do
        table.insert(lines, line)
    end
end

local function list_lines()
    print("\n===== " .. label .. (temp_mode and " (tymcz.)" or "") .. " =====")
    for i, line in ipairs(lines) do
        print(string.format("%02d | %s", i, line))
    end
end

local function persist()
    local text = table.concat(lines, "\n")
    if not temp_mode and load then
        local _, err = load(text, "=" .. label)
        if err then
            print("⚠ Błąd składni (zapisuję mimo to): " .. tostring(err))
        end
    end
    return save_content(text)
end

list_lines()
print("Komendy: .save, .abort, .del N, .ins N tekst, .set N tekst, .list")

while true do
    local input = karmazyn.read_line("> ")
    if input == nil or (input == "" and not karmazyn.interactive()) then break end

    if input == ".save" then
        local ok = persist()
        if ok == true or (type(ok) == "string" and ok:match("^True")) then
            print("✓ Zapisano " .. label .. " (" .. #lines .. " linii).")
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
        if n and n >= 1 and n <= #lines + 1 then
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
