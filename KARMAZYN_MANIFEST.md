# KONSTYTUCJA KARMAZYNOS
**V1.0 | Operacyjna Przestrzeń Znaczeń**

---

## I. Ontologia Informacji

1. **Idea ponad Wartość**  
   KarmazynOS nie przechowuje danych, lecz idee. Każdy bąbel i hologram jest przestrzenią latentną, a nie rekordem w bazie.

2. **Brak Prymatu Formatu**  
   Format (TXT, JSON, .bubble) jest wtórną projekcją. Znaczenie istnieje niezależnie od reprezentacji.

3. **Zapominanie jako Funkcja**  
   Entropia jest naturalnym procesem systemowym. Informacja, która nie jest podsycana uwagą, ulega stabilnemu wygaszeniu (**Vacuum Decay**).

---

## II. Architektura Bytów

4. **Atomy (Stan Przejściowy)**  
   Ulotne jednostki w przestrzeni roboczej **Φ**. Służą do komunikacji, obliczeń transientnych i bieżącej myśli.

5. **Bąble (Domeny Semantyczne)**  
   Nieprzeniknione, trwałe przestrzenie robocze. Stanowią bezpieczne piaskownice (sandboxy) z kryptograficzną membraną.

6. **Hologramy (Pola Wpływu)**  
   Struktury idei generujące nowe myśli poprzez kontrolowany szum. Nie są kopiami danych, lecz ich syntetyczną predykcją.

---

## III. Fizyka Bezpieczeństwa (HSS v2.5.0)

7. **Topologia zamiast Polityki**  
   Bezpieczeństwo jest własnością geometryczną przestrzeni **Φ**. Agent istnieje tylko w obszarze zdefiniowanym przez jego klucz derywowany (KDF).

8. **No-Plaintext-In-Kernel**  
   Moduł jądra (LSM) jest wyłącznie filtrem upcall. Żadne dane w formie jawnej nie mają prawa znaleźć się w pamięci jądra.

9. **Kryptograficzna Izolacja**  
   Każda operacja poza wyznaczoną Φ-przestrzenią musi skutkować odczytem szumu (**Chaosu**), a nie błędem dostępu.

---

## IV. Środowisko Agentowe

10. **Budżet Poznawczy**  
    Agent nie otrzymuje uprawnień, lecz przydział energii **Φ** i ograniczenia entropii wewnątrz swojego Workspace Bubble.

11. **Autonomia i Ład**  
    System dąży do stabilizacji informacji. Każda anomalia energetyczna jest tłumiona lub konsolidowana w nowe struktury wiedzy.

---

## ARCHITECTURE.pl.md – Kluczowe Rewizje

W pliku architektonicznym należy podmienić sekcje dotyczące bezpieczeństwa i modelu pamięci, aby wyeliminować przestarzałe koncepcje *"plików"*.

### Zaktualizowany Model HSS (Holographic Session Spaces)

- **Mechanizm Izolacji**  
  Zamiast list ACL, system stosuje **PrismMasks** oparte na **Ring-LWE**.

- **Derywacja Kluczy**  
  Stosujemy wyłącznie KDF-based attenuation. Klucz agenta $s_A$ jest obliczany jako:

  ```math
  s_A = KDF(s_{sess}, agent_id, authorized_prisms)
