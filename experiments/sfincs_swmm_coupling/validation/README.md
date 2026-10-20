# Dane do walidacji sprzężenia SFINCS–SWMM

Stan na 2026-10-20. Notatka zbiera to, co trzeba wiedzieć o przypadkach
walidacyjnych, zanim zbudujemy na nich model. Zawiera specyfikację,
wyniki odniesienia i informację, skąd wziąć dane.

## 1. Test 8B Environment Agency

**Źródło:** Néelz S., Pender G. (2013) *Benchmarking the latest generation
of 2D hydraulic modelling packages*. Environment Agency, raport SC120002,
rozdz. 4.10 i dodatek A.9. Wcześniejsza wersja testu: SC080035 (2010),
rozdz. 4.8. Raporty są publicznie dostępne na
<https://www.gov.uk/government/publications/benchmarking-the-latest-generation-of-2d-hydraulic-flood-modelling-packages>.

**Czego dotyczy:** wybicie wody z przeciążonego przewodu przez jedną
studzienkę i rozpływ tej wody po terenie. Ten benchmark porównuje modele
między sobą. Pomiarów w nim nie ma, więc zgodność z innymi pakietami nie
oznacza zgodności z rzeczywistością.

### Specyfikacja (dodatek A.9)

| Element | Wartość |
|---|---|
| Obszar | ok. 0,4 × 0,96 km (0,388 km²), teren 21–37 m n.p.m. |
| NMT | 0,5 m, LiDAR bez budynków i roślinności (`Test8DEM.asc`) |
| Siatka obliczeniowa | 2 m (ok. 97 000 komórek) |
| Budynki | obrysy w danych; rzędna dachu dowolna, co najmniej 1 m nad terenem |
| Szorstkość | n = 0,02 na drogach i chodnikach, 0,05 w pozostałych miejscach |
| Brzegi domeny 2D | zamknięte, stan początkowy suchy |
| Przewód | kołowy, D = 1,4 m, dł. ok. 1070 m, dno 2 m pod terenem na całej długości |
| Dopływ do przewodu | hydrogram Q(t) z danych (`Test8B-pipe-inflow.csv`): przepływ bazowy 1,6 m³/s, szczyt ok. 6,3 m³/s w ok. 120 min (odczyt z rys. A.16) |
| Warunek na dole przewodu | wylot swobodny (przepływ krytyczny) |
| Warunek początkowy w przewodzie | przepływ ustalony 1,6 m³/s |
| Studzienka | pionowa, przekrój 1 m², 467 m od początku przewodu, połączona z siatką 2D w jednym punkcie; wierzch na 31,46 m n.p.m. (podaje zespół SOBEK) |
| Sprzężenie wg specyfikacji | „przepływ powierzchniowy nie wpływa na wypływ ze studzienki” |
| Czas symulacji | 5 h |
| Wyniki | wypływ ze studzienki co 30 s; poziom i prędkość co 30 s w 9 punktach (`Test8Output.csv`); rastry maks. poziomu i głębokości |

Uwaga: studzienka leży w zagłębieniu terenu. Woda musi podnieść się do
ok. 31,86 m n.p.m., zanim wypłynie dalej (zespół SOBEK).

### Wyniki odniesienia (SC120002, tab. 4.11 i rys. 4.46)

Objętość wypływu ze studzienki:

| Pakiet | Objętość [m³] |
|---|---|
| TUFLOW | 5840 |
| InfoWorks ICM | 5653 |
| ISIS Fast | 5569 |
| ISIS Fast Dynamic | 5234 |
| UIM | 5227 |
| ISIS 2D | 5058 (5075 w modelu połączonym dynamicznie) |
| MIKE FLOOD | 5033 |
| SOBEK | 4987 |
| XPSTORM | 4954 |

