# Sprzężenie SFINCS–SWMM przez BMI: test wykonalności

Status: eksperyment (2026-10-20). Wstęp do krótkiej publikacji metodycznej; nie jest
to jeszcze część pakietu Hydraulik.

## 1. Cel

Sprawdzić, czy model 2D SFINCS (Deltares) można sprząc z modelem sieci 1D EPA SWMM 5
w schemacie podwójnego drenażu (*dual drainage*): woda z powierzchni wpływa do sieci
przez węzły wymiany, a przy przeciążeniu sieci lub cofce wraca na powierzchnię.
Pytania, w kolejności:

1. Czy technicznie da się prowadzić oba modele krok w krok i wymieniać wodę?
2. Czy sprzężenie zachowuje masę?
3. Czy wynik jest numerycznie stabilny i fizycznie sensowny; od czego to zależy?

Poza zakresem: dane rzeczywiste, siatka subgrid i quadtree, infiltracja, wydajność
na dużych domenach, kalibracja i walidacja względem pomiarów.

## 2. Metodyka

### 2.1 Domena 2D (SFINCS)

Domena idealizowana, dobrana tak, żeby każdy wynik dało się zinterpretować:

| Parametr | Wartość |
|---|---|
| Wymiar | 200 m × 42 m |
| Siatka | regularna, 2 m × 2 m (100 × 21 = 2100 komórek), bez subgrid |
| Powierzchnia | spadek podłużny 0,5% (w kierunku rosnącego x), poprzeczny 2% do linii spływu y = 21 m |
| Szorstkość | Manning n = 0,015 s/m^(1/3), stała |
| Infiltracja | brak |
| Brzegi | wszystkie zamknięte; wodę może wyprowadzić tylko sieć 1D |
| Parametry numeryczne | `alpha` = 0,5, `dtmax` = 1 s, `huthresh` = 0,001 m |
| Opad | równomierny, blokowy: 60 mm/h przez 20 min (168,07 m³); symulacja 60 min |

Zamknięte brzegi są celowe: bilans masy domyka się wtedy dokładnie
(opad = woda na powierzchni + woda w sieci + odpływ wylotem).

### 2.2 Sieć 1D (SWMM)

Trzy węzły wymiany na linii spływu: J1 (x = 51 m), J2 (101 m), J3 (151 m), oraz wylot
OUT (200 m). Dno węzłów 2 m pod powierzchnią, przewody kołowe o spadku 0,5%,
n = 0,013. Fala dynamiczna (`DYNWAVE`), stały krok 1 s (`VARIABLE_STEP 0`),
`MIN_SURFAREA` = 1,167 m², bardzo duża głębokość nadpiętrzenia węzłów (100 m),
żeby SWMM nigdy nie wylewał wody sam: o każdym wypływie na powierzchnię decyduje
koordynator.

| Wariant sieci | Średnice C1 / C2 / C3 | Wylot |
|---|---|---|
| swobodny odpływ (S1) | 0,6 / 0,6 / 0,6 m | swobodny |
| przeciążenie (S2) | 0,3 / 0,3 / 0,15 m | swobodny |
| cofka (S3) | 0,6 / 0,6 / 0,6 m | poziom wody rośnie od 7,0 m (30 min) do 9,6 m (45 min), powyżej terenu przy J2 i J3 |

### 2.3 Schemat sprzężenia

SFINCS jest sterowany przez BMI (biblioteka `libsfincs.so`, wywołania przez `ctypes`):
odczyt `zs` (poziom wody), zapis `qext` (zewnętrzne źródło/ujście, m³/s na komórkę).
SWMM jest sterowany przez `pyswmm` (odczyt ciśnienia w węźle, wpływ boczny węzła).

Koordynator działa jawnie, z synchronizacją w punktach wymiany `t_k = k·Δt_c`:

1. Odczytaj `zs` w komórce każdego węzła i ciśnienie `H` w węźle.
2. Policz wymianę `Q` (dodatnia = powierzchnia → sieć). `z_t` to rzędna terenu,
   `h = zs − z_t`; krata 0,5 × 0,5 m (A = 0,25 m², P = 2 m):
   - `H ≤ z_t` (węzeł niepełny): `Q = min(C_w·P·h^1,5·√(2g), C_o·A·√(2g·h))`, C_w = 0,4, C_o = 0,6,
   - `z_t < H < zs`: `Q = C_o·A·√(2g·(zs − H))`,
   - `H ≥ zs` (wybicie): `Q = −C_o·A·√(2g·(H − zs))`.
