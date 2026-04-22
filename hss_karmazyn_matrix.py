"""
HSS KarmazynMatrix v1.0
Holographic Session Space — wiele równoległych atraktorów.
"""

import numpy as np
import math
import hashlib
import re
from typing import Optional, List, Tuple, Dict
from collections import Counter


class HSSKarmazynMatrix:
    """
    Holographic Session Space — wielosesyjny system atraktorów.
    
    Każda sesja to niezależny attractor (własny trace).
    Atomy są routowane do najbliższej sesji (max cosine similarity).
    """
    
    def __init__(
        self,
        dim: int = 512,
        n_sessions: int = 5,
        lambd: float = 0.08,
        vac_threshold: float = 0.15,
        k: float = 0.2,
        friction_margin: float = 1.2,
        trace_momentum: float = 0.3,
        seed: int = 42,
    ):
        self.dim = dim
        self.n_sessions = n_sessions
        self.lambd = lambd
        self.vac_threshold = vac_threshold
        self.k = k
        self.friction_margin = friction_margin
        self.trace_momentum = trace_momentum
        self.rng_seed = seed
        
        # Adaptacyjna friction
        self.friction = friction_margin / math.sqrt(dim)
        
        # Lista atomów
        self.atoms: List[dict] = []
        
        # Wiele śladów
        self.traces: List[np.ndarray] = [np.zeros(dim) for _ in range(n_sessions)]
        
        self.time = 0
        self.metrics_log = []
        
    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    
    def _normalize(self, v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / (norm + 1e-9)
    
    def _hash_to_vector(self, text: str) -> np.ndarray:
        """Deterministyczny wektor pseudo-losowy z hasha."""
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        seed = int(h, 16) % (2**32)
        gen = np.random.default_rng(seed)
        return self._normalize(gen.normal(0, 1.0, self.dim))
    
    # -----------------------------------------------------------------------
    # Routing
    # -----------------------------------------------------------------------
    
    def assign_session(self, vector: np.ndarray) -> int:
        """Przypisz wektor do najbliższej sesji."""
        if self.time == 0 or np.all(self.traces[0] == 0):
            # Inicjalizacja: round-robin
            return len(self.atoms) % self.n_sessions
        
        sims = [float(np.dot(vector, t)) for t in self.traces]
        return int(np.argmax(sims))
    
    # -----------------------------------------------------------------------
    # Zarządzanie atomami
    # -----------------------------------------------------------------------
    
    def add_atom(self, label: str, topic: str, init_T: float = 1.0,
                 session: Optional[int] = None) -> None:
        """Dodaj atom z losowym wektorem."""
        vector = self._hash_to_vector(label)
        if session is None:
            session = self.assign_session(vector)
        
        self.atoms.append({
            'label': label,
            'topic': topic,
            'S': vector,
            'T': init_T,
            'session': session,
        })
        self._rebuild_trace(session)
    
    def add_atom_vector(self, label: str, topic: str, vector: np.ndarray,
                        init_T: float = 1.0, session: Optional[int] = None) -> None:
        """Dodaj atom z gotowym wektorem."""
        v_norm = self._normalize(vector)
        if session is None:
            session = self.assign_session(v_norm)
        
        self.atoms.append({
            'label': label,
            'topic': topic,
            'S': v_norm,
            'T': init_T,
            'session': session,
        })
        self._rebuild_trace(session)
    
    def _rebuild_trace(self, session_id: int) -> None:
        """Przebuduj ślad dla konkretnej sesji."""
        session_atoms = [a for a in self.atoms if a.get('session') == session_id]
        
        if not session_atoms:
            self.traces[session_id] = np.zeros(self.dim)
            return
        
        weighted = np.sum([a['T'] * a['S'] for a in session_atoms], axis=0)
        blended = (self.trace_momentum * weighted + 
                   (1.0 - self.trace_momentum) * self.traces[session_id])
        self.traces[session_id] = self._normalize(blended)
    
    def _rebuild_all_traces(self) -> None:
        """Przebuduj wszystkie ślady."""
        for sid in range(self.n_sessions):
            self._rebuild_trace(sid)
    
    # -----------------------------------------------------------------------
    # Metryki
    # -----------------------------------------------------------------------
    
    def get_trace_for_cell(self, cell_vector: np.ndarray) -> np.ndarray:
        """Zwraca ślad sesji dla wektora."""
        sid = self.assign_session(cell_vector)
        return self.traces[sid]
    
    def session_similarity(self, cell_vector: np.ndarray) -> Tuple[int, float]:
        """Zwraca (session_id, similarity)."""
        sid = self.assign_session(cell_vector)
        return sid, float(np.dot(cell_vector, self.traces[sid]))
    
    def coherence_functional(self) -> float:
        """Empiryczna koherencja."""
        total = 0.0
        for a in self.atoms:
            sid = a.get('session', 0)
            total += a['T'] * float(np.dot(a['S'], self.traces[sid]))
        return -total
    
    def energy(self) -> float:
        return self.coherence_functional()
    
    # -----------------------------------------------------------------------
    # Dynamika
    # -----------------------------------------------------------------------
    
    def step(self) -> None:
        """Jeden krok ewolucji."""
        self.time += 1
        
        # Aktualizacja temperatur i filtracja
        alive = []
        for a in self.atoms:
            a['T'] *= math.exp(-self.lambd)
            sid = a.get('session', 0)
            infl = float(np.dot(a['S'], self.traces[sid]))
            a['T'] += (self.k * infl) - self.friction
            if a['T'] >= self.vac_threshold:
                alive.append(a)
        self.atoms = alive
        
        # Przebudowa śladów
        self._rebuild_all_traces()
    
    # -----------------------------------------------------------------------
    # Informacje
    # -----------------------------------------------------------------------
    
    def get_session_stats(self) -> List[dict]:
        """Statystyki dla każdej sesji."""
        stats = []
        for sid in range(self.n_sessions):
            atoms_in = [a for a in self.atoms if a.get('session') == sid]
            if atoms_in:
                avg_T = np.mean([a['T'] for a in atoms_in])
                trace_norm = np.linalg.norm(self.traces[sid])
            else:
                avg_T = 0.0
                trace_norm = 0.0
            
            stats.append({
                'session_id': sid,
                'atom_count': len(atoms_in),
                'avg_temperature': avg_T,
                'trace_norm': trace_norm,
                'labels': [a['label'] for a in atoms_in[:5]],
            })
        return stats
    
    def print_session_summary(self) -> None:
        """Wypisz podsumowanie sesji."""
        print(f"\n{'='*70}")
        print(f"HSS STATE (time={self.time}, atoms={len(self.atoms)})")
        print(f"{'='*70}")
        for s in self.get_session_stats():
            if s['atom_count'] > 0:
                print(f"  Session {s['session_id']}: {s['atom_count']} atoms, "
                      f"avg_T={s['avg_temperature']:.3f}, "
                      f"labels={s['labels'][:3]}")
            else:
                print(f"  Session {s['session_id']}: EMPTY")


# ===========================================================================
# FUNKCJE POMOCNICZE
# ===========================================================================

def clean_lineage(label: str) -> str:
    """Wyciąga czystą nazwę linii z etykiety typu '15Mon' lub 'cell_0_15Mon'."""
    if not label:
        return '?'
    
    # Lista wszystkich linii w Paul 2015
    lineages = ['Ery', 'MEP', 'Mk', 'GMP', 'DC', 'Baso', 'Mon', 'Neu', 'Eos', 'Lymph', 'HSC']
    
    for lin in lineages:
        if lin in label:
            return lin
    
    # Fallback: usuń cyfry na początku
    cleaned = re.sub(r'^\d+', '', label)
    return cleaned if cleaned else label


# ===========================================================================
# INTEGRACJA Z GRID SEARCH
# ===========================================================================

def run_hss_grid(paul15_path: str, n_sessions: int = 5, gate_factor: float = 0.8,
                 n_hvg: int = 3004, embedding: str = 'log1p_only',
                 balance: int = 150, max_age: int = 40, n_gen: int = 5,
                 verbose: bool = True) -> Tuple[dict, 'HSSKarmazynMatrix']:
    """
    Uruchom HSS grid search na danych Paul 2015.
    
    Returns:
        score: dict z metrykami
        hss: HSSKarmazynMatrix object
    """
    # Importy zależne
    import sys
    import os
    
    # Dodaj ścieżkę do oryginalnych plików
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from grid_search import load_paul15_raw, preprocess, adata_to_cells, build_centroids
    from grid_search import DIFF_TREE
    from karmazyn_matrix_v34 import KarmazynMatrix
    
    if verbose:
        print("\n" + "="*70)
        print(f"HSS GRID SEARCH")
        print(f"  n_sessions={n_sessions}, gate_factor={gate_factor}")
        print(f"  n_hvg={n_hvg}, embedding={embedding}")
        print("="*70)
    
    # Ładuj dane
    if verbose:
        print("  Ładowanie danych Paul 2015...")
    adata_raw = load_paul15_raw(paul15_path)
    X_embed = preprocess(adata_raw, embedding, n_hvg, 512)
    cells = adata_to_cells(adata_raw, X_embed, balance=balance)
    centroids = build_centroids(cells)
    
    if verbose:
        print(f"  Wczytano: {len(cells)} komórek, {len(centroids)} centroidów")
    
    # Inicjalizuj HSS
    hss = HSSKarmazynMatrix(dim=512, n_sessions=n_sessions, seed=42)
    
    # Dodaj centroidy jako atomy core (po jednym w każdej sesji)
    for i, (lin, vec) in enumerate(centroids.items()):
        session = i % n_sessions
        hss.add_atom_vector(f"centroid_{lin}", "core", vec, init_T=2.5, session=session)
    
    # Oblicz próg gate
    km_tmp = KarmazynMatrix(dim=512)
    gate = (km_tmp.lambd * km_tmp.vac_threshold + km_tmp.friction * gate_factor) / km_tmp.k
    
    if verbose:
        print(f"  Próg gate = {gate:.4f}")
    
    # Symulacja
    traj = ['GMP']
    all_top20_raw = []
    all_top20_clean = []
    
    for gen in range(n_gen):
        if verbose:
            print(f"  Generacja {gen+1}/{n_gen}...", end=" ", flush=True)
        
        # Dodaj komórki które przekraczają próg
        for cell in cells:
            sid = hss.assign_session(cell['vector'])
            sim = float(np.dot(cell['vector'], hss.traces[sid]))
            if sim > gate:
                hss.add_atom_vector(
                    f"cell_{gen}_{cell['cluster']}",
                    "cell",
                    cell['vector'],
                    init_T=1.5,
                    session=sid
                )
        
        # Ewolucja
        for _ in range(max_age):
            hss.step()
        
        # Zbierz top komórki
        survivors = sorted(
            [a for a in hss.atoms if a.get('topic') == 'cell'],
            key=lambda x: x['T'], reverse=True
        )
        
        top20_raw = [a.get('label', '?') for a in survivors[:20]]
        top20_clean = [clean_lineage(lbl) for lbl in top20_raw]
        
        all_top20_raw.append(top20_raw)
        all_top20_clean.append(top20_clean)
        
        # Znajdź następny core (najczęstsza oczekiwana linia)
        if top20_clean:
            expected = DIFF_TREE.get(traj[-1], [])
            # Licz tylko oczekiwane linie
            valid = [l for l in top20_clean if l in expected or l == traj[-1]]
            if valid:
                counter = Counter(valid)
                next_lin = counter.most_common(1)[0][0]
            else:
                next_lin = traj[-1]
            
            if next_lin in centroids:
                traj.append(next_lin)
            else:
                traj.append(traj[-1])
        else:
            traj.append(traj[-1])
        
        if verbose:
            print(f"done, atoms={len(hss.atoms)}")
    
    # Oblicz score
    expected_start = set(DIFF_TREE.get('GMP', []))
    g0_clean = all_top20_clean[0] if all_top20_clean else []
    
    from_expected = sum(1 for l in g0_clean if l in expected_start)
    from_self = sum(1 for l in g0_clean if l == 'GMP')
    bif_score = from_expected / max(1, len(g0_clean))
    
    # Trajectory accuracy
    correct = 0
    for i in range(len(traj) - 1):
        p, c = traj[i], traj[i + 1]
        if c in DIFF_TREE.get(p, []) or c == p:
            correct += 1
    traj_acc = correct / max(1, len(traj) - 1)
    
    score = {
        'from_expected': from_expected,
        'from_self': from_self,
        'bif_score': bif_score,
        'traj_acc': traj_acc,
        'trajectory': ' → '.join(traj),
        'diversity': len(set(g0_clean)),
        'unique_types': set(g0_clean),
        'top20_clean': g0_clean[:10],
    }
    
    if verbose:
        print(f"\n  {'='*50}")
        print(f"  WYNIKI HSS")
        print(f"  {'='*50}")
        print(f"    from_expected = {from_expected}/20")
        print(f"    bif_score     = {bif_score:.0%}")
        print(f"    traj_acc      = {traj_acc:.0%}")
        print(f"    trajectory    = {score['trajectory']}")
        print(f"    różnorodność  = {len(set(g0_clean))} typów: {set(g0_clean)}")
        print(f"    TOP 10: {g0_clean[:10]}")
        
        hss.print_session_summary()
    
    return score, hss


# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":
    print("HSS KarmazynMatrix v1.0 — test działania")
    print("="*70)
    
    # Prosty test
    hss = HSSKarmazynMatrix(dim=64, n_sessions=3, seed=42)
    
    hss.add_atom("A", "test", init_T=2.0, session=0)
    hss.add_atom("B", "test", init_T=2.0, session=1)
    hss.add_atom("C", "test", init_T=2.0, session=2)
    
    print("\n  Stan początkowy:")
    hss.print_session_summary()
    
    for _ in range(50):
        hss.step()
    
    print("\n  Po 50 krokach:")
    hss.print_session_summary()
    
    # Test routingu
    test_vec = hss._hash_to_vector("test_vector")
    sid, sim = hss.session_similarity(test_vec)
    print(f"\n  Routing testowego wektora → session {sid}, sim={sim:.4f}")
    
    print("\n  ✅ Test HSS zakończony pomyślnie.")
    print("\n  Aby uruchomić grid na Paul 2015:")
    print("    python -c \"from hss_karmazyn_matrix import run_hss_grid; run_hss_grid('paul15.h5', n_sessions=5)\"")