Przebieg wypływu (odczyt z rysunku, dokładność ok. ±2 min i ±0,05 m³/s):
- początek wybicia w 82–87 min;
- szczyt 2,0–2,2 m³/s w ok. 120 min;
- koniec wybicia w ok. 155 min;
- potem krótki przepływ wsteczny do przewodu, do ok. −0,3 m³/s w ok. 160 min.

Przepływ wsteczny pojawia się mimo zapisu w specyfikacji. Większość
pakietów liczyła więc wymianę w obu kierunkach.

Poziom w zagłębieniu w punkcie 3 na końcu symulacji: przy głębokości
ok. 0,7 m rozrzut między modelami wynosi ok. 0,08 m. Prędkości różnią się
między modelami nawet o 50%.

### Dostępność danych

Na stronie GOV.UK są tylko raporty. Archiwum `LIT_8570_a3d694.zip` zawiera
dwa pliki PDF (raport i streszczenie SC120002), bez danych.

Według zgłoszenia TUFLOW (2012) zbiór danych wydaje Environment Agency na
prośbę wysłaną na adres `fcerm.evidence@environment-agency.gov.uk`. Ten
adres pochodzi z 2012 r. i nie wiadomo, czy nadal działa.

Prawdopodobny powód: NMT pochodzi z danych LiDAR EA (Geomatics), więc jego
redystrybucja może być ograniczona. To przypuszczenie, nie potwierdzona
informacja.

Model Itzï (2D + SWMM, open source) również był testowany na teście 8A,
ale w jego repozytorium (`ItziModel/itzi`) nie ma danych EA.

### Plan odwzorowania w SFINCS–SWMM (do zatwierdzenia po pozyskaniu danych)

- **SFINCS:** siatka 2 m z NMT 0,5 m (uśrednienie, opcjonalnie tablice
  podsiatkowe), budynki podniesione o 1 m, mapa szorstkości 0,02/0,05,
  maska bez komórek brzegowych.
- **SWMM:**
  - jeden przewód podzielony studzienką na dwa odcinki;
  - wysokości terenu wzdłuż trasy z `Test8BPipeGeometry.xls`;
  - dopływ z `Test8B-pipe-inflow.csv`, interpolacja liniowa;
  - wylot swobodny;
  - przepływ początkowy 1,6 m³/s.
- **Sprzężenie:** wariant zalecany do screeningu (wybicie liczone przez
  SWMM, SurDepth = 0, `EXTRAN`). Dwa przebiegi:
  - (a) bez powrotu wody, zgodnie ze specyfikacją;
  - (b) z powrotem wody wzorami v2, A = 1 m², obwód przelewu 4 m.
- **Porównanie:**
  - objętość wypływu z tab. 4.11;
  - przebieg wypływu z rys. 4.46;
  - poziomy w punktach 1–3;
  - czas obliczeń.

## 2. Dane laboratoryjne (pomiary)

| Zbiór | Co zawiera | Gdzie | Licencja |
|---|---|---|---|
| A Coruña, CITEEC: Sañudo i in. (2024), *Hydrol. Processes* 38(1), doi:10.1002/hyp.15068 | ulica 100 m² (skrzyżowanie w kształcie T) połączona z kanalizacją, symulator deszczu; geometria, NMT, wpusty, studzienki, wylot, wyniki | Zenodo, doi:10.5281/zenodo.7941067 | CC BY 4.0 |
| WASHTREET (ten sam ośrodek) | hydraulika, spłukiwanie i transport osadów | Zenodo 3256325, 3754092, 3935914 (wersje), 3241337 (NMT z fotogrametrii) | CC BY 4.0 |
| Sheffield: Martins i in. (2018) | stały przepływ przez 10 typów kratek, pola prędkości PIV | Zenodo 2605134 | CC BY 4.0 |

### 2.1 A Coruña (Zenodo 7941067): co zawiera zbiór

Pobrane 2026-10-20, sumy MD5 zgodne z Zenodo. Bez archiwum multimediów.