3. Opcjonalnie stabilizacja (p. 2.5).
4. Ogranicz `Q > 0` do wody dostępnej w komórce: `Q ≤ h·A_cell / (Δt_c + dtmax)`.
5. Ustaw `qext = −Q` i przesuń SFINCS do `t_{k+1}` (`update_until`).
6. Odczytaj faktyczny czas SFINCS-a i policz objętość, która opuściła powierzchnię:
   `V = Q·(t_SFINCS,nowy − t_SFINCS,stary)`.
7. Przekaż SWMM dokładnie tę objętość jako wpływ boczny `V/Δt_c` i przesuń go o `Δt_c`.

### 2.4 Synchronizacja kroków czasowych

SFINCS ma krok adaptacyjny (CFL), a SWMM stały. Z kodu SFINCS-a wynika, że
`update_until` **nie przycina** ostatniego kroku, więc model przestrzeliwuje cel o
maksymalnie jeden swój krok. Cele są bezwzględne, więc przesunięcie się nie kumuluje.

Rozwiązanie zastosowane w teście:
- **wymiana objętości, nie przepływów** (krok 6–7): bilans jest dokładny z samej
  konstrukcji, zostaje tylko przesunięcie w czasie ≤ jeden krok SFINCS-a;
- **jawne `dtmax` ≤ `Δt_c`**: domyślne `dtmax` = 60 s pozwala na start na suchej
  domenie krokiem 30 s;
- SWMM kroczy co 1 s (równe krokowi obliczeniowemu), co pozwala dokładnie całkować
  przepływ na wylocie przy każdym `Δt_c`; `Δt_c` musi być całkowitą liczbą sekund
  (ograniczenie `swmm_stride`).

### 2.5 Warianty stabilizacji

| Składnik | Opis |
|---|---|
| `SLOT` | metoda szczeliny Preissmanna w SWMM zamiast domyślnej `EXTRAN` dla przepływu ciśnieniowego |
| ogranicznik wyrównania | gdy `H > z_t`: `|Q|·Δt_c ≤ β·|zs − H|·A_eq`, `A_eq = A_cell·A_node/(A_cell + A_node)`, β = 0,5 |
| relaksacja | `Q_k = w·Q_nowe + (1 − w)·Q_{k−1}`; objętość nadal liczona z faktycznie użytego `Q_k`, więc masa zachowana |

### 2.6 Scenariusze

| Grupa | Scenariusze |
|---|---|
| A. Odniesienie | S0 (sam SFINCS), S0K (wbudowany koncepcyjny drenaż SFINCS: `piped_drainage`, cała siatka, 30 mm/h, bez wylotu) |
| B. Sprzężenie naiwne (domyślne SWMM) | S1, S2, S3 |
| C. Stabilizacja krok po kroku | S2/S3 + `SLOT`; + ogranicznik; S3 + `SLOT` + relaksacja w = 0,3 |
| D. Wariant zalecany i wrażliwość | S2/S3 + `SLOT` + relaksacja w = 0,1, `Δt_c` = 1, 5, 30 s |
| E. Dopływ powierzchniowy (p. 2.7) | Q0 (bez sieci), Q1, Q2, Q3 w wariantach: naiwny, `SLOT`, zalecany; Q2 zalecany z `Δt_c` = 5 s i z krokiem SWMM 0,5 i 0,25 s |

### 2.7 Wariant z dopływem powierzchniowym

Zamiast opadu woda wpływa na powierzchnię jako przepływ, w układzie podobnym do
eksperymentów laboratoryjnych podwójnego drenażu:

- **dopływ:** natywne punkty źródłowe SFINCS-a (`srcfile`/`disfile`), po jednym na
  każdy wiersz komórek górnej krawędzi (x = 1 m), równy podział;
- **hydrogram schodkowy:** 0,05 → 0,10 → 0,15 m³/s, każdy stopień przez 20 min,
  przejścia liniowe 60 s (razem 355,5 m³);
- **dolna krawędź:** odpływ swobodny. Koordynator odbiera przez `qext` wodę stojącą
  w ostatniej kolumnie komórek i księguje jej objętość, więc bilans zostaje dokładny;
