#!/usr/bin/env python3
"""
Wizualizacja wyników HSS na danych Paul 2015.
Generuje:
1. Heatmapę przypisań komórek do sesji
2. UMAP z kolorami sesji HSS
3. Rozkład linii komórkowych w każdej sesji
4. Trajektorię różnicowania (Sankey lub macierz przejść)
"""

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import pandas as pd
from sklearn.manifold import TSNE
import umap
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hss_karmazyn_matrix import run_hss_grid, clean_lineage
from grid_search import load_paul15_raw, preprocess, adata_to_cells, build_centroids


def collect_hss_assignments(hss, cells, gate_factor=0.8):
    """
    Zbiera przypisania komórek do sesji po symulacji.
    Zwraca: listy (lineage, session_id, similarity)
    """
    from karmazyn_matrix_v34 import KarmazynMatrix
    
    km_tmp = KarmazynMatrix(dim=512)
    gate = (km_tmp.lambd * km_tmp.vac_threshold + km_tmp.friction * gate_factor) / km_tmp.k
    
    assignments = []
    
    for cell in cells:
        vec = cell['vector']
        sid = hss.assign_session(vec)
        sim = float(np.dot(vec, hss.traces[sid]))
        
        # Tylko komórki które przekroczyły próg (były dodane)
        if sim > gate:
            assignments.append({
                'lineage': cell['lineage'],
                'cluster': cell['cluster'],
                'session': sid,
                'similarity': sim,
                'vector': vec
            })
    
    return assignments


def plot_heatmap_session_lineage(assignments, n_sessions=5, save_path='hss_heatmap.png'):
    """Heatmap: liczba komórek danej linii w sesji."""
    
    # Zbuduj macierz (sessions x lineages)
    lineages = sorted(set(a['lineage'] for a in assignments))
    matrix = np.zeros((n_sessions, len(lineages)))
    
    for a in assignments:
        matrix[a['session'], lineages.index(a['lineage'])] += 1
    
    # Normalizuj wierszami (procent w sesji)
    row_sums = matrix.sum(axis=1, keepdims=True)
    matrix_norm = matrix / (row_sums + 1e-9)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(matrix_norm, cmap='YlOrRd', aspect='auto')
    
    # Adnotacje
    ax.set_xticks(range(len(lineages)))
    ax.set_xticklabels(lineages, rotation=45, ha='right')
    ax.set_yticks(range(n_sessions))
    ax.set_yticklabels([f'Session {i}' for i in range(n_sessions)])
    ax.set_xlabel('Lineage', fontsize=12)
    ax.set_ylabel('HSS Session', fontsize=12)
    ax.set_title('HSS Session Composition by Lineage\n(normalized per session)', fontsize=14)
    
    # Kolorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Fraction of session', fontsize=10)
    
    # Dodaj liczby w komórkach
    for i in range(n_sessions):
        for j in range(len(lineages)):
            val = matrix[i, j]
            if val > 0:
                text = ax.text(j, i, f'{int(val)}',
                              ha="center", va="center", color="black", fontsize=8)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✓ Heatmap saved: {save_path}")
    
    return matrix


