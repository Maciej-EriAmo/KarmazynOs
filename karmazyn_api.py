# karmazyn_api.py
from karmazyn import KarmazynOS

class KarmazynAPI:
    def __init__(self):
        self.os = KarmazynOS()

    def remember(self, text: str) -> str:
        label = self.os.write(text)
        self.os.consolidate(label)
        return label

    def recall_text(self, query: str, top_k: int = 3) -> list:
        res = self.os.recall(query, k=top_k)
        return [(r['label'], self.os.read_bubble(r['label']) if r['layer']=='bubble' else None) for r in res]

    def create_idea(self, topic: str, texts: list) -> str:
        labels = [self.os.write(t) for t in texts]
        for lbl in labels: self.os.consolidate(lbl)
        return self.os.archive_bubbles_to_hologram(topic, labels)

    def imagine(self, idea_id: str, prompt: str) -> list:
        return self.os.recall_from_hologram(idea_id, prompt, temperature=0.5)

# Przykład
api = KarmazynAPI()
api.remember("Python to język programowania.")
idea_id = api.create_idea("Python", ["listy składane", "dekoratory", "async/await"])
vec = api.imagine(idea_id, "wydajność")
print(vec)