- **stany ustalone:** statystyki z ostatnich 5 min każdego stopnia (średnia, odchylenie,
  zmiany znaku, dryf).

Zaleta: w stanie ustalonym prawdziwa wymiana jest stała, więc każda oscylacja jest
jednoznacznie artefaktem numerycznym.

## 3. Wyniki

Pełne liczby: `results/summary.json`. Błąd bilansu odniesiony do całkowitego
dopływu (opad + woda wpływająca wylotem przy cofce).

### 3.1 Wykonalność techniczna i bilans masy

- Sprzężenie działa: BMI SFINCS-a udostępnia wszystko, co potrzebne (`zs`, `zb`,
  `qext`, indeks komórki dla punktu, `update_until`). SWMM ląduje dokładnie w punktach
  wymiany, a SFINCS przestrzeliwuje cel o 0–0,5 s (S3, gdzie CFL ogranicza krok).
- **Sam interfejs sprzężenia nie wnosi błędu masy.** W każdym stabilnym przebiegu błąd
  po stronie powierzchni wynosi 0,035 m³, dokładnie tyle co w S0 bez sprzężenia
  (zaokrąglenia pojedynczej precyzji w SFINCS-ie). Błąd po stronie sieci jest równy
  błędowi ciągłości raportowanemu przez sam SWMM (np. S1: −0,313 m³ ≈ −0,32%
  z 98,5 m³).
- Koszt czasu na tej domenie: 0,45–0,7 s z sprzężeniem wobec 0,5 s samego SFINCS-a.
  Domena jest zbyt mała, by to uogólniać.

### 3.2 Stabilność

| Scenariusz | Wymiana [m³] | Maks. skok Q między krokami [m³/s] | Błąd bilansu [%] | Błąd ciągłości SWMM [%] |
|---|---|---|---|---|
| S1 naiwne | 98,5 | 0,000 | −0,17 | −0,32 |
| S2 naiwne (`EXTRAN`) | — rozbieżne | 7,6 | −14 615 | −2 526 |
| S3 naiwne (`EXTRAN`) | — rozbieżne | 3,2 | −975 | −479 |
| S2 + `SLOT` | 95,6 | 0,337 | −0,05 | −0,07 |
| S2 + `SLOT` + ogranicznik | 95,5 | 0,047 | −0,04 | −0,11 |
| **S2 + `SLOT` + relaksacja 0,1** | **95,8** | **0,014** | **−0,06** | **−0,14** |
| S3 + `SLOT` | −151,8 | 0,378 | −0,66 | −0,73 |
| S3 + `SLOT` + ogranicznik | −30,4 | 0,008 | −0,87 | −1,13 |
| S3 + `SLOT` + relaksacja 0,3 | −152,1 | 0,079 | −0,65 | −0,77 |
| **S3 + `SLOT` + relaksacja 0,1** | **−150,2** | **0,033** | **−0,70** | **−0,83** |

Ujemna wymiana = netto więcej wody wypłynęło z sieci na powierzchnię (cofka).

Obserwacje:

1. **Naiwne sprzężenie działa tylko bez przeciążenia sieci** (S1). Gdy przewody
   przechodzą w przepływ ciśnieniowy, domyślna metoda `EXTRAN` daje w węzłach skoki
   ciśnienia rzędu metrów z kroku na krok. Jawna wymiana je wzmacnia i obliczenia
   się rozbiegają.
2. **`SLOT` usuwa rozbieżność, ale zostaje cykl graniczny**: wymiana skacze z okresem
   3 kroków (±0,17 m³/s w J3 w S2), gdy ciśnienie w węźle jest bliskie poziomowi wody.
   Masa jest zachowana, objętości skumulowane są wiarygodne, ale chwilowe przepływy nie.
3. **Ogranicznik wyrównania jest fałszywym tropem.** W S2 tłumi oscylacje, ale w S3
   zmniejsza wypływ z sieci pięciokrotnie (−30 zamiast ~−150 m³). Zakłada, że
   ciśnienie w węźle spada, gdy woda z niego wypływa. Przy cofce ciśnienie trzyma
   rzeka, więc to założenie jest fałszywe.
4. **Relaksacja w = 0,1 jest najlepszym prostym stabilizatorem.** Amplituda oscylacji
   spada ponad dziesięciokrotnie, a skumulowane objętości zgadzają się z wariantem
   bez stabilizacji (S2: 95,8 vs 95,6 m³; S3: −150,2 vs −151,8 m³). **Nie usuwa
   oscylacji całkowicie**: zostaje łagodna fala o okresie ok. 6 s (rys. 1, 2).

