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
  Odpływ z dachów jest zmierzony, więc można go podać wprost do SWMM.
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
