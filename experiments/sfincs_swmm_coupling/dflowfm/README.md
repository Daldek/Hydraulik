# D-Flow FM 1D2D: próba porównania z SFINCS–SWMM

Status (2026-10-20): **2D działa, 1D2D nie działa** w samodzielnie skompilowanej,
w pełni darmowej wersji D-Flow FM.

## Co zrobiono

1. **Kompilacja silnika wyłącznie darmowymi narzędziami** (gfortran/gcc 13.3,
   Open MPI, zależności z apt i ze źródeł; bez kompilatorów Intela i bez
   infrastruktury Deltares). Instrukcja, poprawki i atrapy: `build_kit/`
   (`BUILD_NOTES.md`, `patches.diff`: 37 plików, w tym ok. 10 ukrytych błędów
   pamięci, które kompilator Intela toleruje, a gfortran nie).
   Ponowna kompilacja z poprawkami: ok. 15 min; pierwsze dojście do działającej
   wersji: ok. 1 h 45 min pracy na poziomie eksperta.
2. **Model wyłącznie darmowymi narzędziami Deltares** (HYDROLIB-core 1.5.0,
   MeshKernel 8.3.0): `build_case.py` buduje te same warianty co test SFINCS–SWMM
   z dopływem powierzchniowym (DQ0 bez sieci, DQ1–DQ3 z siecią, połączenia 1D2D typu
   `embedded` albo `street inlet`). `run_cases.py` je uruchamia.

## Wyniki

**2D (DQ0 vs SFINCS Q0, ta sama siatka 2 m, ten sam dopływ):**

| Czas | Głębokość na linii spływu SFINCS / D-Flow FM [cm] | Woda na powierzchni SFINCS / D-Flow FM [m³] |
|---|---|---|
| 1200 s (0,05 m³/s) | 4,35 / 4,30 | 22,3 / 19,3 |
| 2400 s (0,10 m³/s) | 5,78 / 5,75 | 40,4 / 36,8 |
| 3600 s (0,15 m³/s) | 6,80 / 6,76 | 53,5 / 48,9 |

Głębokości zgadzają się w granicach 1%. Objętość różni się o 8–14%, najpewniej przez inne
traktowanie płytkich komórek bocznych.

**Czas obliczeń (1 wątek, nieobciążona maszyna):** SFINCS 0,4 s, D-Flow FM 37 s, czyli
ok. 90 razy dłużej. Porównanie jest orientacyjne: D-Flow FM zapisywał mapy co 10 s,
SFINCS co 600 s.

**1D2D: brak wymiany.** Wszystkie warianty z siecią liczą się do końca, ale wymiana
1D–2D wynosi zero, a wyniki są identyczne jak bez sieci:

- połączenia 1D2D zapisane przez HYDROLIB-core są w pliku sieci poprawnie (węzły
  studzienek ↔ komórki nad nimi), ale silnik nie tworzy z nich przepływów
  i nie zgłasza błędu;
- próba z automatycznym tworzeniem połączeń (`CreateLinks1D2D = 1`) kończy się
  uszkodzeniem pamięci (`free()` w `setnodadm.f90`), czyli kolejnym ukrytym błędem
  tej kompilacji;
- na koniec każdego przebiegu program kończy się błędem segmentacji przy zwalnianiu
  pamięci (`ec_filereader.F90`). Wyniki są wtedy już zapisane.

Nie wiadomo, czy brak wymiany to błąd danych wejściowych, czy kompilacji. Ścieżka 1D
tej kompilacji nie była sprawdzona na żadnym poprawnym modelu referencyjnym.

## Problemy z darmową ścieżką (do ścieżki 2 Hydraulika)

1. HYDROLIB-core 1.5.0 zapisuje parametry MDU, które aktualny silnik odrzuca
   (`qhrelax`, `wrishp_enc`); trzeba je usuwać.
2. HYDROLIB-core zapisuje wszystkie połączenia 1D2D jako typ 3 (`embedded`); inne typy
   trzeba ustawiać ręcznie w pliku sieci.
3. Kompilacja kompilatorami GNU wymaga poprawek w kodzie Deltares i ujawnia błędy pamięci
   w ścieżkach, których nikt nie testuje tym kompilatorem.
