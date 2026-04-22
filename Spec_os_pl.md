# KarmazynOS — Specyfikacja Fundamentów

**Maciej Mazur | Warsaw | 2026-04-17**
**Dokument inżynierski. Bez metafor — tylko struktury i operacje.**
**v0.6 — decyzje i poprawki względem v0.5:**
**  [1B] recall = hybrydowy: score = α×structural + (1-α)×semantic**
**       niestabilność po restarcie = filozoficznie spójna (historia somatyczna)**
**  [M1] root_key = HMAC(base_secret, atom.id) — stabilny, niezależny od epoki**
**       COLD = długoterminowe archiwum przez cały czas życia sesji Φ**
**  [Y]  Atom z content=None jako stan WARM — jedna struct, trzy stany**
**  [+]  FSM lifecycle atomu: CREATED→HOT→WARM→COLD→TOMB→GC**
**  [+]  MAX_ATOMS jako constraint-based bound (nie heurystyka)**
**  [+]  Trzy niezależne rytmy systemu bez wspólnego zegara (filozofia)**

---

## Część 1: Atom

### 1.1 Definicja

Atom jest **najmniejszą niepodzielną jednostką informacji** w KarmazynOS.
Nie można zapisać połowy atomu. Nie można odczytać części atomu.
Atom istnieje w całości albo nie istnieje.

```
struct Atom {
    id:           bytes[16]     # UUID v4, losowy przy tworzeniu
    content:      bytes[N_c]    # surowe dane; None w stanach WARM/COLD
    embedding:    float32[D]    # = embed_structural; znormalizowany |e|₂=1.0
    epoch_born:   uint64        # epoka stworzenia
    epoch_warm:   uint64        # epoka ostatniego recall
    base_delta_T: float64       # energia startowa ΔT
    session_id:   bytes[32]     # KDF(Φ², epoch) — epoka stworzenia (dla AAD)
    root_key:     bytes[32]     # HMAC(base_secret, b"atom-root:" || id)
    mac_meta:     bytes[32]     # HMAC(k_meta, id||embedding||epoch_born)
    mac_cipher:   bytes[32]     # HMAC(k_cipher, id||ciphertext) — przy write
}
```

`root_key = HMAC(base_secret, b"atom-root:" || atom.id)`

`base_secret` to stały korzeń sesji Φ — nie rotuje z epoką.
Atom stworzony w epoce `e` jest dostępny w każdej późniejszej epoce
tej samej sesji Φ, bo `base_secret` nie zmienia się.
COLD jest długoterminowym archiwum przez cały czas życia sesji Φ.

`session_id` (epokowy) pozostaje w struct tylko dla AAD binding pryzmatów —
wiąże ciphertext z konkretną epoką stworzenia. Nie jest używany do
wyprowadzania `root_key` ani kluczy MAC.

`embed_semantic` nie jest polem atomu. Trzymany jest w
**SemanticCache** — słowniku sesji poza strukturą atomu:

```python
# Poza atomem — w kontekście sesji
semantic_cache: dict[bytes, float32[D']]   # atom_id → embed_semantic
# Opcjonalne. Brak wpisu = używaj atom.embedding jako fallback.
# Znika przy restarcie — nie jest persystowany.
```

### 1.2 Embedding

#### embed_structural (= `atom.embedding`)

```
embed_structural: bytes → float32[D]
    kontrakt: ∀ content: embed_structural(content) jest stały zawsze
    |embed_structural(x)|₂ = 1.0   # znormalizowany — wymagane dla HRR
    implementacje: KuRz hash-based, MD5-based
    NIE może być modelem ML
```

Zamrożony na poziomie instancji systemu. Zmiana implementacji
= zniszczenie wszystkich istniejących hologramów.

#### embed_semantic (w SemanticCache)

```
embed_semantic: bytes → float32[D']
    kontrakt: deterministyczny w ramach sesji — nie globalnie
    D' może być ≠ D
    implementacje: dowolne, w tym modele ML (§1.2.1)
    NIE wchodzi do HRR trace
    używany tylko do cosine similarity przy recall
```

#### §1.2.1 Warunki dla modeli ML jako embed_semantic

Model ML może pełnić rolę embed_semantic jeśli spełnia:
- CPU inference (nie GPU — float drift)
- `torch.use_deterministic_algorithms(True)` lub odpowiednik
- fixed precision float32

Naruszenie = recall może zwracać błędne wyniki,
ale hologramy i HRR trace pozostają nienaruszone.

#### embed_structural — wchodzi do HRR trace

```
embed_structural: bytes → float32[D]
    # D = 64 (domyślnie), stały dla całej instancji systemu
    # kontrakt: ∀ content, ∀ t: embed_structural(content, t) == embed_structural(content)
    # implementacje: KuRz hash-based, MD5-based
    # NIE może być modelem ML — wymóg absolutnej deterministyczności
```

Jest to embedding **strukturalny** — wchodzi do HRR trace hologramu.
Zmiana implementacji = zniszczenie wszystkich istniejących hologramów.
Dlatego jest zamrożony na poziomie instancji systemu przy inicjalizacji.

Właściwości wymagane:
- `|embed_structural(x)|₂ = 1.0` — znormalizowany (wymagane dla HRR)
- `∀ x: embed_structural(x) == embed_structural(x)` — absolutna deterministyczność
- `cosine(a, b) ∈ [-1, 1]`

