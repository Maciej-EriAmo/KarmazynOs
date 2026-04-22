"""
Hematopoiesis Colony — Paul 2015 validation (v2.7 — bifurkacje)
=====================================================================

Nowy test (Opcja C):
  Zamiast HSC → * (gdzie centroid HSC jest rozmyty),
  testujemy dwie niezależne bifurkacje:

    Test 1: MEP → ? (oczekiwane: Ery lub Mk)
    Test 2: GMP → ? (oczekiwane: Neu, Mon, DC, Baso lub Eos)

  Każdy test uruchamia pełną kolonię z innym startem.
  Jeśli oba znajdują biologicznie poprawnych potomków —
  kolonia rekonstruuje bifurkację, nie pełne drzewo.

Użycie:
    python hematopoiesis_colony.py --real paul15.h5 --gate-factor 0.8 --top-k 20
    python hematopoiesis_colony.py --real paul15.h5 --gate-factor 0.8 --start-from GMP
    python hematopoiesis_colony.py --real paul15.h5 --gate-factor 0.8 --start-from MEP --n-gen 5

Nowy parametr --start-from: HSC (default) | MEP | GMP | all (uruchamia wszystkie 3)
"""

import numpy as np
import hashlib
import argparse
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from karmazyn_matrix_v34 import KarmazynMatrix


# ============================================================
# Struktura Paul 2015
# ============================================================

PAUL15_CLUSTERS = {
    '1Ery':   {'lineage': 'Ery', 'markers': ['Klf1','Hba-a1','Car2','Bpgm','Gypa','Alas2','Tfrc']},
    '2Ery':   {'lineage': 'Ery', 'markers': ['Hba-a1','Hbb-b1','Klf1','Car1','Trim10','Nfe2','Kel']},
    '3Ery':   {'lineage': 'Ery', 'markers': ['Klf1','Gata1','Epor','Car1','Cited2','Rbm38','Ahsp']},
    '4Ery':   {'lineage': 'Ery', 'markers': ['Gata1','Tal1','Hba-a1','Epor','Cited4','Cnbp']},
    '5Ery':   {'lineage': 'Ery', 'markers': ['Gata1','Kit','Mpl','Hba-a1','Epor','Cited4']},
    '6Ery':   {'lineage': 'HSC', 'markers': ['Gata2','Kit','Mpl','Tal1','Runx1','Lyl1','Hmga2']},
    '7MEP':   {'lineage': 'MEP', 'markers': ['Gata1','Gata2','Klf1','Epor','Car1','Tal1','Lmo2']},
    '8Mk':    {'lineage': 'Mk',  'markers': ['Pf4','Vwf','Itga2b','Mpl','Gata1','Pbx1','Nrg1']},
    '9GMP':   {'lineage': 'GMP', 'markers': ['Mpo','Cebpa','Csf3r','Elane','Prg3','Ctsg']},
    '10GMP':  {'lineage': 'GMP', 'markers': ['Mpo','Elane','Cebpe','Ltf','S100a8','Prg3']},
    '11DC':   {'lineage': 'DC',  'markers': ['Irf8','Bst2','Siglech','H2-Aa','Ccr7','Cd86']},
    '12Baso': {'lineage': 'Baso','markers': ['Ms4a2','Mcpt8','Fcer1a','Il4','Hdc','Prss34']},
    '13Baso': {'lineage': 'Baso','markers': ['Ms4a2','Fcer1a','Mcpt8','Hdc','Cx3cr1','Il4']},
    '14Mo':   {'lineage': 'Mon', 'markers': ['Csf1r','Cd14','Ccl2','Ly6c2','S100a4','Cx3cr1']},
    '15Mo':   {'lineage': 'Mon', 'markers': ['Csf1r','Itgam','Cd68','Ccr2','S100a6','Mafb']},
    '16Neu':  {'lineage': 'Neu', 'markers': ['S100a8','S100a9','Mmp8','Lcn2','Ltf','Cebpe']},
    '17Neu':  {'lineage': 'Neu', 'markers': ['S100a8','Mpo','Elane','Csf3r','S100a9','Ngp']},
    '18Eos':  {'lineage': 'Eos', 'markers': ['Prg2','Il5ra','Ear2','Epx','Ccr3','Rnase2b']},
    '19Lymph':{'lineage': 'Lymph','markers': ['Cd3e','Gata3','Il7r','Tcf7','Cd79a','Ebf1']},
}

DIFF_TREE = {
    'HSC':  ['MEP', 'GMP'],
    'MEP':  ['Ery', 'Mk'],
    'GMP':  ['Neu', 'Mon', 'DC', 'Baso', 'Eos'],
    'Ery':  [], 'Mk': [], 'Neu': [], 'Mon': [],
    'DC':   [], 'Baso': [], 'Eos': [], 'Lymph': [],
}

