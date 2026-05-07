# test_persistence.py
from karmazyn import KarmazynOS

# Zapis
ko = KarmazynOS()
label = ko.write("test persystencji kluczy")
atom_before = ko.phi._mx.get_atom(label)
atom_before.E = "extra context"
atom_before.decay = 0.05
atom_before.age = 10

# Test rejestru agentów i IDF
ko.derive_agent("test_agent", "verification_task")
ko.phi.embed_semantic(b"doc for idf", update=True)

bid = ko.consolidate(label)
key_before = ko.bubbles._b[bid].bubble_key.hex()
content_before = ko.read_bubble(label)
ko.save("./test_save_p2s")

# Odczyt w nowej instancji
ko2 = KarmazynOS()
ko2.load("./test_save_p2s")
key_after = ko2.bubbles._b[bid].bubble_key.hex()
content_after = ko2.read_bubble(label)

atom_after = ko2.phi._mx.get_atom(label)

assert label in ko2._amap, f"_amap nie odtworzone dla {label}"
assert label in ko2._raw, f"_raw nie odtworzone dla {label}"
assert ko2._raw[label] == "test persystencji kluczy".encode(), "_raw treść różna"

assert key_before == key_after, f"KLUCZE RÓŻNE!\nPrzed: {key_before[:16]}...\nPo:    {key_after[:16]}..."
assert content_before == content_after, f"TREŚĆ RÓŻNA!\nPrzed: {content_before}\nPo:    {content_after}"
assert atom_after is not None, "Atom nie został odtworzony!"
assert atom_after.E == "extra context", f"E RÓŻNE! {atom_after.E}"
assert atom_after.decay == 0.05, f"decay RÓŻNE! {atom_after.decay}"
assert atom_after.age == 10, f"age RÓŻNE! {atom_after.age}"

# Weryfikacja rejestru i IDF
assert 101 in ko2._reg, "Agent registry not restored!"
assert ko2._reg[101][0] == "verification_task"
assert ko2.phi._idf._ndocs > 0, "IDF ndocs not restored!"

print("✓ TEST ZALICZONY: klucze i treść identyczne po save/load")