![Wymiana w J3, S2](figures/fig1_s2_exchange_J3.png)

![Wymiana w J2, S3](figures/fig2_s3_exchange_J2.png)

### 3.3 Wrażliwość na krok wymiany (wariant zalecany)

| | Δt_c = 1 s | 5 s | 30 s |
|---|---|---|---|
| S2: wymiana razem [m³] | 95,8 | 95,5 | 46,8 |
| S3: wymiana razem [m³] | −150,2 | −135,8 | −158,2 |
| S3: J2 / J3 [m³] | +4,1 / −168,2 | −10,7 / −138,9 | −73,1 / −83,5 |

- S2: wyniki dla 1 s i 5 s różnią się o 0,3%. Przy 30 s sieć przejmuje o połowę mniej
  wody. To strukturalna granica schematu jawnego: w jednym kroku do sieci może wpłynąć
  tylko woda obecna w komórce na początku kroku.
- S3: suma jest podobna, ale **rozkład między węzłami nie jest zbieżny** już przy 5 s.
  Dla cofki trzeba krótkiego kroku (≤ 1 s) albo lepszego schematu.

![Wrażliwość na krok wymiany](figures/fig4_interval_sensitivity.png)

### 3.4 Porównanie z koncepcyjnym drenażem SFINCS-a

| Scenariusz | Woda na powierzchni na końcu [m³] | Maks. głębokość [m] | Powierzchnia z głębokością > 5 cm [m²] |
|---|---|---|---|
| S0, bez odprowadzenia | 168,0 | 0,358 | 1044 |
| S0K, koncepcyjny 30 mm/h | 58,9 | 0,270 | 532 |
| S1, sieć, swobodny odpływ | 69,6 | 0,302 | 688 |
| S2, sieć przeciążona | 72,2 | 0,314 | 748 |
| S3, cofka | 318,2 | 0,448 | 1604 |

Moduł koncepcyjnego drenażu (`urban_drainage`) jest na gałęzi głównej SFINCS-a od
2026-09-23 i nie wszedł jeszcze do żadnego wydania (ostatnie: v2.4.1, 2026-08-18).

Model koncepcyjny odbiera wodę tam, gdzie spadła. Sieć odbiera ją tylko we wpustach,
część wody je omija i gromadzi się niżej (rys. 3). Przy cofce sieć wprowadza na
powierzchnię wodę z odbiornika (278 m³ wpłynęło wylotem). Tego wbudowany model
koncepcyjny w tej postaci (bez wylotu) nie odtwarza. Bilans S0K nie był niezależnie
weryfikowany (objętość drenażu nie była odczytywana z wyników SFINCS-a).

![Maksymalna głębokość](figures/fig3_max_depth.png)

### 3.5 Dopływ powierzchniowy: stany ustalone

**Stan ustalony jest osiągany na każdym stopniu.** Dopływ − suma wymiany − odpływ
dolną krawędzią ≤ 0,0004 m³/s we wszystkich przebiegach.

**Bilans.** Błąd po stronie powierzchni wynosi −0,045 m³ we wszystkich przebiegach,
tyle samo co w Q0 bez sieci. Błąd po stronie sieci jest równy błędowi ciągłości
raportowanemu przez SWMM (zgodność do 0,03 m³).

Wymiana w stanie ustalonym, ostatni stopień (0,15 m³/s), średnia ± odchylenie [m³/s]:

| Przebieg | J1 | J2 | J3 | Suma |
|---|---|---|---|---|
| Q1 zalecany (sieć swobodna) | +0,0308 ± 0 | +0,0284 ± 0 | +0,0238 ± 0 | +0,083 |
| Q2 naiwny (`EXTRAN`) | rozbieżny | | | |
| Q2 `SLOT` | +0,0308 ± 0 | +0,0284 ± 0 | **−0,0251 ± 0,1353** | +0,034 |
| Q2 zalecany | +0,0308 ± 0 | +0,0284 ± 0 | −0,0250 ± 0,0083 | +0,034 |
| Q2 zalecany, `Δt_c` = 5 s | +0,0299 ± 0 | +0,0276 ± 0 | −0,0232 ± 0,0040 | +0,034 |
| Q2 zalecany, krok SWMM 0,5 s | | | −0,025 ± 0,0017 | |
| Q2 zalecany, krok SWMM 0,25 s | | | **−0,025 ± 0,0000** | |
| Q3 `SLOT` (cofka) | +0,0308 ± 0 | +0,0133 ± 0,1274 | −0,2698 ± 0,0004 | −0,226 |
| Q3 zalecany (cofka) | +0,0308 ± 0 | +0,0108 ± 0,0187 | −0,2689 ± 0,0016 | −0,227 |