#### embed_semantic — używany tylko do recall

```
embed_semantic: bytes → float32[D']
    # D' może być różne od D
    # kontrakt: deterministyczny w ramach jednej sesji — nie musi być globalnie
    # implementacje: KuRz, hash-based, modele ML (z ograniczeniami §1.2.1)
    # NIE wchodzi do HRR trace
```

Jest to embedding **semantyczny** — używany tylko do cosine similarity
przy recall. Może być wymieniony bez wpływu na integralność hologramów.

#### §1.2.1 Warunki dla modeli ML jako embed_semantic

Model ML może pełnić rolę embed_semantic jeśli:
- CPU inference (nie GPU — float drift)
- `torch.use_deterministic_algorithms(True)` lub odpowiednik
- fixed precision float32
- brak batch-zależnych operacji (LayerNorm z batch statistics)

Naruszenie warunków = recall może zwracać błędne wyniki,
ale hologramy pozostają nienaruszone (embed_structural niezmieniony).

### 1.3 Temperatura

Temperatura to **liczba rzeczywista ≥ T_vacuum** opisująca
jak "żywy" jest atom w danej chwili.

```
T(atom, current_epoch) = T_vacuum + ΔT × exp(−λ × age)

gdzie:
    age   = current_epoch − atom.epoch_warm
    ΔT    = atom.base_delta_T    # energia nadana przy tworzeniu
    λ     = 0.1                  # stała zaniku (konfigurowalna)
    T_vacuum = measure_entropy(sample_rlwe(N=64)) # mierzona, nie stała
```

`T_vacuum` jest **mierzona przy starcie systemu**, nie zakodowana na stałe.
Jest jedyną wartością której system nie może zmienić.

Atom jest **żywy** gdy: `T(atom) > T_vacuum + ε` (ε = 0.05 × T_vacuum)
Atom jest **kandydatem vacuum** gdy: `T(atom) ≤ T_vacuum + ε`

### 1.4 Tożsamość sesyjna

```
session_id = HMAC-SHA256(base_secret, epoch.to_bytes(8, 'big'))

base_secret = HMAC-SHA256(CSPRNG(32), Φ².tobytes() + b"ksz-v1")
epoch       = floor(UTC_timestamp / 300)
```

`session_id` rotuje co 300 sekund.
Atom stworzony w epoce `e` ma `session_id` epoki `e`.
Aby go odczytać w epoce `e+k`, system musi mieć dostęp do `base_secret`
(z którego może re-derywować `session_id` epoki `e`).

### 1.5 MAC atomu — root_key i dwa derived keys

Każdy atom ma jeden `root_key` z którego wyprowadzane są dwa klucze MAC.
Jeden trust domain per atom, dwie domeny operacyjne.

```
root_key  = HMAC-SHA256(base_secret, b"atom-root:" || atom.id)

k_meta    = HMAC-SHA256(root_key, b"meta")
k_cipher  = HMAC-SHA256(root_key, b"cipher")
```

`root_key` jest przechowywany w struct Atom (patrz §1.1).
Oba klucze pochodne są obliczane na żądanie — nie są persystowane.

**mac_meta** — chroni integralność metadanych (index store WARM).
Weryfikowany **przed** odczytem z COLD. Nie zależy od `content`.

```
mac_meta = HMAC-SHA256(
    key  = k_meta,
    data = b"meta" || atom.id || atom.embedding.tobytes()
                    || atom.epoch_born.to_bytes(8)
)
```

**mac_cipher** — chroni integralność szyfrogramu (archive COLD).
Weryfikowany **po** odszyfrowaniu, przed użyciem `content`.

```
mac_cipher = HMAC-SHA256(
    key  = k_cipher,
    data = b"cipher" || atom.id || ciphertext_bytes
)
```

Kolejność weryfikacji przy odczycie:
1. Oblicz `k_meta = HMAC(root_key, b"meta")`
2. Sprawdź `mac_meta` — metadane nienaruszone?
3. Pobierz ciphertext z COLD przez `atom.id`
4. Oblicz `k_cipher = HMAC(root_key, b"cipher")`
5. Sprawdź `mac_cipher` — ciphertext nienaruszony?
6. Odszyfruj → `content`

Niezgodność `mac_meta`   → atom traktowany jak vacuum.
Niezgodność `mac_cipher` → IntegrityError, nie vacuum.

---

## Część 2: Mocowanie atomu w pamięci

### 2.1 Trzy warstwy — definicja i role

```
HOT   active store   — RAM, atom z content (plaintext)
WARM  index store    — RAM/plik, atom bez content (metadane + embedding)
COLD  archive store  — dysk, zaszyfrowany content (ciphertext)
```

**Niezmiennik single source of truth:**
Atom istnieje w **dokładnie jednej** warstwie jako autorytatywna kopia.

```
atom.content != None  →  atom jest w HOT (autorytatywny)
atom.content == None  →  atom jest w WARM (index), content w COLD
```

Atom nie może być jednocześnie autorytatywny w HOT i WARM.
Awans WARM→HOT (przez `cold_decrypt`) przenosi autorytet do HOT
i usuwa wpis z WARM (lub oznacza jako stale).

