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
| WASHTREET (ten sam ośrodek) | hydraulika, spłukiwanie i transport osadów | Zenodo 3935914 i rekordy powiązane | do sprawdzenia |
| Sheffield: Rubinato i in. | wymiana w obu kierunkach przez studzienkę, model fizyczny | Zenodo (rekordy wskazane w przeglądzie literatury) | do sprawdzenia |

Wszystkie te zbiory są na Zenodo. Z tego środowiska Zenodo jest na razie
niedostępne, bo sieć odrzuca połączenie.

Pod względem metody zbiór z A Coruña jest bardziej wartościowy niż test 8B.
Zawiera zmierzone przepływy przez wpusty i studzienki, czyli dokładnie to,
co liczy sprzężenie.
