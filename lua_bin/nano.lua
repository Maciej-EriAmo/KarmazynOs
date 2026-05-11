-- nano.lua – edytor zawartości bąbla (trwały)
-- Użycie: nano [nazwa_bąbla] [--temp] [--atom nazwa_atomu]
-- Domyślnie: nano notatki
-- Jeśli bąbel nie istnieje, zostanie utworzony.

local args = {...}
local bubble_name = "notatki"
local temp_mode = false
local atom_name = nil

-- Parsowanie argumentów
for i, arg in ipairs(args) do
    if arg == "--temp" then
        temp_mode = true
    elseif arg == "--atom" then
        atom_name = args[i+1]
    elseif not arg:match("^%-%-") and bubble_name == "notatki" then
        bubble_name = arg
    end
end

local target_bubble = nil
local target_atom = nil

if temp_mode then
    -- Tryb tymczasowy: atom (ulotny)
    if not atom_name then
        print("❌ Tryb --temp wymaga --atom <nazwa>")
        return
    end
    target_atom = karmazyn.get_atom(atom_name)
    if not target_atom then
        print("❌ Atom '" .. atom_name .. "' nie istnieje.")
        return
    end
    print("🌡️ Edytujesz atom tymczasowy – po zamknięciu może wygasnąć.")
else
    -- Tryb trwały: bąbel
    target_bubble = karmazyn.get_bubble(bubble_name)
    if not target_bubble then
        target_bubble = karmazyn.create_bubble(bubble_name, "document")
        print("🫧 Utworzono nowy bąbel: " .. bubble_name)
    end
end

-- Pobierz istniejącą zawartość jako listę linii
local lines = {}
local current_content = ""

if target_bubble then
    current_content = target_bubble:content("CORE") or ""
elseif target_atom then
    current_content = target_atom:get_content() or ""
end

for line in string.gmatch(current_content, "[^\r\n]+") do
    table.insert(lines, line)
end

-- Funkcje pomocnicze
local function list_lines()
    local display = {}
    for i, line in ipairs(lines) do
        table.insert(display, string.format("%02d | %s", i, line))
    end
    local title = (target_bubble and "🫧 " .. bubble_name) or (target_atom and "⚛️ " .. atom_name) or "Edytor"
    print(karmazyn.ui.draw_frame(title, display, "phi_signal"))
end

local function save_to_atom()
    if not target_atom then
        -- Jeśli nie ma atomu docelowego, tworzymy nowy atom tymczasowy
        local new_id = "tmp_" .. os.time()
        target_atom = karmazyn.create_atom(new_id, "Nano", "Edycja", 0.8)
        atom_name = new_id
        print("⚛️ Utworzono nowy atom tymczasowy: " .. atom_name)
    end
    target_atom:set_content(table.concat(lines, "\n"))
    print("✓ Zapisano w atomie (ulotny): " .. atom_name)
end

local function save_to_bubble()
    if not target_bubble then
        target_bubble = karmazyn.create_bubble(bubble_name, "document")
        print("🫧 Utworzono bąbel: " .. bubble_name)
    end
    -- Bąbel przechowuje atomy, a nie bezpośrednio treść.
    -- Najprościej: usuwamy stare atomy i dodajemy nowy z całą treścią.
    -- W przyszłości można zrobię bardziej finezyjnie, ale na razie tak.
    local atoms = target_bubble:get_atoms()
    for _, atom in ipairs(atoms) do
        target_bubble:remove_atom(atom.id)
    end
    local new_atom = karmazyn.create_atom("nano_" .. os.time(), "nano", "edytor", 1.0)
    new_atom:set_content(table.concat(lines, "\n"))
    target_bubble:add_atom(new_atom)
    print("✓ Zapisano w bąblu (trwały): " .. bubble_name)
end

-- Główna pętla edycji
list_lines()
print("Komendy: .save_atom (zapis do atomu), .save_bubble (zapis do bąbla), .abort, .del <n>, .ins <n> <tekst>, .list")
print("Wpisanie tekstu dodaje nową linię na końcu.")

while true do
    local input = karmazyn.read_line("> ")
    if not input then break end

    if input == ".save_atom" then
        save_to_atom()
        break
    elseif input == ".save_bubble" then
        if temp_mode then
            print("⚠️ Jesteś w trybie ulotnym (--temp). Aby zapisać do bąbla, wywołaj bez --temp.")
        else
            save_to_bubble()
            break
        end
    elseif input == ".abort" then
        print("Anulowano.")
        break
    elseif input == ".list" then
        list_lines()
    elseif input:match("^%.del %d+$") then
        local n = tonumber(input:match("%d+"))
        if n and n >= 1 and n <= #lines then
            table.remove(lines, n)
            print("✓ Usunięto linię " .. n)
        else
            print("❌ Nieprawidłowy numer linii.")
        end
    elseif input:match("^%.ins %d+ .+") then
        local n, text = input:match("^%.ins (%d+) (.+)")
        n = tonumber(n)
        if n and n >= 1 and n <= #lines + 1 then
            table.insert(lines, n, text)
            print("✓ Wstawiono linię " .. n)
        else
            print("❌ Nieprawidłowe miejsce wstawienia.")
        end
    else
        table.insert(lines, input)
        print("→ Dodano linię " .. #lines)
    end
end
