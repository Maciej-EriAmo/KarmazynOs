
# Most LSM dla HolonOS

Ten katalog zawiera mostek umożliwiający KarmazynOS odpowiadanie na zapytania kontroli dostępu z modułu bezpieczeństwa `holo_lsm` jądra Linux.

## Jak to działa

1. `holo_lsm` przechwytuje operacje plikowe na i-węzłach oznaczonych `security.hss.lock`.
2. Wysyła strukturę `hss_upcall_msg` do gniazda Unix (`/run/hss-daemon.sock`).
3. `hss_bridge.py` nasłuchuje na tym gnieździe, przekazuje żądanie do KarmazynOS.
4. KarmazynOS ocenia kontekst (`phi_context`, identyfikator agenta, politykę) i zwraca decyzję.
5. Mostek odsyła `hss_upcall_resp` do jądra, które egzekwuje decyzję.

## Wymagania

- Jądro Linux z załadowanym `holo_lsm`.
- Python 3.10+ z `karmazyn.py` i `numpy`.

## Użycie

```bash
sudo python hss_bridge.py