- **Powierzchnia:** NMT `SURFACE.asc`, oczko 5 cm, 306 × 99 komórek,
  ok. 64 m², rzędne 2,59–3,12 m.
  - Ulica: dwie jezdnie po 2,5 m i chodniki po 30 cm.
  - Krawężnik 6 cm.
  - Spadek poprzeczny 2%, podłużny 1%.
  - Dachy mają osobne NMT z oczkiem 5 mm.
- **Deszcz:** symulator, mapy natężenia dla 30, 50 i 80 mm/h (oczko 5 cm).
  - Mapy mają lokalnie wartości ujemne (artefakty interpolacji).
  - Hietogramy:
    - H1–H3: deszcz stały przez 240 s;
    - H4–H5: przerywany;
    - H6: zmienny.
  - W serii 2 (T07–T12) dochodzi dopływ 1 L/s z każdego z dwóch
    generatorów spływu (SD1, SD2).
- **Kanalizacja:** współrzędne, rzędne dna i topologia w tab. 3 opisu.
  - 4 studzienki, przewód główny 240 mm, poprzeczny 194 mm.
  - Wylot przez przelew trójkątny.
- **Wpusty:**
  - cztery kratki 0,5 × 0,2 m, każda połączona z najbliższą studzienką;
  - kratka poprzeczna 2,5 × 0,13 m.
  - Prześwit kratek nie jest podany.
- **Dachy:** woda trafia rynną do wpustów dachowych i dalej do studzienek.
  Zapisy odpływu z dachów w testach blokowych są niespójne (p. 3.1), więc
  nie nadają się na dane wejściowe.
- **Pomiary:** baza SQLite, testy T01–T12, 600 s, krok 0,2 s:
  - przepływ przez wpusty 1–4 (szeregi czasowe);
  - wpust 5 i dopływy do studzienek tylko jako wartości ustalone dla H1–H3;
  - odpływ z sieci;
  - odpływ z dachów;
  - głębokości w 9 punktach ulicy (0,2–14 mm).
- **Jednostki:** nagłówki kolumn podają `[m3/s]`, ale wartości są w L/s.
  Sprawdzenie dla T03 (80 mm/h przez 240 s):
  - opad na mapie natężenia to ok. 480 L;
  - suma odpływu przy założeniu L/s to ok. 460 L;
  - przy założeniu m³/s wyszłoby 460 m³, co jest niemożliwe.

Czego ten zbiór nie testuje: wybicia z sieci. Przepływy rzędu kilku L/s nie
wypełniają przewodów, więc wymiana idzie tylko z powierzchni do sieci.

### 2.2 Sheffield (Zenodo 2605134): co zawiera zbiór

Martins i in. (2018), *Water Resources Research*, doi:10.1029/2018WR022782.

- Model w skali 1:6 z jedną studzienką.
- 10 konfiguracji kratek (8 wzorów, dwa z nich testowane także po obrocie
  o 90°).
- Stały przepływ powierzchniowy 2,75–10 L/s.
- Zmierzony stały przepływ przez kratkę (`FlowExchangeGrate*.csv`).
- Pola prędkości PIV wokół kratki.

Wymiana idzie tylko z powierzchni do sieci. Zbiór nadaje się do
sprawdzenia samego wzoru wpustu (przejście z przelewu na otwór), nie do
testu dynamiki sprzężenia.

Rekord 1464864 zawiera tylko PDF artykułu (Rubinato i in. 2018,
*J. Hydroinformatics*), bez danych pomiarowych.

### 2.3 Wniosek

Żaden z otwartych zbiorów pomiarowych nie obejmuje wybicia z sieci w
warunkach nieustalonych.

- A Coruña sprawdza kierunek z powierzchni do sieci w pełnym łańcuchu:
  opad → spływ → wpusty → sieć → wylot.
- Wybicie sprawdza tylko test 8B EA. To porównanie modeli, a dane są
  dostępne na prośbę.

## 3. Test A Coruña: model i wyniki

