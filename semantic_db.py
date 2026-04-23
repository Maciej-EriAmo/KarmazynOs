# semantic_db.py
from karmazyn import KarmazynOS
import json
import numpy as np  # <- dodaj ten import

class SemanticDB:
    def __init__(self, kernel: KarmazynOS):
        self.k = kernel
        self.collections = {}

    def insert(self, collection: str, data: dict):
        content = json.dumps(data)
        label = self.k.write(content)
        if collection not in self.collections:
            self.collections[collection] = []
        self.collections[collection].append(label)
        self.k.consolidate(label)
        return label

    def search(self, collection: str, query: str, k: int = 5):
        if collection not in self.collections:
            return []
        results = []
        q_sem = self.k.phi.embed_semantic(query.encode())
        for lbl in self.collections[collection]:
            b = self.k.bubbles.get_by_label(lbl)
            if b:
                sim = float(np.dot(q_sem, b.S_sem))
                results.append((sim, b))
        results.sort(reverse=True)
        return [(b.label, self.k.read_bubble(b.label)) for _, b in results[:k]]

    def create_idea(self, collection: str, topic: str):
        if collection not in self.collections:
            return None
        labels = self.collections[collection][:10]
        return self.k.archive_bubbles_to_hologram(topic, labels)

    def semantic_query(self, idea_id: str, prompt: str):
        vectors = self.k.recall_from_hologram(idea_id, prompt, temperature=0.2, k=1)
        return vectors

if __name__ == "__main__":
    k = KarmazynOS()
    db = SemanticDB(k)
    db.insert("users", {"name": "Alice", "role": "admin"})
    db.insert("users", {"name": "Bob", "role": "user"})
    results = db.search("users", "administrator")
    print(results)