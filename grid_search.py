"""
Hematopoiesis Colony — Grid Search
===================================
Systematyczne przeszukanie przestrzeni hiperparametrów.

Konfiguracje testowane:
  embedding:       PCA | log1p_only | diffusion_map | zscore
  n_hvg:           500 | 1500 | all (highly variable genes)
  gate_factor:     0.5 | 0.8 | 1.0 | 1.2
  start:           HSC | MEP | GMP
  balance:         150

Dla każdej kombinacji liczymy:
  - Czy top-20 zwycięzców zawiera biologicznie oczekiwanych potomków
  - Trajektoria pierwszych 3 pokoleń
  - Zgodność z drzewem

Wynik: tabela ~100-200 wierszy. Jeśli jakakolwiek kombinacja daje >50% zgodności
dla MEP→Ery/Mk lub GMP→Neu/Mon — mamy konfigurację która działa.

Użycie:
    python grid_search.py paul15.h5                    # pełny grid ~2h
    python grid_search.py paul15.h5 --quick            # mały grid ~15 min
    python grid_search.py paul15.h5 --quick --out results.csv
"""

import numpy as np
import hashlib
import argparse
import sys
import os
import time
import csv
from collections import defaultdict
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from karmazyn_matrix_v34 import KarmazynMatrix


# ============================================================
# Struktura Paul 2015 (ground truth)
# ============================================================

DIFF_TREE = {
    'HSC':  ['MEP', 'GMP'],
    'MEP':  ['Ery', 'Mk'],
    'GMP':  ['Neu', 'Mon', 'DC', 'Baso', 'Eos'],
    'Ery':  [], 'Mk': [], 'Neu': [], 'Mon': [],
    'DC':   [], 'Baso': [], 'Eos': [], 'Lymph': [],
}


# ============================================================
# Ładowanie Paul 2015 z różnymi preprocessingami
# ============================================================

def load_paul15_raw(path: str):
    """Zwraca adata z surową macierzą ekspresji i etykietami."""
    import pathlib
    p = pathlib.Path(path)
    assert p.exists(), f"Brak pliku: {path}"

    if path.endswith('.h5ad'):
        import anndata
        adata = anndata.read_h5ad(path)
    elif path.endswith('.h5'):
        import h5py, anndata
        with h5py.File(path, 'r') as f:
            X              = f['data.debatched'][()].T.astype(np.float32)
            gene_names     = f['data.debatched_rownames'][()].astype(str)
            cell_names     = f['data.debatched_colnames'][()].astype(str)
            clusters       = f['cluster.id'][()].flatten().astype(int)
            info_genes_raw = f['info.genes_strings'][()].astype(str)

        adata = anndata.AnnData(X)
        adata.var_names = gene_names
        adata.obs_names = cell_names
        ct_map = (6*['Ery'] + 'MEP Mk GMP GMP DC Baso Baso Mon Mon Neu Neu Eos Lymph'.split())
        adata.obs['paul15_clusters'] = [f"{i}{ct_map[i-1]}" for i in clusters]

        info_genes = np.intersect1d(info_genes_raw, adata.var_names)
        adata = adata[:, info_genes].copy()
    else:
        raise ValueError(f"Nieznany format: {path}")

    def cluster_to_lin(cname):
        for s in ['Ery','MEP','Mk','GMP','DC','Baso','Mon','Neu','Eos','Lymph']:
            if s in cname: return s
        return cname

    adata.obs['lineage'] = adata.obs['paul15_clusters'].apply(cluster_to_lin)
    adata.obs.loc[adata.obs['paul15_clusters'] == '6Ery', 'lineage'] = 'HSC'
    return adata