WARM jest **indeksem** — wskazuje na COLD przez `atom.id`.
WARM nie zawiera ciphertext. WARM nie daje dostępu do COLD.
Dostęp do COLD wymaga: `atom.id` z WARM + `session_id` sesji.

### 2.2 Warstwa HOT

Python dict: `hot_store: dict[bytes, Atom]` (klucz = `atom.id`)

Cechy:
- Dostęp O(1)
- Zawiera `content` jako plaintext
- Znika przy restarcie (brak persystencji)
- Limit: konfigurowalny (domyślnie 256 atomów)

Eviction policy: LRU + temperatura — przy przepełnieniu
usuwany jest atom o najniższej `T(atom, current_epoch)`.

### 2.3 Warstwa WARM

Serializowane do `phi_state.json` przy `save()` i przy wyjściu.

```python
# Schemat JSON dla jednego atomu w warstwie WARM
{
    "id":           "hex string 32 chars",
    "embedding":    [float, ...],         # lista D floatów (embed_structural)
    "base_delta_T": float,
    "epoch_born":   int,
    "epoch_warm":   int,
    "session_id":   "hex string 64 chars",  # epoka stworzenia (dla AAD)
    "root_key":     "hex string 64 chars",  # HMAC(base_secret, id) — stały
    "mac_meta":     "hex string 64 chars",  # jedyny MAC w WARM
    # mac_cipher: NIEOBECNY — należy do COLD (przy ciphertexcie)
    # content:    NIEOBECNY — plaintext nie jest persystowany
}
```

`content` **nie ma** w warstwie WARM.
`mac_cipher` **nie ma** w warstwie WARM — weryfikowany dopiero po
odczycie ciphertextu z COLD.
Przy wczytaniu: atom odtwarzany z metadanych, `content` dostępny
tylko przez deszyfrowanie z warstwy COLD (wymaga `root_key`).

### 2.4 Warstwa COLD

Zaszyfrowane bloki na dysku — patrz §3 (format dyskowy).

Połączenie WARM↔COLD przez `atom.id`:
- WARM trzyma metadane + embedding
- COLD trzyma zaszyfrowany content
- Klucz łączący: `atom.id`

### 2.5 Recall — hybrydowy dostęp do atomu

Recall używa **ważonej sumy** embeddingów strukturalnego i semantycznego.

```
ALPHA = 0.3    # waga embed_structural (konfigurowalna, 0.0-1.0)
               # 0.0 = czysto semantyczny, 1.0 = czysto strukturalny
               # domyślnie 0.3: semantic dominuje, structural jako kotwica

score(atom, query) = (ALPHA * cosine(q_struct, atom.embedding)
                   + (1-ALPHA) * cosine(q_semantic, semantic_cache.get(atom.id,
                                                     atom.embedding))
                   ) * T(atom, current_epoch)
```

Gdy `semantic_cache` nie ma wpisu dla atomu — fallback na `atom.embedding`.
Skutek po restarcie (gdy cache znika): ranking przesuwa się w stronę
embeddingów strukturalnych. To jest zamierzone — system "ostygły" po
restarcie ma inne priorytety. Spójne z filozofią historii somatycznej.

```python
def recall(query: str, k: int = 3,
           alpha: float = ALPHA) -> list[Atom]:

    q_struct   = embed_structural(query)
    q_semantic = embed_semantic(query)     # None jeśli brak implementacji

    candidates = []

    for store in (hot_store, warm_store):
        for atom_id, atom in store.items():
            if store is warm_store and atom_id in hot_store:
                continue   # nie duplikuj

            # Embedding strukturalny (zawsze dostępny)
            sim_s = cosine(q_struct, atom.embedding)

            # Embedding semantyczny (z cache lub fallback)
            if q_semantic is not None:
                sem_emb = semantic_cache.get(atom_id, atom.embedding)
                sim_m   = cosine(q_semantic, sem_emb)
            else:
                sim_m = sim_s   # brak semantic = użyj structural dla obu

            sim   = alpha * sim_s + (1 - alpha) * sim_m
            T     = atom.temperature(T_vac, current_epoch)
            candidates.append((sim * T, atom))

    if not candidates:
        return []

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:k]

    for _, atom in top:
        heat(atom)
        if atom.content is None:
            atom.content = cold_decrypt(atom.id, atom.root_key)
            hot_store[atom.id] = atom
            warm_store.pop(atom.id, None)   # przenieś autorytet do HOT

    return [atom for _, atom in top]


def heat(atom: Atom):
    """Częściowe ogrzewanie — nie do maksimum od razu."""
    T_current = atom.temperature(T_vac, current_epoch)
    T_max     = T_vac + atom.base_delta_T
    T_new     = T_current + ALPHA_HEAT * (T_max - T_current)
    # Przelicz epoch_warm z nowej temperatury
    atom.epoch_warm = current_epoch - int(
        -log(max((T_new - T_vac) / atom.base_delta_T, 1e-9)) / LAMBDA
    )
```

### 2.6 Vacuum Decay — usuwanie atomu

Vacuum decay usuwa atom ze wszystkich warstw z jawną semantyką
dla każdej z nich.