ALL_MARKERS = sorted(set(g for c in PAUL15_CLUSTERS.values() for g in c['markers']))


# ============================================================
# VSA + syntetyczne
# ============================================================

def gene_vsa(gene: str, dim: int) -> np.ndarray:
    seed = int(hashlib.md5(gene.encode()).hexdigest(), 16) % (2**32)
    v = np.random.default_rng(seed).normal(0, 1, dim)
    return v / np.linalg.norm(v)


def expr_to_vsa(cluster_id: str, noise: float, dim: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    markers = set(PAUL15_CLUSTERS[cluster_id]['markers'])
    result = np.zeros(dim)
    for g in ALL_MARKERS:
        base = 1.0 if g in markers else 0.03
        expr = max(0.0, base + rng.normal(0, noise))
        result += expr * gene_vsa(g, dim)
    return result / (np.linalg.norm(result) + 1e-9)


def make_synthetic_cells(n_per_cluster: int, noise: float, dim: int) -> list[dict]:
    cells = []
    for cid, info in PAUL15_CLUSTERS.items():
        for i in range(n_per_cluster):
            cells.append({
                'cluster': cid,
                'lineage': info['lineage'],
                'vector':  expr_to_vsa(cid, noise, dim, hash(cid) % 10000 + i),
            })
    np.random.default_rng(42).shuffle(cells)
    return cells


# ============================================================
# Ładowanie realnych danych
# ============================================================

def load_real_cells(path: str, dim: int, balance: int = 150) -> list[dict]:
    import pathlib
    p = pathlib.Path(path)
    assert p.exists(), f"Brak pliku: {path}"
    print(f"  Wczytywanie: {path}")

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

    print(f"  Kształt: {adata.shape}")
    print(f"  Klastry: {adata.obs['paul15_clusters'].value_counts().to_dict()}")

    import scipy.sparse as sp
    X = adata.X.toarray() if sp.issparse(adata.X) else np.array(adata.X)
    X = np.log1p(X).astype(np.float64)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9

    from sklearn.decomposition import PCA
    nc    = min(dim, X.shape[1], X.shape[0] - 1)
    X_pca = PCA(n_components=nc, random_state=42).fit_transform(X)
    if nc < dim:
        X_pca = np.hstack([X_pca, np.zeros((X_pca.shape[0], dim - nc))])
    X_pca /= np.linalg.norm(X_pca, axis=1, keepdims=True) + 1e-9

    def cluster_to_lin(cname):
        for s in ['Ery','MEP','Mk','GMP','DC','Baso','Mon','Neu','Eos','Lymph']:
            if s in cname: return s
        return cname

    cells = []
    for i, (_, row) in enumerate(adata.obs.iterrows()):
        cluster = row['paul15_clusters']
        lineage = cluster_to_lin(cluster)
        if cluster == '6Ery':
            lineage = 'HSC'
        cells.append({'cluster': cluster, 'lineage': lineage, 'vector': X_pca[i]})

    if balance > 0:
        print(f"\n  === BALANSOWANIE (target = {balance} na linię) ===")
        lineage_groups = defaultdict(list)
        for cell in cells:
            lineage_groups[cell['lineage']].append(cell)

        balanced = []
        for lin, group in sorted(lineage_groups.items()):
            orig = len(group)
            if orig > balance:
                selected = np.random.default_rng(42).choice(group, balance, replace=False).tolist()
                balanced.extend(selected)
                print(f"  → {lin:6s} : {orig:4d} → {balance}")
            else:
                balanced.extend(group)
                print(f"  → {lin:6s} : {orig:4d} (zachowane)")
        cells = balanced
        print(f"  Balanced total: {len(cells)} komórek")
    else:
        print("  Balansowanie wyłączone")

    np.random.default_rng(42).shuffle(cells)
    print(f"  Atomów (finalnie): {len(cells)}\n")
    return cells


# ============================================================
# Kolonia
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


def run_generation(core_vec, cells, gen_id, centroids, max_age, top_k,
                   dim, gate_factor, start_lineage, verbose):
    km   = KarmazynMatrix(dim=dim, seed=42 + gen_id)
    gate = (km.lambd * km.vac_threshold + km.friction * gate_factor) / km.k

    if verbose:
        print(f"  [gate ≈ {gate:.4f} (factor={gate_factor})]")

    km.add_atom_vector(f'core_G{gen_id}', 'core', core_vec, init_T=3.5)
    km.atoms[-1]['permanent'] = True
    km.atoms[-1]['age']       = 0

    for _ in range(15):
        for a in km.atoms:
            a['age'] = a.get('age', 0) + 1
        km.step()

    core_id, core_sim = nearest(core_vec, centroids)

    # ============================================================
    # DIAGNOSTYKA G0: rozkład sim per linia + top-k breakdown
    # ============================================================
    if verbose and gen_id == 0:
        print(f"\n  === Rozkład sim z trace_{start_lineage} ===")
        print(f"  {'lin':6s} {'mean':>7s} {'std':>7s} {'min':>7s} {'max':>7s}   above_gate")
        per_lineage_trace_sims = defaultdict(list)
        for cell in cells:
            s = float(np.dot(cell['vector'], km.trace))
            per_lineage_trace_sims[cell['lineage']].append(s)
        for lin in sorted(per_lineage_trace_sims.keys()):
            sims = np.array(per_lineage_trace_sims[lin])
            above = int((sims > gate).sum())
            marker = "→" if lin in DIFF_TREE.get(start_lineage, []) else " "
            print(f"{marker} {lin:6s} {sims.mean():7.3f} {sims.std():7.3f} "
                  f"{sims.min():7.3f} {sims.max():7.3f}   {above:3d}/{len(sims):<3d}")
        print()

    # ============================================================
    # Admission
    # ============================================================
    admitted = []
    for cell in cells:
        if float(np.dot(cell['vector'], km.trace)) > gate:
            km.atoms.append({
                'label':     f"c{len(admitted)}",
                'topic':     'cell',
                'lineage':   cell['lineage'],
                'cluster':   cell.get('cluster', '?'),
                'S':         cell['vector'],
                'T':         1.5,
                'age':       0,
                'permanent': False,
            })
            km._rebuild_trace()
            admitted.append(cell)

    # T-competition
    for _ in range(max_age - 1):
        for a in km.atoms:
            a['age'] = a.get('age', 0) + 1
        km.step()

    survivors = sorted(
        [a for a in km.atoms if a.get('topic') == 'cell'],
        key=lambda x: x['T'], reverse=True,
    )

    tc = {}
    for a in survivors:
        lineage = a.get('lineage', '?')
        tc[lineage] = tc.get(lineage, 0) + 1

    # ============================================================
    # DIAGNOSTYKA G0: top-20 breakdown po klastrach
    # ============================================================
    if verbose and gen_id == 0:
        top20 = survivors[:20]
        cluster_breakdown = defaultdict(int)
        lineage_breakdown = defaultdict(int)
        for a in top20:
            cluster_breakdown[a.get('cluster', '?')] += 1
            lineage_breakdown[a.get('lineage', '?')] += 1

        print(f"  === Top-20 zwycięzców ===")
        print(f"  Linie: {dict(sorted(lineage_breakdown.items(), key=lambda x: -x[1]))}")
        print(f"  Klastry: {dict(sorted(cluster_breakdown.items(), key=lambda x: -x[1]))}")

        expected = DIFF_TREE.get(start_lineage, [])
        from_expected = sum(lineage_breakdown.get(l, 0) for l in expected)
        from_self     = lineage_breakdown.get(start_lineage, 0)
        from_other    = 20 - from_expected - from_self

        print(f"\n  Z oczekiwanych potomków {expected}: {from_expected}/20")
        print(f"  Z linii startowej ({start_lineage}): {from_self}/20")
        print(f"  Z innych (niepowiązanych): {from_other}/20")

        if from_expected >= 5:
            print(f"  ✓ BIFURKACJA WYKRYTA: kolonia znalazła biologicznie poprawnych potomków")
        elif from_self > 10:
            print(f"  = SELF-LOOP: kolonia pozostaje przy linii startowej")
        else:
            print(f"  ⚠ ROZMYCIE: brak wyraźnego sygnału bifurkacji")
        print()

    top_vecs  = [a['S'] for a in survivors[:top_k]]
    if top_vecs:
        nv = np.sum(top_vecs, axis=0)
        next_core = nv / (np.linalg.norm(nv) + 1e-9)
    else:
        next_core = core_vec
    next_id, next_sim = nearest(next_core, centroids)

    if verbose:
        tc_top = dict(sorted(tc.items(), key=lambda x: -x[1])[:8])
        print(f"G{gen_id} | core={core_id} ({core_sim:.4f})")
        print(f"  Admitted: {len(admitted)}/{len(cells)}  "
              f"Survivors: {len(survivors)}  {tc_top}")
        print(f"  → G{gen_id+1}: {next_id} ({next_sim:.4f})")

    return {
        'gen':         gen_id,
        'core_id':     core_id,
        'core_sim':    core_sim,
        'n_admitted':  len(admitted),
        'n_survivors': len(survivors),
        'type_counts': tc,
        'next_core':   next_core,
        'next_id':     next_id,
        'next_sim':    next_sim,
    }


def run_colony(cells, start='HSC', max_age=40, top_k=15, n_gen=12, dim=512,
               gate_factor=1.18, verbose=True):
    centroids = build_centroids(cells)
    print(f"\n{'='*70}")
    print(f"KOLONIA  start={start}  max_age={max_age}  top_k={top_k}  "
          f"gate_factor={gate_factor}")
    print(f"Oczekiwani potomkowie: {DIFF_TREE.get(start, [])}")
    print(f"Lineages w danych: {sorted(centroids.keys())}")

    print("\nSeparacja centroidów od startu (sim):")
    if start in centroids:
        start_c = centroids[start]
        for lin in sorted(centroids.keys()):
            if lin == start:
                continue
            s = float(np.dot(start_c, centroids[lin]))
            marker = "→" if lin in DIFF_TREE.get(start, []) else " "
            print(f"{marker} {start}-{lin:6s}: {s:7.3f}")

    if start not in centroids:
        start = sorted(centroids.keys())[0]
    current_core = centroids[start].copy()

    history = []
    for gen in range(n_gen):
        r = run_generation(
            current_core, cells, gen, centroids, max_age, top_k,
            dim, gate_factor, start, verbose,
        )
        history.append(r)
        current_core = r['next_core']
        if gen > 0 and r['next_id'] == history[-2]['next_id']:
            print(f"\n  → Stabilna w G{gen}")
            break

    traj = [h['core_id'] for h in history]
    if history and history[-1]['next_id'] != traj[-1]:
        traj.append(history[-1]['next_id'])

    print(f"\n{'='*70}")
    print(f"TRAJEKTORIA: {' → '.join(traj)}")
    print()

    correct = total = 0
    for i in range(len(traj) - 1):
        p, c = traj[i], traj[i+1]
        exp  = DIFF_TREE.get(p, [])
        ok   = c in exp or c == p
        print(f"  G{i}→G{i+1}: {p} → {c}  expected={exp}  {'✓' if ok else '✗'}")
        if ok:
            correct += 1
        total += 1

    acc = correct / max(1, total)
    print(f"\n  Zgodność z biologią: {correct}/{total} = {acc:.0%}")

    return {'history': history, 'trajectory': traj, 'accuracy': acc}


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--real',        metavar='PATH')
    ap.add_argument('--dim',         type=int,   default=512)
    ap.add_argument('--max-age',     type=int,   default=40)
    ap.add_argument('--top-k',       type=int,   default=15)
    ap.add_argument('--n-gen',       type=int,   default=8)
    ap.add_argument('--noise',       type=float, default=0.12)
    ap.add_argument('--n-cells',     type=int,   default=15)
    ap.add_argument('--balance',     type=int,   default=150)
    ap.add_argument('--gate-factor', type=float, default=0.8,
                    help='0.8 = sweet spot dla real data po diagnozie v2.6')
    ap.add_argument('--start-from',  default='HSC',
                    choices=['HSC', 'MEP', 'GMP', 'all'],
                    help='Linia startowa kolonii lub "all" dla 3 kolejnych testów')
    args = ap.parse_args()

    print("=" * 70)
    if args.real:
        print("HEMATOPOIESIS COLONY — PRAWDZIWE DANE")
        cells = load_real_cells(args.real, dim=args.dim, balance=args.balance)
    else:
        print("HEMATOPOIESIS COLONY — DANE SYNTETYCZNE")
        cells = make_synthetic_cells(args.n_cells, args.noise, args.dim)

    # Uruchom jeden test lub wszystkie trzy
    starts = ['HSC', 'MEP', 'GMP'] if args.start_from == 'all' else [args.start_from]
    results = {}

    for start in starts:
        print(f"\n{'#' * 70}")
        print(f"# TEST BIFURKACJI: start={start}")
        print(f"# Oczekiwane: {start} → {DIFF_TREE.get(start, [])}")
        print(f"{'#' * 70}")
        results[start] = run_colony(
            cells       = cells,
            start       = start,
            max_age     = args.max_age,
            top_k       = args.top_k,
            n_gen       = args.n_gen,
            dim         = args.dim,
            gate_factor = args.gate_factor,
        )

    print(f"\n{'='*70}")
    print("PODSUMOWANIE WSZYSTKICH TESTÓW")
    print(f"{'='*70}")
    print(f"  Dane:        {'PRAWDZIWE' if args.real else 'SYNTETYCZNE'}")
    if args.real and args.balance > 0:
        print(f"  Balans:      {args.balance} na linię")
    print(f"  Gate factor: {args.gate_factor}")
    print()
    for start, r in results.items():
        expected = DIFF_TREE.get(start, [])
        print(f"  {start:4s}: {' → '.join(r['trajectory']):30s}  "
              f"expected={expected}  "
              f"acc={r['accuracy']:.0%}")


if __name__ == '__main__':
    main()
