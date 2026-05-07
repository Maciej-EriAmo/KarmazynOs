local tools = {
    ls = "Listuje atomy i bąble w systemie.",
    cat = "Wyświetla pełną treść atomu.",
    touch = "Tworzy nowy atom.",
    rm = "Usuwa atom (przenosi do TOMB).",
    cp = "Kopiuje atom.",
    mv = "Przenosi atom między warstwami.",
    df = "Wyświetla statystyki termodynamiczne.",
    free = "Wyświetla zasoby i żywicę.",
    ps = "Listuje aktywnych agentów.",
    uptime = "Czas życia systemu w epokach.",
    whoami = "Informacje o węźle.",
    nano = "Edytor linii emanacji atomu.",
    kedit = "Menu zarządzania atomem.",
    recall = "Wyszukiwanie semantyczne.",
    step = "Wykonuje kroki termodynamiczne.",
    consolidate = "Stabilizuje atom do bąbla.",
    clear = "Czyści ekran."
}

local tool = karmazyn.read_line("Podaj nazwę narzędzia dla instrukcji (lub zostaw puste dla listy): ")
if tool == "" then
    local list = {}
    for k, _ in pairs(tools) do table.insert(list, k) end
    table.sort(list)
    print(karmazyn.ui.draw_frame("DOSTĘPNE NARZĘDZIA LUA", list, "phi_signal"))
else
    local desc = tools[tool]
    if desc then
        print(karmazyn.ui.draw_frame("MAN: " .. tool, {desc}, "phi_core"))
    else
        print("Brak wpisu dla: " .. tool)
    end
end