```python
def vacuum_decay():
    to_remove = []

    # Skanuj HOT (autorytatywne źródło temperatury)
    for atom_id, atom in hot_store.items():
        T = atom.temperature(T_vac, current_epoch)
        if T <= T_vac + EPSILON_FEP:
            to_remove.append(atom_id)

    for atom_id in to_remove:
        # HOT: usuń natychmiast — content znika z RAM
        hot_store.pop(atom_id, None)

        # WARM: usuń wpis indeksu
        warm_store.pop(atom_id, None)

        # COLD: zapisz tombstone — nie kasuj bajtów
        cold_store.write_tombstone(atom_id)
        # Tombstone = plik <atom_id>.tomb w katalogu COLD
        # Zawiera: atom_id + epoch_decay + HMAC(session_id, atom_id||"tomb")
        # Semantyka: ciphertext istnieje, ale session_id dla niego
        # jest skasowany → dane są termodynamicznie niedostępne.
        # Tombstone pozwala na audyt (kiedy atom został zdegradowany)
        # i na GC (fizyczne usunięcie pliku .ksz po retencji).

# Lifecycle COLD:
# .ksz  — aktywny atom (ciphertext czytelny przy poprawnym session_id)
# .tomb — atom po vacuum_decay (ciphertext istnieje, niedostępny)
# brak  — atom fizycznie usunięty przez GC po retencji (domyślnie 7 epok)
```

---

## Część 3: Format dyskowy

### 3.1 Zasada

**Jeden plik dyskowy = jeden zaszyfrowany blok = N pryzmatów.**

Pryzmat to **jednostka szyfrowania** — nie atom.
Jeden atom może być rozbity na wiele pryzmatów.
Wiele atomów może być połączonych w jeden hologram (patrz §4).

### 3.2 Plik dyskowy — nagłówek

```
PLIK KSZ (KarmazynOS Zaszyfrowany)
Rozszerzenie: .ksz

Offset  Rozmiar  Pole
0       4        Magic: b"KSZ\x01"
4       1        Wersja formatu: 0x01
5       1        Liczba pryzmatów: uint8 (1-255)
6       2        Zarezerwowane: 0x0000
8       32       Fingerprint sesji: HMAC-SHA256(session_id, b"ksz-fp")
40      8        Epoch stworzenia: uint64 little-endian
48      16       Atom ID: UUID bytes
64      32       MAC nagłówka: HMAC-SHA256(k_store, bajty[0:64])
                 # k_store = HMAC(atom.root_key, b"cold:store")
── (96 bajtów razem) ──
```

### 3.3 Pryzmat — jednostka w pliku

Po nagłówku: N pryzmatów jeden za drugim.

```
PRYZMAT
Offset  Rozmiar  Pole
0       1        Prism ID: uint8 (0=CORE, 1=IN, 2=OUT, 3-255=rozszerzenia)
1       2        Długość danych zaszyfrowanych: uint16 little-endian
3       16       Nonce: losowe bajty (różne dla każdego pryzmatu)
19      40       AAD: SHA256(atom_id || prism_id || nonce || sess_fp || epoch_bytes)
59      32       MAC_phi: HMAC-SHA256(k_mac_phi, u||v||aad||nonce)
91      N*2      u: wielomian R_q, N współczynników uint16 little-endian
91+N*2  N*2      v: wielomian R_q, N współczynników uint16 little-endian
── (91 + 2*N*2 bajtów = 91 + 256 bajtów dla N=64 = 347 bajtów) ──
```

`sess_fp    = HMAC-SHA256(session_id, b"ksz-fp")[:8]` — 8 bajtów
`epoch_bytes = epoch.to_bytes(8, 'big')`

AAD wiąże pryzmat z konkretną sesją i epoką.
Replay pryzmatem z innej sesji lub epoki → AAD mismatch → IntegrityError.

Łączny rozmiar jednego pryzmatu dla N=64: **347 bajtów**.
Łączny rozmiar pliku z 3 pryzmatami: 96 + 3×347 = **1137 bajtów**.

### 3.4 Trzy standardowe pryzmaty

```
PRISM_CORE (id=0)  — treść semantyczna atomu (główne dane)
PRISM_IN   (id=1)  — kontekst wejściowy (metadane, skąd przyszedł)
PRISM_OUT  (id=2)  — interfejs wyjściowy (jak był użyty, hash odpowiedzi)
```

Każdy pryzmat jest niezależnie zaszyfrowany.
Agent z capability tylko na PRISM_OUT widzi tylko pryzmat OUT.
Pryzmaty CORE i IN są dla niego szumem — matematycznie.

### 3.5 Szyfrowanie pryzmatu (LPR Ring-LWE)

**Parametry kryptosystemu LPR:**
Pełna specyfikacja w HSS Paper v2.6.0 §2.1 (DOI: 10.5281/zenodo.19548693).
Parametry operacyjne: N=64, Q=3329, η=2 (centered binomial distribution).
Warunek poprawności deszyfrowania: `B_e(B_r + B_s + 1) < Q/4`.
Dla N=64, Q=3329, B_e=B_r=B_s=2: `2×5=10 ≪ 832=Q/4` ✓

**KDF dla warstwy COLD** — klucze wyprowadzane z `atom.root_key`:

```
# Klucz publiczny LPR (deterministyczny — ten sam content → ten sam klucz pub)
k_pub_seed = HMAC-SHA256(atom.root_key, b"cold:pub")

# Klucz MAC szyfrogramu (taki sam jak k_cipher w §1.5)
k_cipher   = HMAC-SHA256(atom.root_key, b"cipher")

# Klucz MAC storage (dla warstwy pryzmatów)
k_store    = HMAC-SHA256(atom.root_key, b"cold:store")
```

Wszystkie klucze COLD wyprowadzane z `atom.root_key`, nie z `session_id`
bezpośrednio — spójność z modelem MAC z §1.5.

```python
def encrypt_prism(content_bits: ndarray[N], atom: Atom,
                  prism_id: int, epoch: int) -> Prism:
    k_pub_seed = HMAC(atom.root_key, b"cold:pub")
    k_store    = HMAC(atom.root_key, b"cold:store")
    sess_fp    = HMAC(atom.session_id, b"ksz-fp")[:8]
    epoch_b    = epoch.to_bytes(8, 'big')

    a, b = keygen_pub(seed=k_pub_seed)   # deterministyczny klucz pub
    r    = sample_small(N)               # efemeryczny, losowy
    e1   = sample_small(N)
    e2   = sample_small(N)
    u    = (poly_mul(a, r) + e1) % Q
    v    = (poly_mul(b, r) + e2 + (Q//2) * content_bits) % Q

    nonce = os.urandom(16)
    aad   = SHA256(atom.id + prism_id.to_bytes(1) + nonce + sess_fp + epoch_b)
    mac   = HMAC(k_store, u.tobytes() + v.tobytes() + aad + nonce)

    return Prism(id=prism_id, nonce=nonce, aad=aad, mac=mac, u=u, v=v)


def decrypt_prism(prism: Prism, atom: Atom, epoch: int) -> ndarray[N]:
    k_store = HMAC(atom.root_key, b"cold:store")
    k_pub_seed = HMAC(atom.root_key, b"cold:pub")
    sess_fp = HMAC(atom.session_id, b"ksz-fp")[:8]
    epoch_b = epoch.to_bytes(8, 'big')

    # Weryfikacja MAC storage
    expected_mac = HMAC(k_store,
        prism.u.tobytes() + prism.v.tobytes() + prism.aad + prism.nonce)
    if not compare_digest(prism.mac, expected_mac):
        raise IntegrityError("MAC mismatch")

    # Weryfikacja AAD (session + epoch binding)
    expected_aad = SHA256(
        atom.id + prism.id.to_bytes(1) + prism.nonce + sess_fp + epoch_b)
    if prism.aad != expected_aad:
        raise IntegrityError("AAD mismatch — zły kontekst lub replay")

    # Deszyfrowanie: klucz tajny = s_sess z root_key (spójny z encrypt)
    s_sess = KDF(atom.root_key, b"cold:pub")   # ten sam seed → ten sam s
    a, _   = keygen_pub(seed=k_pub_seed)        # odtwórz a deterministycznie
    # Decoding LPR: v - s*u, zaokrąglenie do {0,1}
    raw  = (prism.v - poly_mul(s_sess, prism.u)) % Q
    bits = ((raw + Q//4) // (Q//2)) % 2
    return bits
```

---

## Część 4: Hologram — agregat atomów

### 4.1 Czym jest hologram w KarmazynOS

Hologram to **struktura nośna danych** — nie indeks pomocniczy.
HRR trace jest jedynym sposobem na asocjatywny dostęp do atomów hologramu.
Uszkodzenie trace = niemożność odczytu bez skanowania pełnej listy `atom_ids`.

Właściwości:
- Zawiera od 1 do `MAX_ATOMS` atomów (patrz §4.1.1)
- Ma własne ID (`hologram_id`)
- `hrr_trace` używa wyłącznie `embed_structural` — absolutna deterministyczność
- Asocjatywny dostęp przez splot odwrotny (patrz §4.3)
- Graceful degradation: każdy dodany atom obniża SNR odczytu pozostałych

#### §4.1.1 Limit pojemności hologramu i niezmienniki stabilności

HRR trace jest superpozycją N wektorów w przestrzeni D-wymiarowej.

**Niezmiennik normy** (obowiązkowy):
```
∀ t: |hrr_trace|₂ = 1.0
```
Renormalizacja po każdym splocie. Naruszenie = trace zdegenerowany.

**Orthogonality bound** (heurystyczny):
Przy n atomach z losowymi embeddingami w R^D, oczekiwane SNR przy
asocjatywnym odczycie jednego atomu:

```
SNR(n, D) ≈ 1 / sqrt(n - 1)     # dla embeddingów quasi-ortogonalnych

Próg separowalności: SNR > SNR_min = 0.5  (konfigurowalne)
Maksymalna pojemność: n_max = 1 + 1/SNR_min² = 1 + 4 = 5  (dla SNR_min=0.5)
```

Konservatywny limit operacyjny (z marginesem bezpieczeństwa 3×):
```
MAX_ATOMS = floor(D / 12)    # SNR > 1.0 z prawdopodobieństwem > 0.95

Dla D=64:   MAX_ATOMS = 5
Dla D=128:  MAX_ATOMS = 10
Dla D=256:  MAX_ATOMS = 21
```

