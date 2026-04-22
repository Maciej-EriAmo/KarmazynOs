#!/usr/bin/env python3
"""
Uruchomienie HSS grid search na danych Paul 2015.
"""

import sys
import os

# Dodaj ścieżki
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hss_karmazyn_matrix import run_hss_grid_simple

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python run_hss_grid.py paul15.h5 [n_sessions]")
        sys.exit(1)
    
    path = sys.argv[1]
    n_sessions = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    score, hss = run_hss_grid_simple(path, n_sessions=n_sessions, verbose=True)
    
    print("\n" + "="*70)
    print("PODSUMOWANIE")
    print("="*70)
    if score['from_expected'] >= 10 and len(set(score.get('top20_lineages', []))) >= 3:
        print("  ✓ HSS DZIAŁA — widać różnorodność!")
    else:
        print("  · Sygnał jest, ale potrzebna dalsza optymalizacja.")