def preprocess(adata_raw, embedding: str, n_hvg: int, dim: int):
    """
    Preprocessing + embedding.

    embedding:
      'pca'           : log1p → row-L2 → PCA → row-L2
      'log1p_only'    : log1p → row-L2 (no dim reduction, use top genes)
      'diffusion_map' : log1p → PCA → diffusion map (approx)
      'zscore'        : z-score per gene → row-L2 → PCA
    """
    import scipy.sparse as sp

    X = adata_raw.X.toarray() if sp.issparse(adata_raw.X) else np.array(adata_raw.X)
    X = X.astype(np.float64)

    # HVG selection jeśli n_hvg < n_genes
    if n_hvg < X.shape[1]:
        # Wybierz geny z największą wariancją
        gene_var = X.var(axis=0)
        top_idx = np.argsort(gene_var)[-n_hvg:]
        X = X[:, top_idx]

    # Preprocessing
    if embedding == 'log1p_only':
        X = np.log1p(X)
        X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
        # Pad/truncate do dim
        if X.shape[1] > dim:
            X = X[:, :dim]
        elif X.shape[1] < dim:
            X = np.hstack([X, np.zeros((X.shape[0], dim - X.shape[1]))])
        X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
        return X

    if embedding == 'zscore':
        X = np.log1p(X)
        mean = X.mean(axis=0)
        std  = X.std(axis=0) + 1e-9
        X = (X - mean) / std

    elif embedding in ('pca', 'diffusion_map'):
        X = np.log1p(X)
        X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9

    # PCA
    from sklearn.decomposition import PCA
    nc = min(dim, X.shape[1], X.shape[0] - 1)
    pca = PCA(n_components=nc, random_state=42)
    X_embed = pca.fit_transform(X)

    if embedding == 'diffusion_map':
        # Uproszczona diffusion map: k-NN graph → Laplacian → eigenvectors
        from sklearn.neighbors import NearestNeighbors
        k = 30
        nn = NearestNeighbors(n_neighbors=k).fit(X_embed)
        distances, _ = nn.kneighbors(X_embed)
        sigma = np.median(distances[:, -1])
        # Transfer prob = exp(-d^2/sigma^2) dla najbliższych sąsiadów
        # Przybliżamy przez re-skalowanie PCA przez wariancję lokalną
        local_density = np.exp(-distances.mean(axis=1)**2 / (sigma**2 + 1e-9))
        X_embed = X_embed * local_density.reshape(-1, 1)

    # Pad to dim
    if X_embed.shape[1] < dim:
        X_embed = np.hstack([X_embed, np.zeros((X_embed.shape[0], dim - X_embed.shape[1]))])
    # L2 normalizacja per komórka
    X_embed /= np.linalg.norm(X_embed, axis=1, keepdims=True) + 1e-9
    return X_embed


def adata_to_cells(adata, X_embed, balance: int = 150):
    """Konwersja AnnData + embedding do listy atomów z balansowaniem."""
    cells = []
    for i, (_, row) in enumerate(adata.obs.iterrows()):
        cells.append({
            'cluster': row['paul15_clusters'],
            'lineage': row['lineage'],
            'vector':  X_embed[i].copy(),
        })

    if balance > 0:
        lineage_groups = defaultdict(list)
        for cell in cells:
            lineage_groups[cell['lineage']].append(cell)

        balanced = []
        for lin, group in sorted(lineage_groups.items()):
            orig = len(group)
            if orig > balance:
                selected = np.random.default_rng(42).choice(group, balance, replace=False).tolist()
                balanced.extend(selected)
            else:
                balanced.extend(group)
        cells = balanced

    np.random.default_rng(42).shuffle(cells)
    return cells


# ============================================================
# Kolonia (uproszczona, cicha)
# ============================================================

def nearest(vec, centroids):
    best, best_s = None, -1.0
    for k, c in centroids.items():
        s = float(np.dot(vec, c))
        if s > best_s:
            best, best_s = k, s
    return best, best_s


def build_centroids(cells):
    groups = defaultdict(list)
    for c in cells:
        groups[c['lineage']].append(c['vector'])
    return {
        lin: np.mean(vecs, axis=0) / (np.linalg.norm(np.mean(vecs, axis=0)) + 1e-9)
        for lin, vecs in groups.items()
    }


def run_generation_silent(core_vec, cells, gen_id, max_age, top_k, dim, gate_factor):
    km   = KarmazynMatrix(dim=dim, seed=42 + gen_id)
    gate = (km.lambd * km.vac_threshold + km.friction * gate_factor) / km.k

    km.add_atom_vector(f'core_G{gen_id}', 'core', core_vec, init_T=3.5)
    km.atoms[-1]['permanent'] = True
    km.atoms[-1]['age']       = 0
    for _ in range(15):
        for a in km.atoms:
            a['age'] = a.get('age', 0) + 1
        km.step()

    for cell in cells:
        if float(np.dot(cell['vector'], km.trace)) > gate:
            km.atoms.append({
                'label':     f"c{len(km.atoms)}",
                'topic':     'cell',
                'lineage':   cell['lineage'],
                'cluster':   cell['cluster'],
                'S':         cell['vector'],
                'T':         1.5,
                'age':       0,
                'permanent': False,
            })
            km._rebuild_trace()

    for _ in range(max_age - 1):
        for a in km.atoms:
            a['age'] = a.get('age', 0) + 1
        km.step()

    survivors = sorted(
        [a for a in km.atoms if a.get('topic') == 'cell'],
        key=lambda x: x['T'], reverse=True,
    )

    top_vecs = [a['S'] for a in survivors[:top_k]]
    if top_vecs:
        nv = np.sum(top_vecs, axis=0)
        next_core = nv / (np.linalg.norm(nv) + 1e-9)
    else:
        next_core = core_vec

    top_lineages = [a.get('lineage', '?') for a in survivors[:20]]
    return next_core, top_lineages, len(survivors)