Kod: `coruna/` (`coruna_setup.py`, `run_coruna.py`, `run_all.py`,
`compare.py`). Tabele: `coruna/results/`. Rysunki: `coruna/figures/`.

### 3.1 Model

- **Powierzchnia SFINCS:** ulica i chodniki z NMT 5 cm, 19 766 komórek,
  49,4 m².
  - Szorstkość n = 0,016, próg suchej komórki 0,1 mm, `dtmax` 0,2 s.
  - Adwekcja pędu włączona; w tej wersji SFINCS jest domyślna.
- **Dachy pominięte.** Odprowadzają wodę rynnami prosto do studzienek, więc
  nie biorą udziału w wymianie ulica–sieć. Ich zapisy w testach blokowych
  są niespójne:
  - w T01–T03 odpływ z dachu trwa ok. 115 s, choć deszcz trwa 240 s;
  - zawiera tylko ok. 45% wody, która spadła na dach;
  - w T06–T12 zapisów nie ma.

  Dlatego odpływ z sieci porównuję tylko tam, gdzie woda z dachów do niego
  nie trafia: w serii 2 przed deszczem.
- **Deszcz:**
  - hietogramy H1–H6 odczytane z rysunku w opisie zbioru;
  - natężenie równomierne; mapa natężenia jako wariant wrażliwości;
  - początek deszczu 130 s. Zbiór go nie podaje, więc oszacowałem go
    z odpowiedzi zmierzonej.
- **Generatory SD1 i SD2** (seria 2): po 1 L/s rozłożone w 10 punktach na
  szerokości jezdni. Opis nie podaje, jak wyglądają urządzenia. Przed
  początkiem zapisu model ma 300 s rozbiegu, żeby przepływ się ustalił.
- **Sieć SWMM:** z warstw autorów zbioru (w tym n = 0,005), wylot swobodny,
  `EXTRAN`, SurDepth = 0.
- **Sprzężenie:** wariant zalecany do screeningu (README p. 4) z jedną
  zmianą: kratka zbiera wodę ze wszystkich komórek pod sobą.
  - Kratka 0,5 × 0,2 m to 40 komórek, kratka poprzeczna 150.
  - Głębokość nad kratką = średnia z tych komórek.
  - Wzór przelew/otwór (v2), z obwodem i polem kratki.
  - Wymiana co 0,2 s, SWMM co 1 s.
- **Dwa warianty współczynników:**
  - bez kalibracji: współczynniki z testu wykonalności;
  - skalibrowany: oba współczynniki × 0,07, dobrane na stanie ustalonym
    serii 2 (p. 3.4).

### 3.2 Bilans i koszt obliczeń

- **Bilans powierzchni:** błąd poniżej 0,01 L na 260–2060 L wody, we
  wszystkich 45 przebiegach.
- **Bilans sieci:** do −2,8 L (0,14%) przy dopływie z generatorów. SWMM sam
  raportuje błąd 0,000%, więc różnica pochodzi raczej z odczytu objętości
  w sieci przez pyswmm. Nie wyjaśniłem jej do końca.
- **Wybicie:** nie wystąpiło. Przewody są wypełnione w niewielkim stopniu.
- **Czas:** 40–98 s na test (900 s symulacji, oczko 5 cm). Przy oczku 10 cm
  8–12 s, z praktycznie tymi samymi wynikami (p. 3.6).

### 3.3 Co mówią same pomiary

1. **Seria 2 przed deszczem (stan ustalony):**
   - z generatorów wpływa 2 L/s, a odpływ z sieci to 2,05–2,13 L/s, więc
     bilans się zamyka;
   - kratki 1–4 łapią razem 1,18 L/s, a 0,91 L/s przepływa nad nimi do
     kratki końcowej IN5;
   - sześć powtórzeń tego stanu różni się o 0,005–0,035 L/s (odch. std.).