def plot_umap_sessions(assignments, save_path='hss_umap.png'):
    """UMAP 2D z kolorami sesji HSS."""
    
    if len(assignments) < 10:
        print("  ⚠️ Too few assignments for UMAP, skipping...")
        return
    
    # Zbierz wektory
    vectors = np.vstack([a['vector'] for a in assignments])
    session_colors = [a['session'] for a in assignments]
    lineages = [a['lineage'] for a in assignments]
    
    # UMAP
    reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=30)
    try:
        embedding = reducer.fit_transform(vectors)
    except Exception as e:
        print(f"  UMAP failed: {e}, trying t-SNE...")
        reducer = TSNE(n_components=2, random_state=42, perplexity=30)
        embedding = reducer.fit_transform(vectors)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Lewy panel: kolory według sesji
    sc1 = axes[0].scatter(embedding[:, 0], embedding[:, 1], 
                          c=session_colors, cmap='tab10', s=10, alpha=0.7)
    axes[0].set_title('HSS Session Assignment', fontsize=12)
    axes[0].set_xlabel('UMAP1')
    axes[0].set_ylabel('UMAP2')
    cbar1 = plt.colorbar(sc1, ax=axes[0])
    cbar1.set_label('Session ID')
    
    # Prawy panel: kolory według lineage
    unique_lineages = sorted(set(lineages))
    lineage_to_num = {l: i for i, l in enumerate(unique_lineages)}
    lineage_nums = [lineage_to_num[l] for l in lineages]
    
    sc2 = axes[1].scatter(embedding[:, 0], embedding[:, 1],
                          c=lineage_nums, cmap='Set3', s=10, alpha=0.7)
    axes[1].set_title('Biological Lineage', fontsize=12)
    axes[1].set_xlabel('UMAP1')
    axes[1].set_ylabel('UMAP2')
    
    # Legenda dla lineage
    handles = [plt.Line2D([0], [0], marker='o', color='w', 
                         markerfacecolor=plt.cm.Set3(i/len(unique_lineages)),
                         markersize=8, label=l) 
               for i, l in enumerate(unique_lineages)]
    axes[1].legend(handles=handles, loc='best', fontsize=8)
    
    plt.suptitle('HSS: Session Isolation vs Biological Lineage', fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✓ UMAP saved: {save_path}")


def plot_session_composition_bar(assignments, n_sessions=5, save_path='hss_composition.png'):
    """Wykres słupkowy: skład sesji (absolutny i procentowy)."""
    
    lineages = sorted(set(a['lineage'] for a in assignments))
    
    # Liczby absolutne
    abs_counts = np.zeros((n_sessions, len(lineages)))
    for a in assignments:
        abs_counts[a['session'], lineages.index(a['lineage'])] += 1
    
    # Procentowe
    row_sums = abs_counts.sum(axis=1, keepdims=True)
    pct_counts = abs_counts / (row_sums + 1e-9) * 100
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Wykres absolutny (stacked bar)
    bottom = np.zeros(n_sessions)
    for j, lin in enumerate(lineages):
        axes[0].bar(range(n_sessions), abs_counts[:, j], bottom=bottom, label=lin)
        bottom += abs_counts[:, j]
    
    axes[0].set_xlabel('Session ID')
    axes[0].set_ylabel('Number of cells')
    axes[0].set_title('Absolute composition', fontsize=12)
    axes[0].legend(loc='upper right', fontsize=8)
    axes[0].set_xticks(range(n_sessions))
    
    # Wykres procentowy (stacked bar)
    bottom = np.zeros(n_sessions)
    for j, lin in enumerate(lineages):
        axes[1].bar(range(n_sessions), pct_counts[:, j], bottom=bottom, label=lin)
        bottom += pct_counts[:, j]
    
    axes[1].set_xlabel('Session ID')
    axes[1].set_ylabel('Percentage (%)')
    axes[1].set_title('Relative composition (normalized)', fontsize=12)
    axes[1].set_xticks(range(n_sessions))
    axes[1].legend(loc='upper right', fontsize=8)
    
    plt.suptitle('HSS Session Composition by Lineage', fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✓ Bar chart saved: {save_path}")


def plot_trajectory_heatmap(trajectory_data, save_path='hss_trajectory.png'):
    """
    trajectory_data: lista słowników {'from': 'GMP', 'to': 'Mon', 'count': x}
    """
    if not trajectory_data:
        print("  ⚠️ No trajectory data, skipping...")
        return
    
    # Zbuduj macierz przejść
    all_states = sorted(set([d['from'] for d in trajectory_data] + [d['to'] for d in trajectory_data]))
    n = len(all_states)
    transition_matrix = np.zeros((n, n))
    
    for d in trajectory_data:
        i = all_states.index(d['from'])
        j = all_states.index(d['to'])
        transition_matrix[i, j] = d['count']
    
    # Normalizuj wierszami
    row_sums = transition_matrix.sum(axis=1, keepdims=True)
    transition_norm = transition_matrix / (row_sums + 1e-9)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(transition_norm, cmap='Blues', vmin=0, vmax=1)
    
    ax.set_xticks(range(n))
    ax.set_xticklabels(all_states, rotation=45, ha='right')
    ax.set_yticks(range(n))
    ax.set_yticklabels(all_states)
    ax.set_xlabel('To', fontsize=12)
    ax.set_ylabel('From', fontsize=12)
    ax.set_title('Lineage Transition Matrix (HSS)', fontsize=14)
    
    # Dodaj wartości
    for i in range(n):
        for j in range(n):
            if transition_matrix[i, j] > 0:
                text = ax.text(j, i, f'{int(transition_matrix[i, j])}',
                              ha="center", va="center", color="black" if transition_norm[i, j] < 0.5 else "white")
    
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Transition probability')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✓ Trajectory heatmap saved: {save_path}")


def main():
    print("="*70)
    print("HSS VISUALIZATION — Generating figures")
    print("="*70)
    
    # Najpierw uruchom HSS (lub wczytaj z pliku)
    path = sys.argv[1] if len(sys.argv) > 1 else 'paul15.h5'
    
    print("\n  Running HSS to collect assignments...")
    score, hss = run_hss_grid(
        paul15_path=path,
        n_sessions=5,
        gate_factor=0.8,
        embedding='log1p_only',
        n_hvg=3004,
        balance=150,
        verbose=False
    )
    
    # Wczytaj dane do zebrania przypisań
    adata_raw = load_paul15_raw(path)
    X_embed = preprocess(adata_raw, 'log1p_only', 3004, 512)
    cells = adata_to_cells(adata_raw, X_embed, balance=150)
    
    assignments = collect_hss_assignments(hss, cells, gate_factor=0.8)
    print(f"  Collected {len(assignments)} cell assignments")
    
    # Generuj wykresy
    print("\n  Generating figures...")
    plot_heatmap_session_lineage(assignments, n_sessions=5, save_path='hss_heatmap.png')
    plot_umap_sessions(assignments, save_path='hss_umap.png')
    plot_session_composition_bar(assignments, n_sessions=5, save_path='hss_composition.png')
    
    # Prosta trajektoria z score
    traj = score['trajectory'].split(' → ')
    trajectory_counts = {}
    for i in range(len(traj) - 1):
        key = (traj[i], traj[i+1])
        trajectory_counts[key] = trajectory_counts.get(key, 0) + 1
    
    trajectory_data = [{'from': k[0], 'to': k[1], 'count': v} 
                       for k, v in trajectory_counts.items()]
    plot_trajectory_heatmap(trajectory_data, save_path='hss_trajectory.png')
    
    print("\n" + "="*70)
    print("✅ All figures generated:")
    print("   - hss_heatmap.png      (session x lineage matrix)")
    print("   - hss_umap.png         (2D embedding with session colors)")
    print("   - hss_composition.png  (stacked bar charts)")
    print("   - hss_trajectory.png   (lineage transition heatmap)")
    print("="*70)


if __name__ == "__main__":
    main()