Obserwacje:

1. **Węzły bez przeciążenia są idealnie stabilne** (odchylenie 0) we wszystkich
   wariantach. Problem dotyczy wyłącznie węzłów w przepływie ciśnieniowym.
2. **Oscylacja w `SLOT` jest czysto numeryczna.** W J3 jej odchylenie (0,135 m³/s) jest
   ponad 5 razy większe niż sama średnia wymiana (−0,025 m³/s).
3. **Relaksacja zachowuje średnią** (−0,0250 vs −0,0251 m³/s) i zmniejsza odchylenie
   16-krotnie.
4. **Resztkowa oscylacja wynika z kroku obliczeniowego SWMM.** Przy kroku SWMM
   0,25 s (wymiana nadal co 1 s) znika całkowicie, a średnia się nie zmienia.
5. **Wynik fizycznie spójny.** W Q2 suma wymiany na stopniach 0,10 i 0,15 m³/s jest
   taka sama (0,034 m³/s): sieć jest nasycona, nadmiar wody wybija w J3 i spływa po
   powierzchni. Tego zachowania nie da się odtworzyć redukcją opadu.
6. **Błąd ciągłości SWMM przy długotrwałym przeciążeniu wynosi ok. 3%** (Q2) i nie
   maleje z krokiem SWMM (3,11% przy 1 s, 3,13% przy 0,25 s). Interfejs sprzężenia go
   nie powoduje (błąd po stronie powierzchni pozostaje −0,045 m³), ale jego przyczyna
   w SWMM nie jest wyjaśniona. Możliwe źródła to metoda `SLOT` albo obsługa ujemnego
   wpływu bocznego w węźle pod ciśnieniem.

![Wymiana w J3, Q2](figures/fig5_q2_exchange_J3.png)

## 4. Wnioski

1. Sprzężenie SFINCS–SWMM przez istniejące BMI SFINCS-a jest **wykonalne bez zmian
   w kodzie żadnego z modeli**.
2. Wymiana objętości liczonych z faktycznego czasu SFINCS-a zapewnia **dokładne
   zachowanie masy na interfejsie** mimo adaptacyjnego kroku SFINCS-a.
3. Stabilność decyduje o użyteczności. Działający zestaw w tym teście to `SLOT`
   w SWMM + relaksacja wymiany (w ≈ 0,1) + `Δt_c` ≈ 1 s. Krok obliczeniowy SWMM
   0,25 s usuwa resztkową oscylację w stanie ustalonym (p. 3.5). Zachowanie przy
   szybko zmiennych przepływach wymaga jeszcze sprawdzenia.
4. Test z dopływem powierzchniowym i stanami ustalonymi jest lepszym testem
   sprzężenia niż opad: oscylacje są jednoznaczne, a wynik da się porównać
   z eksperymentem laboratoryjnym.
5. Kolejny krok badawczy: schemat odporny na cykl graniczny (np. iteracja
   w obrębie kroku albo ogranicznik oparty na zmierzonej odpowiedzi węzła zamiast
   założonej powierzchni) i walidacja na danych laboratoryjnych podwójnego drenażu.

## 5. Ograniczenia

- Jedna domena idealizowana, jeden opad, jedna komórka na węzeł wymiany.
- Tryb regularny SFINCS-a. W trybie subgrid głębokość przy wpuście trzeba liczyć
  względem `subgrid_z_zmin`, a nie `zb`; nie testowane.
- Współczynniki przelewu i otworu (0,4 i 0,6 dla kratki 0,5 × 0,5 m) przyjęte bez
  kalibracji. Jedyny zestaw skalibrowany dla studzienki (Rubinato i in. 2017,
  J. Hydrol., doi:10.1016/j.jhydrol.2017.06.024) to ok. 0,54 (przelew swobodny),
  0,056 (przelew zatopiony) i 0,167 (otwór), odniesione do powierzchni i obwodu
  włazu. Szczegóły: `reports/`.
