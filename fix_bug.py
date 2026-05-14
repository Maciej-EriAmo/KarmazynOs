"""
fix_bugs.py — KarmazynOS patch applier
=======================================
Stosuje zdefiniowane poprawki do plików projektu.

Użycie:
    python fix_bugs.py            # zastosuj wszystkie poprawki
    python fix_bugs.py --dry-run  # tylko sprawdź, nie zapisuj
    python fix_bugs.py --check    # wyjdź z kodem 1 jeśli są niezałatane bugi

Każda poprawka to słownik z kluczami:
    file        – ścieżka względna od PROJECT_ROOT
    description – opis bugu
    search      – dokładny ciąg do zastąpienia (str lub bytes)
    replace     – ciąg zastępczy       (str lub bytes)

Logika apply:
    - Jeśli `search` NIE istnieje w pliku → sprawdź czy `replace` już istnieje
        - Tak  → "już załatane" (OK, idempotent)
        - Nie  → "wzorzec nieznaleziony" (WARN — plik mógł się zmienić)
    - Jeśli `search` istnieje → zastąp, zrób backup .bak_YYYYMMDD_HHMMSS
"""

import pathlib
import shutil
import sys
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).parent

# =====================================================================
# DEFINICJE POPRAWEK
# =====================================================================
# Każda pozycja: wstaw nową poprawkę jako kolejny słownik na liście.
# Kolejność ma znaczenie — poprawki aplikowane są od góry do dołu.

FIXES = [
    # ------------------------------------------------------------------
    # BUG-001  PhiSpace.embed — zdublowany backslash w raw stringu regex
    # ------------------------------------------------------------------
    # r"\\W+" w source to wzorzec \\W+ który pasuje do literalnego backslasha
    # po którym następują wielkie litery W. Tokenizer zwracał puste wyniki
    # dla każdego tekstu niezawierającego backslasha.
    # Poprawka: r"\W+" → wzorzec \W+ → dopasowuje znaki nie-słowne.
    #
    # UWAGA: w tym pliku poprawka zapisana jest jako zwykły string Python,
    # więc jeden backslash w literale stringa = jeden backslash w pliku.
    {
        "id":          "BUG-001",
        "file":        "runtime.py",
        "description": "PhiSpace.embed: r\"\\\\W+\" → r\"\\W+\" (zbędny backslash blokował tokenizację)",
        "search":      "re.split(r\"\\\\W+\", text.lower())",
        "replace":     "re.split(r\"\\W+\", text.lower())",
    },

    # ------------------------------------------------------------------
    # BUG-002  PhiSpace.embed — mylący komentarz sugerujący str.replace
    # ------------------------------------------------------------------
    # Komentarz mówił "Use simple string replace to avoid re template
    # escape issues" ale kod używał re.split. Komentarz był reliktem
    # po próbnym obejściu bugu-001 i nie opisywał rzeczywistego kodu.
    {
        "id":          "BUG-002",
        "file":        "runtime.py",
        "description": "PhiSpace.embed: usunięcie misleading comment o str.replace",
        "search":      "        # Use simple string replace to avoid re template escape issues in python re.sub\n",
        "replace":     "",
    },
]


# =====================================================================
# LOGIKA APPLY
# =====================================================================

def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")

def _write(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")

def _backup(path: pathlib.Path) -> pathlib.Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(f".py.bak_{ts}")
    shutil.copy2(path, bak)
    return bak


class PatchResult:
    APPLIED  = "applied"
    ALREADY  = "already_patched"
    MISSING  = "pattern_missing"
    NO_FILE  = "file_not_found"
    ERROR    = "error"


def apply_fix(fix: dict, dry_run: bool = False) -> tuple[str, str]:
    """
    Zwraca (PatchResult.*, detail_message).
    """
    path = PROJECT_ROOT / fix["file"]

    if not path.exists():
        return PatchResult.NO_FILE, f"plik nie istnieje: {path}"

    try:
        content = _read(path)
    except Exception as e:
        return PatchResult.ERROR, f"błąd odczytu: {e}"

    search  = fix["search"]
    replace = fix["replace"]

    if search not in content:
        # Wzorzec nie istnieje — czy poprawka jest już zastosowana?
        if replace and replace in content:
            return PatchResult.ALREADY, "poprawka już w pliku"
        # Pusty replace oznacza usunięcie — jeśli search nie istnieje, też OK
        if not replace:
            return PatchResult.ALREADY, "wzorzec do usunięcia już nieobecny"
        return PatchResult.MISSING, f"nie znaleziono: {search[:60]!r}"

    if dry_run:
        return PatchResult.APPLIED, "DRY RUN — nie zapisano"

    new_content = content.replace(search, replace, 1)
    try:
        bak = _backup(path)
        _write(path, new_content)
        return PatchResult.APPLIED, f"backup: {bak.name}"
    except Exception as e:
        return PatchResult.ERROR, f"błąd zapisu: {e}"


def run(dry_run: bool = False, check_only: bool = False) -> int:
    """
    Aplikuje wszystkie poprawki.
    Zwraca liczbę niezałatanych bugów (0 = wszystko OK).
    """
    unpatched = 0

    for fix in FIXES:
        fid  = fix["id"]
        desc = fix["description"]

        if check_only:
            path = PROJECT_ROOT / fix["file"]
            if path.exists() and fix["search"] in _read(path):
                print(f"[BUG]  {fid}: {desc}")
                unpatched += 1
            else:
                print(f"[OK]   {fid}: {desc}")
            continue

        result, detail = apply_fix(fix, dry_run=dry_run)

        if result == PatchResult.APPLIED:
            tag = "[DRY]" if dry_run else "[FIX]"
            print(f"{tag}  {fid}: {desc}")
            if detail:
                print(f"       → {detail}")
        elif result == PatchResult.ALREADY:
            print(f"[OK]   {fid}: już załatane")
        elif result == PatchResult.MISSING:
            print(f"[WARN] {fid}: {detail}")
            unpatched += 1
        elif result == PatchResult.NO_FILE:
            print(f"[SKIP] {fid}: {detail}")
        elif result == PatchResult.ERROR:
            print(f"[ERR]  {fid}: {detail}")
            unpatched += 1

    return unpatched


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    dry_run    = "--dry-run" in sys.argv or "--dry" in sys.argv
    check_only = "--check"   in sys.argv

    if dry_run:
        print("=== DRY RUN — pliki NIE zostaną zmodyfikowane ===\n")
    elif check_only:
        print("=== CHECK — weryfikacja bez zapisu ===\n")

    unpatched = run(dry_run=dry_run, check_only=check_only)

    print(f"\n{'='*48}")
    if check_only:
        print(f"Niezałatanych bugów: {unpatched}")
    else:
        label = "zasymulowano" if dry_run else "zastosowano"
        applied = len(FIXES) - unpatched
        print(f"Poprawek {label}: {applied}/{len(FIXES)}")

    sys.exit(1 if unpatched > 0 else 0)