2. **Seria 1 w stanie ustalonym deszczu (T01–T03):** suma przepływu przez
   kratki 1–5 to 78–83% deszczu spadającego na modelowaną powierzchnię.
   - Brakujących 17–22% nie umiem przypisać. Możliwe przyczyny: straty,
     mniejsze natężenie nad ulicą niż na mapach, błąd pomiaru.
   - Model odprowadza do kratek cały deszcz, więc tu musi zawyżać sumę.

### 3.4 Kalibracja na stanie ustalonym (seria 2 przed deszczem)

Rys. `fig_coruna_calibration.png`, tabela `results/calibration.md`.

- **Bez kalibracji** kratki 1–4 łapią 1,99 z 2 L/s, a do IN5 trafia
  0,01 L/s (pomiar: 0,91). RMSE przepływów IN1–IN5 wynosi 0,46 L/s.
- **Skanowanie mnożnika** (1 … 0,05) daje najmniejszy błąd przy 0,07:
  RMSE 0,095 L/s.
- Po kalibracji zostaje błąd kratki 1: 0,23 L/s w modelu wobec 0,43 L/s
  w pomiarze. Jeden mnożnik nie dopasowuje wszystkich kratek naraz.

### 3.5 Sprawdzenie na testach z deszczem

Rys. `fig_coruna_set1.png` i `fig_coruna_set2.png`, tabela
`results/validation.md`.

- Seria 1: cała odpowiedź na deszcz.
- Seria 2: przyrost ponad przepływ z generatorów.
- Mediany z 6 testów × 4 kratek. Przesunięcie = środek ciężkości hydrogramu
  w modelu minus w pomiarze.

| Miara | Bez kalibracji | Skalibrowany (×0,07) |
|---|---|---|
| Stan ustalony serii 2: RMSE przepływów IN1–IN5 | 0,46 L/s | **0,095 L/s** |
| Seria 1, podział wody między kratki w deszczu stałym (T01–T03): RMSE udziałów | **4,6–7,4 p.p.** | 11,7–17,6 p.p. |
| Seria 1: objętość model/pomiar | 1,43 | 1,00 |
| Seria 1: NSE | 0,53 | 0,57 |
| Seria 1: przesunięcie | +15 s | +36 s |
| Seria 2, przyrost od deszczu: objętość model/pomiar (IN2–IN4) | **1,12** | 0,43 |
| Seria 2: NSE | **0,60** | 0,11 |
| Seria 2: przesunięcie | −7 s | −9 s |

Wnioski:

1. **Czas odpowiedzi model oddaje dobrze.**
   - W serii 2, gdzie ulica jest już mokra od generatorów, przesunięcie jest
     bliskie zera.
   - W serii 1 model spóźnia się o ok. 15 s. Model startuje z suchej ulicy,
     a w laboratorium była mokra po poprzednim teście. Swoje wnosi też
     niepewność początku deszczu (±10 s).
2. **Kalibracja na stanie ustalonym nie przenosi się na deszcz.** Mnożnik
   0,07 poprawia przepływ z generatorów, ale psuje odpowiedź na deszcz:
   - zbyt dużo wody przepływa nad kratkami 1–4 do IN5;
   - przyrost od deszczu w serii 2 jest zaniżony ponad dwukrotnie;
   - podział wody w serii 1 jest gorszy niż bez kalibracji.

   W laboratorium kratki przepuszczają ok. 45% skupionego przepływu
   z generatorów (1 L/s), ale wodę z deszczu łapią prawie w całości.
3. **Wzór zależny tylko od głębokości z jednym współczynnikiem nie opisuje
   kratki ulicznej w obu warunkach.** Skuteczność kratki zależy od
   przepływu i prędkości dopływu: woda szybka przeskakuje nad kratką.
   Tak działają zależności skuteczności kratki z podręczników projektowania
   ulic, np. HEC-22 (FHWA), z podziałem na przepływ czołowy i boczny oraz
   prędkością przeskoku.
   - W screeningu w siatce 2–5 m kratka jest mniejsza od komórki, więc jej
     prawo wymiany i tak jest parametryzacją.
   - Wniosek dla Hydraulika: współczynnik wpustu trzeba traktować jako
     niepewny, zależny od warunków dopływu, i pokazywać zakres wyników,
     a nie jedną wartość.
