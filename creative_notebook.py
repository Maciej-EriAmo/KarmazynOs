# creative_notebook.py
from karmazyn import KarmazynOS
import sys

def main():
    k = KarmazynOS()
    print("\n=== Kreatywny Notatnik (oparty na KarmazynOS v0.9) ===")
    print("Komendy: add <tekst> | recall <zapytanie> | idea <temat> | gen <temat> <prompt> | exit\n")

    while True:
        try:
            cmd = input("> ").strip()
        except EOFError:
            break
        if not cmd: continue
        parts = cmd.split(maxsplit=1)
        if parts[0] == "exit": break
        elif parts[0] == "add" and len(parts) > 1:
            label = k.write(parts[1])
            print(f"  Zapisano jako: {label}")
        elif parts[0] == "recall" and len(parts) > 1:
            res = k.recall(parts[1], k=3)
            for i, r in enumerate(res):
                print(f"  {i+1}. [{r['layer']}] {r['label'][:40]} (score={r['score']:.3f})")
        elif parts[0] == "idea" and len(parts) > 1:
            # tworzy hologram z ostatnich 5 bąbli pasujących do tematu (uproszczone)
            topic = parts[1]
            active = k.bubbles.all_active
            if active:
                labels = [b.label for b in active[:5]]
                hid = k.archive_bubbles_to_hologram(topic, labels)
                if hid: print(f"  Utworzono ideę: {hid}")
                else: print("  Nie udało się utworzyć idei.")
            else:
                print("  Brak bąbli do archiwizacji.")
        elif parts[0] == "gen" and len(parts) > 1:
            # generate from idea
            args = parts[1].split(maxsplit=1)
            if len(args) < 2:
                print("  Użycie: gen <hologram_id> <prompt>")
                continue
            hid, prompt = args
            vectors = k.recall_from_hologram(hid, prompt, temperature=0.4, k=1)
            if vectors:
                print(f"  Wygenerowano wektor (pierwsze 8 el.): {vectors[0][:8]}")
            else:
                print("  Nie znaleziono idei.")
        else:
            print("  Nieznana komenda.")

if __name__ == "__main__":
    main()