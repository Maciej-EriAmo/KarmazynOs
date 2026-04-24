# test_persistence.py
from karmazyn import KarmazynOS

# Zapis
ko = KarmazynOS()
label = ko.write("test persystencji kluczy")
bid = ko.consolidate(label)
key_before = ko.bubbles._b[bid].bubble_key.hex()
content_before = ko.read_bubble(label)
ko.save("./test_save_p2s")

# Odczyt w nowej instancji
ko2 = KarmazynOS()
ko2.load("./test_save_p2s")
key_after = ko2.bubbles._b[bid].bubble_key.hex()
content_after = ko2.read_bubble(label)

assert key_before == key_after, f"KLUCZE RÓŻNE!\nPrzed: {key_before[:16]}...\nPo:    {key_after[:16]}..."
assert content_before == content_after, f"TREŚĆ RÓŻNA!\nPrzed: {content_before}\nPo:    {content_after}"

print("✓ TEST ZALICZONY: klucze i treść identyczne po save/load")