# D-Flow FM 1D2D: porównanie z SFINCS–SWMM

Status (2026-10-20): **działa**. D-Flow FM skompilowany ze źródeł Deltares
kompilatorami Intel oneAPI (darmowe, zamknięte), model zbudowany wyłącznie
darmowymi narzędziami Pythona Deltares.

## Kompilacja (`build_kit/`)

| | GNU (gfortran 13.3) | Intel oneAPI 2024.2 (ifx/icx/icpx, Intel MPI) |
|---|---|---|
| Poprawki kodu Deltares | 37 plików (składnia Fortranu, ok. 10 ukrytych błędów pamięci) | **żadne**; tylko atrapy CMake dla bibliotek z apt |
| Stabilność | awaria przy zakończeniu każdego przebiegu, uszkodzenie pamięci w ścieżce 1D2D | bez awarii |
| Czas obliczeń DQ0 (1 wątek) | 37 s | **2,9 s** |
| Czas kompilacji | ok. 15 min (z gotowymi poprawkami) | ok. 13 min |

Wniosek: **właściwa darmowa ścieżka to kompilatory Intela**, które Deltares
oficjalnie wspiera. Kompilacja GNU jest ok. 13 razy wolniejsza i niestabilna.
Kompilatory Intela działają na Windows i Linuksie (x86-64), nie na macOS
z procesorami Apple.

## Budowa modelu (`build_case.py`, `run_cases.py`, `analyse.py`)

HYDROLIB-core 1.5.0 + MeshKernel 8.3.0, te same parametry co test SFINCS–SWMM
z dopływem powierzchniowym (`../case_setup.py`). Trzy pułapki:

1. **Węzeł 1D dokładnie w środku komórki 2D daje połączenie 1D2D o zerowej długości,
   które silnik po cichu odrzuca.** Wymiana wynosi wtedy zero bez żadnego komunikatu.
   Rozwiązanie: sieć przesunięta o 0,5 m w bok, rzędne bez zmian.
2. Węzeł wylotu leżący na krawędzi domeny 2D zostaje „zabrany” przez warunek
   brzegowy powierzchni (ostrzeżenie „already claimed”). Rozwiązanie: wylot 5 m poza
   domeną.
3. HYDROLIB-core zapisuje parametry MDU odrzucane przez aktualny silnik (`qhrelax`,
   `wrishp_enc`) i wszystkie połączenia 1D2D jako typ `embedded`. Typ `street inlet`
   trzeba ustawić ręcznie w pliku sieci.

Wskaźnik `water_balance_exchange_with_1D` w pliku historii pozostaje zerowy mimo
działającej wymiany (najwyraźniej nie obejmuje tych połączeń). Wymianę liczę z bilansu
przepływów w przewodach przy każdej studzience.

## Wyniki: wymiana w stanach ustalonych [m³/s]

Dodatnia = powierzchnia → sieć. SFINCS–SWMM: wzory v2, `SLOT`, relaksacja 0,1, krok
SWMM 0,25 s. D-Flow FM: połączenie `embedded` (typ 3) albo `street inlet` (typ 5,
zamknięty prostokąt 0,5 × 0,5 m).

| Przypadek, stopień dopływu | Węzeł | SFINCS–SWMM | D-Flow FM `embedded` | D-Flow FM `street inlet` |
|---|---|---|---|---|
| sieć swobodna, 0,05 m³/s | J1 / J2 / J3 | +0,020 / +0,013 / +0,008 | **+0,020 / +0,013 / +0,007** | +0,005 / +0,005 / +0,004 |
| sieć swobodna, 0,15 m³/s | J1 / J2 / J3 | +0,034 / +0,031 / +0,029 | +0,053 / +0,042 / +0,025 | +0,013 / +0,013 / +0,012 |
| sieć przeciążona, 0,15 m³/s | J1 / J2 / J3 | +0,034 / +0,030 / −0,030 | +0,064 / −0,000 / −0,034 | +0,017 / +0,015 / −0,002 |
| cofka, 0,15 m³/s | J3 | −0,324 | −0,495 | −0,284 |

Odchylenie w stanach ustalonych D-Flow FM: ≤ 0,0005 m³/s we wszystkich przypadkach.
Solver liczy wymianę niejawnie, więc nie oscyluje, i to bez żadnej stabilizacji.

Obserwacje:

1. **Przy małym przepływie oba modele dają niemal tę samą wymianę** (D-Flow FM
   `embedded` vs SFINCS–SWMM: różnice 0–13%), mimo zupełnie innej fizyki połączenia.
2. Przy większych głębokościach połączenie `embedded` przejmuje więcej wody niż nasze
   wzory (Rubinato i in. 2017), a `street inlet` 0,5 × 0,5 m znacznie mniej. Wynik
   zależy więc silnie od tego, jak opisano wpust. To ten sam problem kalibracji co
   w SFINCS–SWMM.
3. **Jakościowo zachowanie jest zgodne:** nasycenie sieci przeciążonej (suma wymiany ok.
   0,03 m³/s w obu modelach), wybicie w J3 i wypływ wody z odbiornika przy cofce.
4. Stopień 0,10 m³/s w cofce nie jest stanem ustalonym (poziom na wylocie rośnie
   w latach 30–45 min), dlatego go pominięto.

## Czas obliczeń (1 wątek, nieobciążona maszyna)

| | SFINCS (–SWMM) | D-Flow FM (Intel) |
|---|---|---|
| 2D bez sieci | 0,4 s | 2,9 s |
| z siecią 1D | 0,5–0,6 s | 2,9–3,7 s |

D-Flow FM jest tu ok. **6 razy wolniejszy** (mapy zapisywane co 10 s zamiast co 600 s
lekko go obciążają). Na tak małej domenie różnica jest mało miarodajna; na dużych
zlewniach trzeba ją zmierzyć osobno.

## Odtworzenie

```bash
# silnik: build_kit/BUILD_NOTES.md (sekcja 5: Intel)
DFLOWFM_RUNNER=<katalog-kompilacji>/run_dflowfm_intel.sh python run_cases.py
python analyse.py   # wymaga ../results/summary.json z testu SFINCS–SWMM
```