Uwaga: D/4 z v0.4 był zbyt optymistyczny. D/12 daje gwarancję
praktycznej separowalności przy embeddingach z rozkładu normalnego.

Przekroczenie `MAX_ATOMS`: system odmawia dodania atomu do hologramu.
Nie jest to błąd twardy — hologram pozostaje ważny, ale pełny.

### 4.2 Struktura hologramu

```
struct Hologram {
    id:          bytes[16]       # UUID hologramu
    atom_ids:    list[bytes[16]] # lista ID atomów wchodzących w skład
    hrr_trace:   float32[D]      # splot HRR embed_structural wszystkich atomów
    atom_count:  uint16          # bieżąca liczba atomów
    max_atoms:   uint16          # MAX_ATOMS dla tego hologramu
    created:     uint64          # epoka stworzenia
    root_key:    bytes[32]       # HMAC(base_secret, b"holo-root:" || id)
    mac:         bytes[32]       # HMAC(root_key, id||hrr_trace||atom_count)
}
```

`hologram.root_key = HMAC(base_secret, b"holo-root:" || hologram.id)`

Analogicznie do atomu — stabilny przez całe życie sesji Φ, niezależny
od rotacji epoki. MAC hologramu weryfikowalny w każdej epoce.

`hrr_trace` budowany z `embed_structural` — renormalizacja po każdym kroku:

```python
def build_hrr_trace(atoms: list[Atom]) -> ndarray[D]:
    """
    Buduje HRR trace. Używa embed_structural — nie embed_semantic.
    Renormalizacja po każdym kroku zapobiega dryfowi normy.
    Niezmiennik: |trace|₂ = 1.0 zawsze.
    """
    assert len(atoms) <= MAX_ATOMS_FOR_D[D], "Przekroczono MAX_ATOMS"
    trace = zeros(D)
    trace[0] = 1.0                          # element neutralny splotu
    for atom in atoms:
        emb = atom.embedding                # embed_structural — NIE semantic cache
        assert abs(norm(emb) - 1.0) < 1e-6, "embed_structural musi być znormalizowany"
        trace = ifft(fft(trace) * fft(emb)).real
        n = norm(trace)
        assert n > 1e-8, "Dryf normy — trace zdegenerowany"
        trace = trace / n                   # renormalizacja obowiązkowa
    return trace


def add_atom_to_hologram(hologram: Hologram, atom: Atom) -> bool:
    """Zwraca False jeśli hologram pełny."""
    if hologram.atom_count >= hologram.max_atoms:
        return False
    emb = atom.embedding   # = embed_structural — jedyne pole embeddingu w atomie
    hologram.hrr_trace = ifft(
        fft(hologram.hrr_trace) * fft(emb)
    ).real
    n = norm(hologram.hrr_trace)
    hologram.hrr_trace = hologram.hrr_trace / n  # renormalizacja
    hologram.atom_ids.append(atom.id)
    hologram.atom_count += 1
    hologram.mac = recompute_mac(hologram)
    return True
```

### 4.3 Asocjatywny dostęp przez splot odwrotny

Znając `hrr_trace` hologramu i `embed_structural` jednego atomu,
można odzyskać przybliżony `embed_structural` atomu powiązanego:

```python
def query_hologram(trace: ndarray[D], query_emb: ndarray[D]) -> ndarray[D]:
    """
    Zwraca przybliżony embed_structural atomu pasującego do query.
    Nie jest to dokładny odczyt — to korelacja (heurystyka asocjacyjna).
    Wynik należy porównać z embed_structural atomów w atom_ids.
    """
    assert abs(norm(query_emb) - 1.0) < 1e-6
    approx = ifft(fft(trace) * conj(fft(query_emb))).real
    n = norm(approx)
    if n < 1e-8:
        return None   # brak korelacji
    return approx / n


def find_atom_in_hologram(hologram: Hologram,
                           query: str,
                           warm_store: dict) -> Atom | None:
    """
    Pełny asocjatywny odczyt:
    1. Oblicz przybliżony embedding przez splot odwrotny
    2. Porównaj z embed_structural atomów z atom_ids w WARM
    3. Zwróć najlepiej pasujący
    COLD nie jest odpytywany — dostęp tylko przez WARM.
    """
    q_emb = embed_structural(query)
    approx = query_hologram(hologram.hrr_trace, q_emb)
    if approx is None:
        return None

    best, best_sim = None, 0.0
    for atom_id in hologram.atom_ids:
        atom = warm_store.get(atom_id)
        if atom is None:
            continue
        sim = cosine(approx, atom.embedding)
        if sim > best_sim:
            best_sim, best = sim, atom

    return best if best_sim > 0.5 else None

```

### 4.4 Format dyskowy hologramu i COLD jako archiwum

COLD jest **archiwum** — dostęp tylko przez WARM.
Nie można odpytywać COLD bezpośrednio.
Schemat dostępu jest zawsze: HOT → WARM → COLD (nigdy COLD bezpośrednio).

```
Dostęp do atomu:
  1. Szukaj w HOT (dict, O(1))
  2. Szukaj w WARM (embed_structural dostępny, content=None)
  3. Jeśli znaleziono w WARM → cold_decrypt(atom_id) → awansuj do HOT
  4. COLD nigdy nie jest skanowany bez atom_id z WARM
```