- W większości przebiegów krok SFINCS-a był ograniczony przez `dtmax` (stałe 0,5 s).
  Przestrzał czasu był realnie testowany tylko w S3 (do 0,5 s).
- Tylko Linux; kompilacja `libsfincs.so` na Windows i macOS niesprawdzona.
- Czas obliczeń zmierzony na bardzo małej domenie, niereprezentatywny.
- Przegląd literatury nie był systematyczny. Przed tezą o nowości trzeba go wykonać.
- Błąd ciągłości SWMM przy długotrwałym przeciążeniu (ok. 3%) ma niewyjaśnioną przyczynę.
- Odpływ swobodny w wariancie z dopływem jest konstrukcją koordynatora (odbiór wody
  z ostatniej kolumny), a nie natywnym brzegiem SFINCS-a.

## 6. Obserwacje dla autorów narzędzi

SFINCS (commit `db08c6a`, 2026-10-19):

1. Ujście przez `qext` większe niż woda w komórce **po cichu tworzy masę**: poziom
   jest obcinany do dna (`max(..., zb)` w `sfincs_continuity.f90`), a nadmiar nie jest
   nigdzie rejestrowany. W rozbieżnych przebiegach po stronie powierzchni pojawiło się
   do 140 m³ wody spoza bilansu (S0 bez sprzężenia: 0,035 m³), najpewniej z tego
   mechanizmu.
   Wbudowany moduł `urban_drainage` sam się przed tym zabezpiecza, interfejs BMI nie
   i nigdzie o tym nie informuje.
2. `update_until`: opis mówi o długości przedziału, kod traktuje argument jako czas
   bezwzględny. Cel w przeszłości (`t_target ≤ t`) wykonuje jeden krok zamiast
   niczego (gałąź `dtrange <= 0`).
3. Ostatni krok `update_until` nie jest przycinany do celu (przestrzał do jednego kroku).
4. Domyślne `dtmax` = 60 s: na suchej domenie pierwszy krok wynosi 30 s.
5. Jednostka `qext` zmieniła się niedawno z m/s na m³/s (komentarz w `sfincs_bmi.f90`).
6. `make -j4` przerywa się na zależnościach modułów Fortrana; `make` przechodzi.

pyswmm 2.2.0 / SWMM 5.2.4:

7. `SystemStats.routing_stats["final_storage"]` jest zwracane w ft³ mimo
   `FLOW_UNITS CMS` (0,796 m³ ↔ 28,11; ×35,31). Pozostałe pola są w m³.
8. `step_advance` przyjmuje tylko całe sekundy.

## 7. Odtworzenie

Wersje: SFINCS `db08c6a37a956e1a9b14b6f3c65c05834b2b80ce`, pyswmm 2.2.0
(swmm-toolkit 0.17.0, silnik SWMM 5.2.4), gfortran 13.3, netCDF-Fortran 4.5.4,
Python 3.13.

```bash
# 1. SFINCS jako biblioteka współdzielona
git clone https://github.com/Deltares/SFINCS.git && cd SFINCS/source
git checkout db08c6a37a956e1a9b14b6f3c65c05834b2b80ce
autoreconf -if && ./autogen.sh
./configure FC=gfortran --enable-shared --prefix=<katalog-instalacji> \
  FCFLAGS="-fopenmp -O2 -fallow-argument-mismatch -w -fPIC" \
  FFLAGS="-fopenmp -O2 -fallow-argument-mismatch -w -fPIC"
make && make install

# 2. Środowisko Pythona
python -m venv .venv && .venv/bin/pip install pyswmm==2.2.0 numpy matplotlib

# 3. Scenariusze i wykresy (z tego katalogu)
SFINCS_LIBRARY=<katalog-instalacji>/lib/libsfincs.so .venv/bin/python run_all.py
.venv/bin/python plots.py
```

| Plik | Rola |
|---|---|
| `case_setup.py` | geometria, wymuszenia, sieć, macierz scenariuszy |
| `coupler.py` | koordynator: wrapper BMI SFINCS-a, wzory wymiany, bilans |
| `run_all.py` | uruchamia każdy scenariusz w osobnym procesie |
| `plots.py` | rysunki do `figures/` |
| `results/summary.json` | wyniki wszystkich scenariuszy |
