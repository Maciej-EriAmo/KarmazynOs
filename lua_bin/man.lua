-- man.lua — opis narzędzi lua_bin (karmazyn_lua 0.9)
local tools = {
    ls = "Listuje atomy w Φ.",
    cat = "Wyświetla treść atomu.",
    touch = "Tworzy nowy atom.",
    rm = "Usuwa atom.",
    cp = "Kopiuje atom (clone).",
    mv = "Przenosi atom między warstwami HOT/WARM/COLD.",
    df = "Statystyki termodynamiczne warstw.",
    free = "Zasoby store.stats.",
    du = "Użycie emanacji (długości E).",
    find = "Filtr warstwy / temperatury.",
    grep = "Szuka wzorca w S/E atomów.",
    stat = "Metadane atomu.",
    ps = "Listuje agentów rejestru SESJI (nie procesy, nie Store).",
    kill = "Usuwa wpis agenta sesji po PID.",
    uptime = "Epoki sesji (step).",
    whoami = "Informacje o węźle.",
    step = "Kroki termodynamiczne (settle).",
    consolidate = "Konsoliduje atom do bąbla-korzenia.",
    lsb = "Listuje bąble z etykietą.",
    lsh = "Listuje etykiety hologramu w SESJI (nie HRR, nie Store).",
    idea = "WYCOFANE: 16D EriAmo. Nie generuje wektora.",
    recall = "Wyszukiwanie asocjacyjne (resonance).",
    ping = "Podobieństwo semantyczne dwóch atomów.",
    kedit = "Menu edycji atomu.",
    clear = "Czyści ekran terminala.",
    man = "Ten opis.",
    -- deprecated w automatyzacji 0.9
    nano = "[DEPRECATED w smoke] Edytor linii — tylko ręcznie.",
    top = "[DEPRECATED w smoke] Podgląd w pętli — tylko ręcznie (Ctrl+C).",
}

local tool = karmazyn.read_line("Podaj nazwę narzędzia (puste = lista): ")
if tool == "" then
    local list = {}
    for k, _ in pairs(tools) do table.insert(list, k) end
    table.sort(list)
    print(karmazyn.ui.draw_frame("DOSTĘPNE NARZĘDZIA LUA (0.9)", list, "phi_signal"))
else
    local desc = tools[tool]
    if desc then
        print(karmazyn.ui.draw_frame("MAN: " .. tool, {desc}, "phi_core"))
    else
        print("Brak wpisu dla: " .. tool)
    end
end
