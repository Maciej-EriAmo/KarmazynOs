# 🎨 KarmazynOS Design Language — STC-Φ-001 v0.3

> **Kontrakt semantyczny systemu Φ-space.**
> Każdy kolor, dźwięk i animacja opisuje stan systemu, nigdy nie jest ozdobnikiem.

---

## 00 // Filozofia

| Zasada | Opis |
| :--- | :--- |
| **I. Kolor = Stan** | Czerwień → aktywność Φ. Cyjan → dane w ruchu. Zieleń → stabilność. Pomarańcz → ciepło. |
| **II. Ciemność = Głębia** | Warstwy tła (`void` → `bg` → `surface` → `raised`) opisują głębokość stosu pamięci. |
| **III. Decay jest widoczny** | Elementy zanikające — zanikają wizualnie. System nie ukrywa entropii. |
| **IV. Mono = Dane, Sans = UI** | Monospace → output, kod, dane. Sans-serif → interfejs, narracja. |

---

## 01 // Paleta barw

### Φ-Core — tożsamość i aktywność

| Token | Hex | Opis |
| :--- | :--- | :--- |
| `phi_core` | `#C8102E` | Bazowy karmazyn — tożsamość |
| `phi_bright` | `#FF1F45` | Aktywny / hover / focus |
| `phi_deep` | `#8B0000` | Wciśnięty / border akcentu |
| `phi_ember` | `#FF6B4A` | Ciepły akcent / alert niski |

### Entropy — tła, warstwy, głębia

| Token | Hex | Opis |
| :--- | :--- | :--- |
| `entropy_void` | `#080A0F` | Najgłębsze tło |
| `entropy_bg` | `#0E1118` | Tło aplikacji |
| `entropy_surface` | `#161B26` | Karty / panele |
| `entropy_raised` | `#1E2535` | Elevated / modal |
| `entropy_border` | `#2A3347` | Obramowania |

### Φ-Space — semantyczne stany systemu

| Token | Hex | Opis |
| :--- | :--- | :--- |
| `phi_signal` | `#00E5FF` | Dane live / output / stream |
| `phi_stable` | `#39FF14` | Stabilny / OK / verified |
| `phi_thermal` | `#FF9900` | Temperatura / ostrzeżenie |
| `phi_decay` | `#6B7FA3` | Zanikający / nieaktywny |
| `phi_ghost` | `#2E3D5C` | Widmo / vacuum |

---

## 02 // Typografia

| Rola | Font | Styl |
| :--- | :--- | :--- |
| **Display** | Rajdhani 700 | Nagłówki, nazwy |
| **Body** | Exo 2 (200) | Opisy, narracja |
| **Mono** | Share Tech Mono | Dane, kod, output |

---

## 03 // Komponenty bazowe

- **Przyciski**: Primary (`phi_core`), Ghost (`phi_signal`), Thermal (`phi_thermal`), Danger (`phi_deep`)
- **Wskaźniki stanu**: Kropki (`●`) — active, signal, thermal, decay, ghost
- **Pasek termalny**: Wypełnienie kolorem zależnym od T
- **Bąble Φ**: Chmurki semantyczne (phi, signal, stable, decay)

---

## 04 // Spacing & Grid

Bazowa jednostka: **8px**. Wszystkie odstępy są jej wielokrotnością.

| Nazwa | Wartość |
| :--- | :--- |
| micro | 4px (×0.5) |
| xs | 8px (×1) |
| sm | 16px (×2) |
| md | 24px (×3) |
| lg | 32px (×4) |
| xl | 48px (×6) |
| 2xl | 64px (×8) |

---

## 05 // Motion

| Token | Czas | Zastosowanie |
| :--- | :--- | :--- |
| `dur-fast` | 120ms | Hover, feedback |
| `dur-mid` | 280ms | Przejścia, panele |
| `dur-slow` | 500ms | Decay, konsolidacja |

Krzywa: `ease-phi` = `cubic-bezier(0.23, 1, 0.32, 1)`

---

## 06 // Światło / Cień (Mechanicum)

| Token | Opis |
| :--- | :--- |
| `glow-phi` | Poświata Φ — aktywne elementy |
| `glow-signal` | Poświata danych live |
| `glow-stable` | Poświata stabilnego stanu |
| `shadow-lift` | Uniesiony panel / karta |
| `rim-light` | Szczelina światła — górna krawędź |
| `rim-phi` | Sakralna krawędź elementów Φ |

---

## 07 // Tokeny audio

Każdy dźwięk jest proceduralny i odpowiada zdarzeniu systemowemu.

| Token audio | Zdarzenie | Charakter |
| :--- | :--- | :--- |
| `TICK` | Ubytek T | Trzask, wysokość ∝ T |
| `WARM_THRESHOLD` | Atom → WARM | Niski pomruk ~80 Hz |
| `VACUUM_DECAY` | T=0, rozpad | Głęboki gong + szum |
| `CORRUPTION` | Splamienie | Dysonans (1:√2:√3) |
| `MANDALA_HARMONY` | Udana Mandala | Wznoszące glissando kwintowe |
| `INCENSE` | Kadzidło | Delikatny szum |
| `ARCHIVE_SEAL` | Pieczęć Ring-LWE | Metaliczne kliknięcia |

---

## 08 // Mapowanie stanów systemu (STATE_MAP)

**Jedno źródło prawdy** dla percepcji stanu — używane przez UI, audio i logi.

```json
{
  "active":   {"color": "phi_stable", "sound": "tick", "dot": "active"},
  "thermal":  {"color": "phi_thermal", "sound": "tick", "dot": "thermal"},
  "decay":    {"color": "phi_decay", "sound": "vacuum_decay", "dot": "decay"},
  "corrupt":  {"color": "phi_bright", "sound": "corruption", "dot": "thermal"},
  "ghost":    {"color": "phi_ghost", "sound": null, "dot": "ghost"}
