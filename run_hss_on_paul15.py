#!/usr/bin/env python3
"""
Uruchomienie HSS grid search na danych Paul 2015.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hss_karmazyn_matrix import run_hss_grid


def main():
    parser = argparse.ArgumentParser(description='HSS Grid Search na Paul 2015')
    parser.add_argument('path', help='Ścieżka do pliku paul15.h5 lub paul15.h5ad')
    parser.add_argument('--sessions', '-s', type=int, default=5,
                        help='Liczba sesji HSS (domyślnie: 5)')
    parser.add_argument('--gate', '-g', type=float, default=0.8,
                        help='Gate factor (domyślnie: 0.8)')
    parser.add_argument('--hvg', type=int, default=3004,
                        help='Liczba highly variable genes (domyślnie: 3004)')
    parser.add_argument('--embedding', '-e', default='log1p_only',
                        choices=['log1p_only', 'pca', 'diffusion_map', 'zscore'],
                        help='Typ embeddingu (domyślnie: log1p_only)')
    parser.add_argument('--balance', type=int, default=150,
                        help='Balansowanie linii (domyślnie: 150)')
    parser.add_argument('--max-age', type=int, default=40,
                        help='Maksymalny wiek atomu (domyślnie: 40)')
    parser.add_argument('--n-gen', type=int, default=5,
                        help='Liczba generacji (domyślnie: 5)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Mniej outputu')
    
    args = parser.parse_args()
    
    # Sprawdź czy plik istnieje
    if not os.path.exists(args.path):
        print(f"Błąd: Plik {args.path} nie istnieje!")
        sys.exit(1)
    
    # Uruchom HSS grid
    score, hss = run_hss_grid(
        paul15_path=args.path,
        n_sessions=args.sessions,
        gate_factor=args.gate,
        n_hvg=args.hvg,
        embedding=args.embedding,
        balance=args.balance,
        max_age=args.max_age,
        n_gen=args.n_gen,
        verbose=not args.quiet
    )
    
    # Podsumowanie końcowe
    print("\n" + "="*70)
    print("PODSUMOWANIE KOŃCOWE")
    print("="*70)
    
    if score['from_expected'] >= 10:
        print("  ✓ SUKCES: Znaleziono dobrą konfigurację!")
        print(f"    {score['from_expected']}/20 oczekiwanych potomków")
        print(f"    {score['diversity']} różnych typów w top-20")
    elif score['from_expected'] >= 5:
        print("  · Częściowy sukces: Sygnał jest wyraźny")
        print(f"    {score['from_expected']}/20 oczekiwanych potomków")
    else:
        print("  ⚠️  Sygnał słaby – spróbuj zwiększyć liczbę sesji (-s 7 lub -s 10)")
    
    print(f"\n  Najlepsza trajektoria: {score['trajectory']}")
    print(f"  Różnorodność: {score['unique_types']}")


if __name__ == "__main__":
    main()