def run_colony_silent(cells, start, centroids, max_age, top_k, n_gen, dim, gate_factor):
    if start not in centroids:
        return None, [], []
    current_core = centroids[start].copy()

    traj = [start]
    top_20_per_gen = []

    for gen in range(n_gen):
        next_core, top20, n_surv = run_generation_silent(
            current_core, cells, gen, max_age, top_k, dim, gate_factor,
        )
        top_20_per_gen.append(top20)
        next_id, _ = nearest(next_core, centroids)
        traj.append(next_id)
        current_core = next_core
        if len(traj) > 2 and traj[-1] == traj[-2]:
            break

    return traj, top_20_per_gen


def compute_score(traj, top_20_per_gen, start):
    """Dwa score:
       - trajectory_acc: ile przejść jest zgodnych z drzewem
       - bifurcation_score: ile expected potomków w top-20 G0
    """
    expected = DIFF_TREE.get(start, [])

    # Trajectory accuracy
    correct = 0
    total = max(1, len(traj) - 1)
    for i in range(len(traj) - 1):
        p, c = traj[i], traj[i + 1]
        exp_p = DIFF_TREE.get(p, [])
        if c in exp_p or c == p:
            correct += 1
    traj_acc = correct / total

    # Bifurcation score z G0
    if top_20_per_gen:
        g0 = top_20_per_gen[0]
        from_expected = sum(1 for l in g0 if l in expected)
        from_self = sum(1 for l in g0 if l == start)
        bif_score = from_expected / max(1, len(g0))
    else:
        bif_score = 0.0
        from_expected = from_self = 0

    return {
        'traj_acc':      traj_acc,
        'bif_score':     bif_score,
        'from_expected': from_expected,
        'from_self':     from_self,
        'trajectory':    ' → '.join(traj),
    }


# ============================================================
# Grid search
# ============================================================