4. **Bez kalibracji model dobrze dzieli wodę między kratki** (RMSE udziałów
   5–7 p.p.).
   - Sumę przepływu przez wszystkie kratki zawyża o 21–29%, a prawie całą tę
     różnicę wyjaśnia niedobór wody w samych pomiarach (p. 3.3).
   - Objętości poszczególnych kratek 1–4 różnią się bardziej (mediana +43%),
     bo model kieruje za dużo wody do IN1 i IN3, a za mało do IN4.
5. **Głębokości w punktach pomiarowych nie nadają się do oceny.**
   - Model daje w rynsztoku 1,5–4 razy większe głębokości niż pomiar.
   - Mierzone głębokości to 0,5–11 mm. To wielkości porównywalne
     z dokładnością NMT z kamery LiDAR (rzędu milimetrów) i z różnicą rzędnych
     w obrębie jednej komórki 5 cm.
   - Wynik nie przesądza ani o błędzie modelu, ani o jego braku.

### 3.6 Wrażliwość (wariant skalibrowany, T03 i T09)

Tabela `results/sensitivity.md`.

| Zmiana | Przepływ przez kratki 1–4 w stanie ustalonym |
|---|---|
| oczko 10 cm zamiast 5 cm | −4–5% (czas 8× krótszy) |
| krok wymiany 1 s zamiast 0,2 s | 0% |
| n = 0,012 / 0,020 zamiast 0,016 | −11% / +9% (T03) |
| próg suchej komórki 1 mm zamiast 0,1 mm | +6–8%, gorsze NSE w T03 |
| zmierzona mapa deszczu zamiast natężenia równomiernego | +0–4% |
| głębokość nad kratką: maksimum zamiast średniej | **+42–53%** |

- **Definicja głębokości nad kratką** zmienia wynik tak mocno jak
  współczynnik wpustu. To kolejny argument, że opis wpustu jest głównym
  źródłem niepewności sprzężenia (wcześniej: porównanie z D-Flow FM,
  README p. 3.7 i 3.9).
- **Krok wymiany i oczko siatki** prawie nie mają znaczenia, a ostateczne
  wnioski się od nich nie zmieniają.

### 3.7 Ograniczenia testu

- **Brak wybicia z sieci:** test sprawdza tylko kierunek z ulicy do sieci.
- **Założenia własne:**
  - początek deszczu oszacowany z danych;
  - szerokość hietogramu H6 odczytana z rysunku (±5 s);
  - położenie i budowa generatorów przyjęte;
  - prześwit kratek nieznany.
- **Brakująca woda w pomiarach:** w serii 1 brakuje 17–22% wody; przyczyny
  nie ustaliłem.
- **Kratka IN5:** zmierzona tylko jako jedna wartość ustalona (T01–T03),
  a w serii 2 wyznaczona z bilansu.
- **Brak porównania z modelem autorów:** artykułu Sañudo i in. (2024) z ich
  modelem Iber–SWMM nie mogłem pobrać (wiley.com zablokowany w tym
  środowisku).

### 3.8 Odtworzenie

```bash
# dane: https://doi.org/10.5281/zenodo.7941067, rozpakowane archiwa
# 02_Geometries, 03_Rain_intensity_maps, 04_Digital_Elevation_Models,
# 06_Hydraulic_tests_database do jednego katalogu <dane-coruna>
cd coruna
export CORUNA_DATA=<dane-coruna> SFINCS_LIBRARY=<katalog-instalacji>/lib/libsfincs.so
python run_all.py            # 45 przebiegów, 4 równolegle, ok. 15–20 min
python compare.py            # tabele results/*.md i rysunki figures/*.png
```
