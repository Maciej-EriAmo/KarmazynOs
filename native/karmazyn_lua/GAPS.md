# Luki mlua wobec karmazyn_lua 1.1.2

Te przypadki zostają na `karmazyn.cmd --python`. Porównanie z wyrocznią je pomija.

- Tekst błędu składni pochodzi z parsera mlua, nie z parsera Pythona.
- Sterta Lua (tabele, domknięcia, stos) nie wchodzi w snapshot KSUB. `load` odtwarza bąbel sesji `"lua"` i aliasy z jego wiązań, nie skrypty. Wiek po `load` liczy się od nowa.
- `karmazyn.create_atom` i `clone_atom` zwracają proxy (id, S, E, state, get_T, get_T_frac, set_E, set_state) albo tekst błędu. Piąty argument (energia tracera) jest ignorowany: natywny Store nie ma tracera.
- `list_atoms` zwraca proxy aliasów sesji. Filtr `HOT|WARM|COLD|TOMB` działa. `ALL` to te same aliasy, nie atomy silnika spoza `karmazyn.*`.
- `age` to epoki sesji od `create_atom`. Liczy je `karmazyn.step` oraz polecenia powłoki `tick` i `settle` (tyle ticków, ile zaszło w magazynie). To nie są sekundy zegara ściennego z Pythona.
- `fs`, `cache`, agenci i hologramy są mapami sesji. Giną z procesem. Nie wchodzą w snapshot.
- Tabela Lua nie jest bąblem. `collectgarbage` czyści stertę PUC. Atomy `karmazyn.*` trzyma korzeń sesji i zbiera je `karmazyn.step`.
- `recall` i `get_similarity` liczą warstwę `substr` (tekst S/E/id). Most Lorentza i HRR zostają na Pythonie.
- `debug.*` z kontraktu 1.1 zostaje na Pythonie. W tym gościu `debug` jest wyłączone.
- `ui.progress_bar` i `ui.draw_frame` są formatterami tekstu. Styl (`phi_ember` i reszta) nie zmienia rysunku.
- `_VERSION` gościa to `Lua 5.4 (Karmazyn mlua)`. Python zostaje przy `Lua 5.5 (Karmazyn subset)`.