def run_grid(
    paul15_path: str,
    embeddings:  list = None,
    n_hvgs:      list = None,
    gate_factors: list = None,
    starts:      list = None,
    dim:         int = 512,
    max_age:     int = 40,
    top_k:       int = 20,
    n_gen:       int = 5,
    balance:     int = 150,
    quick:       bool = False,
    out_csv:     str = None,
):
    if quick:
        embeddings   = embeddings   or ['pca', 'log1p_only']
        n_hvgs       = n_hvgs       or [1500, 3004]
        gate_factors = gate_factors or [0.8, 1.0]
        starts       = starts       or ['MEP', 'GMP']
    else:
        embeddings   = embeddings   or ['pca', 'log1p_only', 'diffusion_map', 'zscore']
        n_hvgs       = n_hvgs       or [500, 1500, 3004]
        gate_factors = gate_factors or [0.5, 0.8, 1.0, 1.2]
        starts       = starts       or ['HSC', 'MEP', 'GMP']

    print(f"{'='*75}")
    print("GRID SEARCH — Hematopoiesis Colony")
    print(f"{'='*75}")
    print(f"  Embeddings:    {embeddings}")
    print(f"  n_hvg:         {n_hvgs}")
    print(f"  gate_factors:  {gate_factors}")
    print(f"  starts:        {starts}")
    print(f"  dim={dim}, max_age={max_age}, top_k={top_k}, n_gen={n_gen}")

    total = len(embeddings) * len(n_hvgs) * len(gate_factors) * len(starts)
    print(f"\n  Łącznie konfiguracji: {total}")

    print(f"\n  Ładowanie Paul 2015...")
    adata_raw = load_paul15_raw(paul15_path)
    print(f"  Wczytano: {adata_raw.shape}")

    results = []
    idx = 0
    t_start = time.time()

    # Cache embeddingów — ten sam (embedding, n_hvg) daje te same cells
    embed_cache = {}

    print(f"\n{'#':>3s} {'emb':14s} {'nhvg':>5s} {'gate':>5s} {'start':>5s}  "
          f"{'traj_acc':>9s} {'bif':>6s} {'exp':>4s} {'self':>5s}  trajectory")
    print("-" * 95)

    for embedding in embeddings:
        for n_hvg in n_hvgs:
            cache_key = (embedding, n_hvg)
            if cache_key not in embed_cache:
                try:
                    X_embed = preprocess(adata_raw, embedding, n_hvg, dim)
                    cells   = adata_to_cells(adata_raw, X_embed, balance=balance)
                    centroids = build_centroids(cells)
                    embed_cache[cache_key] = (cells, centroids)
                except Exception as e:
                    print(f"  {embedding}/{n_hvg}: preprocessing FAILED ({e})")
                    embed_cache[cache_key] = None
                    idx += len(gate_factors) * len(starts)
                    continue

            if embed_cache[cache_key] is None:
                idx += len(gate_factors) * len(starts)
                continue

            cells, centroids = embed_cache[cache_key]

            for gate_factor in gate_factors:
                for start in starts:
                    idx += 1
                    try:
                        traj, top_20_per_gen = run_colony_silent(
                            cells, start, centroids,
                            max_age, top_k, n_gen, dim, gate_factor,
                        )
                        score = compute_score(traj, top_20_per_gen, start)
                    except Exception as e:
                        score = {'traj_acc': 0, 'bif_score': 0,
                                 'from_expected': 0, 'from_self': 0,
                                 'trajectory': f'ERROR: {e}'}

                    row = {
                        'idx': idx,
                        'embedding':   embedding,
                        'n_hvg':       n_hvg,
                        'gate_factor': gate_factor,
                        'start':       start,
                        **score,
                    }
                    results.append(row)

                    # Podświetl dobre wyniki
                    marker = ""
                    if score['from_expected'] >= 5:
                        marker = " ✓"
                    elif score['from_expected'] >= 3:
                        marker = " ·"

                    print(f"  {idx:>3d} {embedding:14s} {n_hvg:>5d} "
                          f"{gate_factor:>5.2f} {start:>5s}  "
                          f"{score['traj_acc']:>9.0%} "
                          f"{score['bif_score']:>6.0%} "
                          f"{score['from_expected']:>4d} "
                          f"{score['from_self']:>5d}  "
                          f"{score['trajectory'][:35]}{marker}")

    t_total = time.time() - t_start
    print(f"\n  Całkowity czas: {t_total:.1f}s = {t_total/60:.1f} min")

    # Sortuj po bifurcation score
    print(f"\n{'='*75}")
    print("TOP 15 KONFIGURACJI (po from_expected)")
    print(f"{'='*75}")
    print(f"  {'emb':14s} {'nhvg':>5s} {'gate':>5s} {'start':>5s}  "
          f"{'exp':>4s} {'self':>5s}  {'bif':>6s}  trajectory")
    print("-" * 85)

    top = sorted(results, key=lambda r: (-r['from_expected'], -r['bif_score']))[:15]
    for r in top:
        print(f"  {r['embedding']:14s} {r['n_hvg']:>5d} "
              f"{r['gate_factor']:>5.2f} {r['start']:>5s}  "
              f"{r['from_expected']:>4d} "
              f"{r['from_self']:>5d}  "
              f"{r['bif_score']:>6.0%}  "
              f"{r['trajectory'][:40]}")

    # Zapisz CSV
    if out_csv:
        with open(out_csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            for r in results:
                w.writerow(r)
        print(f"\n  Wyniki zapisane: {out_csv}")

    # Podsumowanie
    print(f"\n{'='*75}")
    print("WNIOSEK")
    print(f"{'='*75}")
    best = max(results, key=lambda r: r['from_expected'])
    if best['from_expected'] >= 10:
        print(f"  ✓ ZNALEZIONO dobrą konfigurację:")
        print(f"    embedding={best['embedding']}, n_hvg={best['n_hvg']}, "
              f"gate={best['gate_factor']}, start={best['start']}")
        print(f"    {best['from_expected']}/20 z oczekiwanych potomków")
    elif best['from_expected'] >= 5:
        print(f"  · Częściowy sygnał:")
        print(f"    embedding={best['embedding']}, start={best['start']}, "
              f"{best['from_expected']}/20 expected")
        print(f"    Potencjał do dalszej optymalizacji")
    else:
        print(f"  ✗ Żadna konfiguracja nie daje >5 z oczekiwanych potomków.")
        print(f"    Najlepszy wynik: {best['from_expected']}/20")
        print(f"    Wniosek: model nie rekonstruuje drzewa różnicowania Paul 2015")
        print(f"    w żadnym z testowanych embeddingów.")

    return results


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', help='Ścieżka do paul15.h5')
    ap.add_argument('--quick', action='store_true',
                    help='Mały grid (~15 min) zamiast pełnego (~2h)')
    ap.add_argument('--out', default='grid_results.csv',
                    help='Plik CSV z wynikami (default: grid_results.csv)')
    ap.add_argument('--dim', type=int, default=512)
    ap.add_argument('--n-gen', type=int, default=5)
    ap.add_argument('--balance', type=int, default=150)
    args = ap.parse_args()

    run_grid(
        paul15_path = args.path,
        quick       = args.quick,
        out_csv     = args.out,
        dim         = args.dim,
        n_gen       = args.n_gen,
        balance     = args.balance,
    )


if __name__ == '__main__':
    main()