Plik `.kszh` (KarmazynOS Hologram):

```
Offset  Rozmiar  Pole
0       4        Magic: b"KSZH"
4       1        Wersja: 0x01
5       3        Liczba atomów: uint24 little-endian (max 16M)
8       16       Hologram ID: UUID bytes
24      32       Session fingerprint
56      8        Epoch created
64      D*4      HRR trace: float32[D]  (dla D=64: 256 bajtów)
64+D*4  32       MAC nagłówka
── następuje lista plików .ksz ──
── lub lista atom_id jeśli atomy przechowywane osobno ──
```

Po nagłówku: lista `(atom_id: bytes[16], offset: uint64)` — gdzie
szukać każdego atomu w plikach .ksz lub w strumieniu.

### 4.5 Dwa tryby przechowywania hologramu

**Tryb INLINE** — wszystkie atomy w jednym pliku .kszh:
```
nagłówek hologramu
atom_0.ksz (inline, bez oddzielnego pliku)
atom_1.ksz
...
atom_n.ksz
```

Zaleta: jeden plik do przeniesienia.
Wada: nie można odczytać jednego atomu bez parsowania całości.

**Tryb SPLIT** — hologram jako indeks, atomy jako osobne pliki:
```
hologram.kszh  (nagłówek + lista atom_id + offsety)
atoms/
    <atom_id_0>.ksz
    <atom_id_1>.ksz
    ...
```

Zaleta: O(1) dostęp do dowolnego atomu.
Wada: wiele plików.

Domyślny tryb: SPLIT dla hologramów > 8 atomów, INLINE dla ≤ 8.

---

## Część 5: Operacje podstawowe

### 5.1 Kompletna lista operacji na atomach

```python
# ZAPIS
atom_id = write(content: bytes, prism_set=["CORE","IN","OUT"]) -> bytes[16]
# Tworzy atom, szyfruje, zapisuje .ksz, zwraca ID

# ODCZYT
atom = read(atom_id: bytes[16], session_id: bytes[32]) -> Atom | None
# Deszyfruje atom z dysku jeśli MAC OK i session_id pasuje

# WYSZUKIWANIE
atoms = recall(query: str, k=3) -> list[Atom]
# Wyszukuje przez cosine similarity × temperatura

# OGRZEWANIE
heat(atom: Atom) -> None
# Przesuwa epoch_warm do przodu → temperatura rośnie

# KROK EPOKI
step_epoch() -> None
# current_epoch += 1, vacuum_decay(), apply_interactions()

# USUWANIE (termodynamiczne)
vacuum_decay() -> int
# Usuwa atomy poniżej progu, zwraca liczbę usuniętych
# Pliki .ksz pozostają na dysku jako szum — session_id nie istnieje

# TWORZENIE HOLOGRAMU
holo_id = create_hologram(atom_ids: list[bytes[16]]) -> bytes[16]

# ZAPIS HOLOGRAMU
write_hologram(holo_id: bytes[16], path: str, mode="SPLIT") -> None

# ODCZYT HOLOGRAMU
atoms = read_hologram(path: str, session_id: bytes[32]) -> list[Atom]

# ZAPYTANIE ASOCJATYWNE
approx = query_hologram(holo_id: bytes[16], query: str) -> Atom | None
```

### 5.2 Capability — kto co może odczytać

```python
# Wyprowadzenie klucza agenta
s_agent = KDF(
    session_id,
    JSON({"task": task_id, "prisms": sorted(allowed_prisms)})
)

# Weryfikacja capability
def has_capability(s_agent: bytes, prism_id: str, allowed_prisms: list) -> bool:
    return prism_id in set(allowed_prisms)   # set, nie substring

# Re-szyfrowanie dla agenta
def transfer_prism(prism: Prism, s_phi: bytes, s_agent: bytes) -> Prism:
    content = decrypt_prism(prism, s_phi)
    return encrypt_prism(content, s_agent, ...)
```

---

## Część 6: Niezmienniki i FSM lifecycle atomu

### 6.1 FSM lifecycle atomu

Atom przechodzi przez dokładnie zdefiniowane stany:

```
CREATED ──→ HOT ──→ WARM ──→ COLD ──→ TOMB ──→ GC
              ↑       │        │
              └───────┘        │ (cold_decrypt + awans)
              (recall)
```

| Stan | content | embedding | root_key | plik .ksz | dostępny |
|---|---|---|---|---|---|
| HOT  | plaintext | tak | tak | nie | tak |
| WARM | None | tak | tak | nie | recall |
| COLD | ciphertext | nie* | nie* | tak | przez WARM |
| TOMB | ciphertext | nie* | nie* | .tomb | nie |
| GC   | usunięty | — | — | brak | nie |

*embedding i root_key atomu w stanie COLD są dostępne przez WARM index.

**Przejścia dozwolone:**
- `HOT → WARM`: eviction (LRU + temperatura), zawsze dozwolone
- `WARM → HOT`: recall z cold_decrypt, wymaga `root_key`
- `HOT/WARM → TOMB`: vacuum_decay (T ≤ T_vac + ε)
- `COLD → TOMB`: jednoczesne z HOT/WARM → TOMB
- `TOMB → GC`: po retencji (domyślnie 7 epok)

