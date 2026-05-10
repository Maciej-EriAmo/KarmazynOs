# MANIFEST KARMAZYN OS

System KarmazynOS integruje model ontologiczny z rygorystycznym modelem kryptograficznym Holographic Session Spaces (HSS v2.5.0). Bąble to nie tylko pliki wymiany – to hermetyczne piaskownice (Dynamic Holographic Task Memory Spaces).

Poniżej znajdują się fundamentalne zasady i filary konstytuujące system KarmazynOS.

## 1. Ontologia Przestrzeni (Atom vs Bąbel)

*   **Φ (Phi) i Atomy:** Pamięć robocza, przepływ, stan w czasie rzeczywistym. **Atomy NIE są używane jako trwała baza danych.** Są wskaźnikami, buforami, reprezentacją trwającego procesu. Żyją tak długo, jak długo utrzymują wysoką temperaturę (energię).
*   **Bąble (Holographic Task Memory Spaces):** Trwała jednostka pamięci ORAZ hermetyczna przestrzeń wykonawcza z kryptograficzną membraną. Stanowią granicę, poza którą proces nie może samodzielnie wyjść bez autoryzacji z zewnątrz.

## 2. Topologia Bezpieczeństwa (Model HSS v2.5.0)

Wdrożenie zasady: **Bezpieczeństwo to własność topologiczna przestrzeni wykonawczej, a nie zewnętrzna polityka ACL.**

*   **Mechanizm wyprowadzania kluczy agenta (KDF):**
    $$s_A = \text{KDF}(s_{\text{sess}}, \text{agent\_id}, \mathcal{P}_{\text{task}})$$
    Agent istnieje tylko i wyłącznie w przestrzeni określonej przez wyprowadzony dla niego klucz. Ten klucz hermetyzuje jego środowisko i ogranicza zakres jego percepcji oraz oddziaływania.
*   **Context Binding (AAD):** Gwarantuje, że agenci powoływani do życia i generowani wewnątrz Bąbli mają **absolutny zakaz modyfikacji rdzenia Φ** (Write-protection of Φ core). Powiązanie kontekstowe upewnia się, że nie powstaną nieautoryzowane powiązania do głównej matrycy.

## 3. Informacja pragnie być ideą, nie wartością (Hologramy)

*   Klasyczne bazy danych przechowują *wartości*. KarmazynOS przechowuje **idee**.
*   **Idea (Hologram)** nie jest pojedynczą, zamrożoną daną — jest ciągłą przestrzenią latentną, zdolną do generowania nieskończenie wielu instancji tego samego pojęcia.
*   Poprzez projekcję zapytania na tę n-wymiarową przestrzeń i celowe dodanie kontrolowanego szumu, system syntetyzuje nowe myśli, które *nie są* bezpośrednimi kopiami żadnych wcześniej zapisanych danych, a stają się wariacjami tej samej koncepcji.

## 4. Złota zasada "No-Plaintext-In-Kernel" i Termodynamika

*   **No-Plaintext-In-Kernel:** Jest to twardy, niepodważalny wymóg. Moduł LSM (Linux Security Module) wbudowany w jądro systemu pełni funkcję **wyłącznie upcall filter**. Cała zaawansowana kryptografia (np. mechanizm LPR) i weryfikacja wariancji odbywa się bezwzględnie w uprzywilejowanym demonie `hss-daemon` operującym w bezpiecznej przestrzeni użytkownika. W jądrze nie przetwarza się odszyfrowanych danych.
*   **Vacuum Decay:** Działa jako organiczny mechanizm usuwania anomalii entropii z systemu (powrót do bazowego szumu kryptograficznego $\sigma_\infty^2$).
*   **Time Freezing:** Zjawisko to naturalnie chroni uśpionych, nieaktywnych agentów przed parowaniem, dopóki nie zostaną ponownie wzbudzeni (przypomnieni) w systemie.