**Przejścia niedozwolone:**
- `TOMB → HOT/WARM`: brak recovery po vacuum
- `COLD → HOT` bez przejścia przez WARM: COLD nie jest odpytywany bezpośrednio

### 6.2 Trzy niezależne rytmy systemu

KarmazynOS operuje na trzech niezależnych zegarach semantycznych
bez wspólnego zegara globalnego. To jest cecha architektury, nie brak.

```
Rytm kryptograficzny:  epoch = floor(UTC / 300)
    — rotacja session_id, forward secrecy
    — granulacja: 300 sekund

Rytm termodynamiczny:  T(atom) = T_vac + ΔT × exp(−λ × age_in_epochs)
    — decay naturalny, vacuum_decay
    — granulacja: kroki epoch (konfigurowane przez użytkownika)

Rytm semantyczny:      score = (α×structural + (1-α)×semantic) × T(atom)
    — recall, heat, interaction
    — granulacja: każde zapytanie
```

Atom może być jednocześnie:
- ważny kryptograficznie (root_key dostępny, MAC OK)
- martwy termodynamicznie (T ≤ T_vac + ε → vacuum_decay)
- aktywny semantycznie (wysoki score w recall tego kroku)

Brak globalnego arbitrażu między rytmami = brak single point of failure
semantyki. Każdy rytm jest niezależnie konfigurowalny.

### 6.3 Siedem niezmienników systemu

```
1. INTEGRALNOŚĆ
   ∀ atom w HOT/WARM: verify_mac_meta(atom) przed każdym użyciem
   ∀ atom wczytany z COLD: verify_mac_cipher(atom) przed użyciem content

2. STABILNOŚĆ ROOT_KEY
   atom.root_key = HMAC(base_secret, b"atom-root:" || atom.id)
   base_secret nie rotuje — atom dostępny przez całe życie sesji Φ

3. VACUUM FLOOR
   ∀ atom żywy: T(atom) > T_vacuum
   T_vacuum mierzone przy starcie, nie zakodowane

4. DETERMINISTYCZNOŚĆ EMBED_STRUCTURAL
   ∀ content: embed_structural(content) == embed_structural(content) zawsze
   Zmiana implementacji embed_structural = migracja wszystkich hologramów

5. MONOTONICZNOŚĆ EPOKI
   epoch nigdy się nie cofa
   vacuum_decay nie cofa epoch_warm (tylko zeruje)

6. ATOMOWOŚĆ ZAPISU
   write() atomowe: albo cały atom na dysk, albo nic
   partial write = jak brak zapisu

7. AAD BINDING
   ciphertext stworzony dla atom_id_A nieczytelny jako atom_id_B
   AAD zawiera atom_id + sess_fp + epoch_born
```

### 6.4 MAX_ATOMS — constraint-based bound

Zamiast stałej heurystyki, MAX_ATOMS wyznaczany z warunku SNR:

```python
def max_atoms_for_dim(D: int, snr_threshold: float = 1.0) -> int:
    """
    Maksymalna liczba atomów przy której E[SNR] > snr_threshold.
    Wynika z teorii HRR: przy n quasi-ortogonalnych wektorach w R^D
    SNR ≈ sqrt(D / (n-1)).
    Odwrócenie: n_max = 1 + D / snr_threshold²
    Z marginesem bezpieczeństwa 3×: n_max = 1 + D / (3 × snr_threshold²)
    """
    return max(1, int(1 + D / (3 * snr_threshold ** 2)))

# Przykłady dla snr_threshold=1.0:
# D=64:   max_atoms = 1 + 64/3 ≈ 22  (konserwatywnie: 21)
# D=128:  max_atoms = 1 + 128/3 ≈ 44
# D=256:  max_atoms = 1 + 256/3 ≈ 86
```

System oblicza MAX_ATOMS przy inicjalizacji hologramu na podstawie D
i konfigurowalnego `snr_threshold`. Nie jest to stała w kodzie.

---

## Część 7: Co dalej — jak budować wyższe struktury

Na tym fundamencie można budować:

**Drzewo capability** — hologram rodzica zawiera hologramy dzieci,
każde dziecko ma `s_agent = KDF(base_secret, policy || child_id)`.
Uprawnienia przepływają z góry na dół, nigdy odwrotnie.

**Graf asocjacyjny** — atomy połączone przez HRR trace.
Zapytanie do jednego atomu może propagować przez graf
do semantycznie powiązanych atomów.

**Sesja agenta** — hologram z TTL.
Po zakończeniu zadania `vacuum_decay()` czyści automatycznie.
Agent nie może zapisać poza własnym hologramem.

**Indeks semantyczny** — HRR trace hologramu jako skrót
całej zawartości. Wyszukiwanie O(1) zamiast O(n).

**Konfiguracja** — atom z `prism_id=CORE` tylko do odczytu,
`prism_id=IN` dostępny dla agentów konfiguracyjnych,
`prism_id=OUT` publiczny fingerprint.

---

*KarmazynOS Spec v0.6 — Maciej Mazur*
*To jest specyfikacja strukturalna, nie implementacja.*
*Implementacja referencyjna: hss_demo.py v2.9 + holonos_integrated.py*
*HSS Paper: DOI 10.5281/zenodo.19548693*
