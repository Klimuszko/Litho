# Review techniczny: nieokrągły fidget planetarny 0.2 (po naprawach)

Data: 2026-09-30. Przedmiot: gałąź `Main_Frame` @ `68d86c6` („Validate and compact noncircular gear profiles”),
czyli `aa205d1` + `68d86c6` względem stanu z poprzedniego review (`91fef41`, raport
`docs/noncircular-fidget-review.pl.md`).
Zakres: `examples/scad/planetary-fidget-noncircular/`, `tools/noncircular-oracle/`,
`docs/noncircular-fidget-plan.pl.md`, integracja z `frontend/src/scadWasm.worker.ts` i limitem importu backendu.

Review przeprowadzono od zera. Kodu nie zmieniano. Wszystkie wnioski geometryczne opierają się na **niezależnych
skryptach**, które nie importują oracle. Skrypty czytają dokładnie dane z `lib/ncg_profiles.scad`, a więc profile po
radializacji i uproszczeniu, które trafiają do OpenSCAD. Istniejące testy uruchomiono, ale żaden werdykt nie opiera się
tylko na nich.

## Werdykt

| Poziom | Werdykt | Uzasadnienie |
|---|---|---|
| **Code-level** | **GO** (warunkowe) | K1–K6 i W1 naprawione. Niezależna symulacja pełnego cyklu na eksportowanych profilach nie wykazała żadnej kolizji ani zakleszczenia dla 2 kształtów × 3 profili dopasowania × 3 faz stopni. Nie ma otwartych błędów krytycznych ani wysokich. Zostają ustalenia średnie N1–N5 (poniżej); nie blokują one prototypu. |
| **Prototype-print** | **GO** | Wydruk kuponów F1/F11 oraz prototypów F2 (kwadrat) i F4 (trójkąt) ma teraz sens: geometria jest kinematycznie poprawna i ma retencję osiową. Zalecam zacząć od profilu „Standardowy” lub „Luźny”. Wydruk rozstrzygnie ryzyka N1–N5, których nie da się zamknąć numerycznie. |
| **Production** | **NO-GO** | Nie wykonano żadnego z testów F1–F11 (`docs/noncircular-physical-tests-protocol.pl.md`: wszystkie „niewykonany”). Testy oracle i smoke WASM nie działają w CI. Zostały też średnie defekty druku (warstwy poza siatką 0,2 mm, niepełna rampa, brak `c_tip`). Sprawności fizycznej **nie deklaruję**. |

## Co uruchomiono

Skrypty review leżą poza repo, w katalogu roboczym sesji (`scratchpad/indep/`). Ich metodę opisano w sekcji „Metoda niezależna”.

| # | Polecenie | Wynik |
|---|---|---|
| 1 | `tools/noncircular-oracle`: `npm test` | 6/6 pass, 127 s (test „4–6” 50,6 s; „profile eksportowane” 76,2 s) |
| 2 | Kopia `tools/noncircular-oracle` w scratchpad → `node generate-scad-data.mjs` | 1 min 52 s, `wrote 3990531 bytes`. Porównanie liczbowe z plikiem w repo: 0 różnic we wszystkich wierzchołkach, identyczna topologia. Różnica 2 bajtów to tylko CRLF. Dane są **odtwarzalne**. |
| 3 | `backend`: `py -3 -m pytest tests/test_scad_parser.py tests/test_scad_repository.py -q` | 13 pass (7,9 s). Z katalogu repo test nie startuje (`No module named 'app'`), trzeba go uruchamiać z `backend/`. |
| 4 | `git diff --quiet 74e8487 HEAD -- examples/scad/planetary-fidget` | pusty diff: klasyczny moduł nietknięty |
| 5 | `git diff --stat 74e8487 HEAD -- frontend backend` | tylko `backend/tests/*` (+14/−2) i `frontend/package.json` (dodany skrypt `test:noncircular-wasm`). `frontend/src` i `backend/app` bez zmian. |
| 6 | `indep/basic.mjs <ncg_profiles.scad>` | liczba zębów, głębokość, samoprzecięcia, kanał, poza montażowa, oddychanie orbity (tabela A) |
| 7 | `indep/sweep.mjs <data> <shape> <fit> 97 1.05` × 6 | pełny cykl + 5% za granicą płatu, 97 pozycji na podziałkę, siatka przesunięta o pół kroku (tabela B) |
| 8 | `indep/static.mjs` | luzy w pozie wydruku (stałe `ncg_mount_*` z SCAD, pierścień 0°) i rzeczywisty min. odstęp planet |
| 9 | `indep/ramp.mjs` | brakujący nawis ostatniego kroku rampy (tabela C) |
| 10 | `indep/tips.mjs` | szerokość głowy zęba 0,15 mm pod wierzchołkiem (P, S) |
| 11 | `indep/wasm.mjs` (ten sam `@lofcz/openscad-wasm`, backend Manifold) × 11 renderów | tabela D |
| 12 | `indep/wasm.mjs -Ddebug_section_z=z` (13 wysokości) + `indep/section.mjs` | porównanie przekrojów SCAD z danymi (tabela E) |
| 13 | ZIP modułu, jak w `seed_bundled_examples` (Python `zipfile`, DEFLATED) | 1 388 508 B po kompresji, 4 002 012 B rozpakowane, limit `LITHO_SCAD_MAX_SOURCE_BYTES` = 10 485 760 B |
| 14 | `ls .github/workflows` | tylko `container-images.yml`: oracle i smoke WASM **nie działają w CI** |

### Metoda niezależna

1. **Dane:** `ncg_profiles.scad` parsowany jako JSON. Użyto wszystkich 18 zestawów (kształt × dopasowanie × faza 0/δ/2δ)
   i wszystkich 6 profili w zestawie (P, S, R oraz kanały P, S, R).
2. **Kinematyka własna:** analityczna krzywa `r = R(1 + e·cos nθ)` z analityczną styczną. Długość łuku liczona kwadraturą
   Gaussa-Legendre’a (20 000 przedziałów) z odwracaniem metodą Newtona. Toczenie bez poślizgu: łuk S = s, łuk P = L/(2n) − s,
   styczne przeciwne. Kod oracle (`poseAtArc`, `solveKinematics`, `chiKin`, `k`) nie jest używany.
3. **Kąt pierścienia bez oracle:** dla każdej pozy kąt ψ pierścienia wyznaczono jako **maksimum minimalnego luzu**
   (skan i złoty podział), jednocześnie dla wszystkich trzech faz stopni, z ciągłym śledzeniem ψ. Sprawdza to
   jednocześnie domknięcie, sprzężenie i spójność trzech warstw jako jednej bryły. Na tym samym ψ sprawdzono wszystkie
   N planet oraz parę S–R.
4. **Miara kolizji:** zamiast pola przecięcia użyto odległości ze znakiem. Każdy wierzchołek jednego ciała jest
   klasyfikowany (wewnątrz/na zewnątrz) względem drugiego i liczona jest odległość do jego brzegu, w obie strony.
   Wynik ujemny oznacza głębokość wniknięcia w mm.
5. **Blokada osiowa:** głębokość wniknięcia `P(faza i)` w `S(faza j)` i w `R(faza j)` dla sąsiednich faz |i − j| = 1,
   w pozie nominalnej. Odpowiada to przesunięciu planety o jeden stopień w osi Z. Ponieważ pasy są lustrzane,
   poza nominalna jest najlepszą dostępną pozą planety.
6. **Siatka:** 97 pozycji na podziałkę, przesunięta o pół kroku. Nie pokrywa się ani z siatką generacji (8 na podziałkę),
   ani z siatką walidacji w repo (64 na podziałkę). Zakres: 1,05 płatu, więc sprawdzone jest też przejście przez
   granicę okresu.

## Tabela A: geometria eksportowanych profili (`basic.mjs`)

| Wielkość | Kwadrat (n = 4) | Trójkąt (n = 3) |
|---|---|---|
| R / L centroidy / z / m | 12,805 / 81,002 / 24 / 1,0743 | 12,705 / 80,263 / 27 / 0,9462 |
| Zęby P / S / R policzone na obrysie | **24 / 24 / 72** (wszystkie 9 zestawów) | **27 / 27 / 81** (wszystkie 9 zestawów) |
| Planeta `r − r_centroidy` | −1,096 … +1,136 mm (głębokość 2,23 mm ≈ 2,08 m) | −0,966 … +0,998 mm |
| Koło centralne `r − r_c` (Ciasny / Std / Luźny) | −1,261…0,972 / −1,313…0,919 / −1,377…0,858 | −1,122…0,841 / −1,175…0,790 / −1,234…0,729 |
| Samoprzecięcia (wszystkie pierścienie, 18 zestawów) | 0 | 0 |
| Promienie z > 1 przecięciem planety (utrata podcięć przez radializację) | 0/3600 | 0/3600 |
| Kanał P: max `r − r_c` / odległość do uzębienia | −1,80 mm / ≥ 0,72 mm | −1,63 mm / ≥ 0,71 mm |
| Kanał S, R: odległość do uzębienia | S ≥ 0,78; R ≥ 0,63 mm | S ≥ 0,77; R ≥ 0,72 mm |
| Wierzchołki kanału poza bryłą uzębioną | 0 | 0 |
| Poza montażowa: dokładna / w SCAD | [25,61024; 0], β = −225,000° / [25,61022; 0,02490], −224,884° (Δ 0,025 mm, 0,116°) | [25,40892; 0], −240,000° / [25,40890; 0,02311], −239,890° (Δ 0,023 mm, 0,110°) |
| Oddychanie orbity | 0,043 mm | 0,061 mm |
| Szerokość głowy 0,15 mm pod wierzchołkiem P / S | 0,65–0,72 / 0,47–0,66 mm | 0,59–0,65 / 0,41–0,57 mm |

## Tabela B: pełny cykl, eksportowane profile, kinematyka niezależna (`sweep.mjs`)

Wszystkie wartości w mm; „≥ x” oznacza, że wynik przekroczył próg odcięcia pomiaru.
Kolumny S–P i P–R podają minimum z trzech faz. „P–R wszystkie N” to wszystkie planety przy jednym wspólnym ψ.

| Kształt / dopasowanie | Pozy | min S–P | min P–R (N planet) | P–P | S–R | Kanały S–P / P–R / P–P | Luz obrotowy R (łuk przy 3R) | Blokada osiowa S / R (min wniknięcia) | ψ na 1,05 płatu |
|---|---|---|---|---|---|---|---|---|---|
| Kwadrat Ciasny | 612 | **0,107** | **0,110** | ≥ 1,5 (rzeczywiście 7,43) | ≥ 3 | ≥ 3 / ≥ 3 / ≥ 3 | 0,244–0,262 | **0,234 / 0,234** | 125,49° |
| Kwadrat Standardowy | 612 | **0,157** | **0,160** | ≥ 1,5 | ≥ 3 | ≥ 3 | 0,352–0,374 | **0,285 / 0,284** | 125,49° |
| Kwadrat Luźny | 612 | **0,219** | **0,220** | ≥ 1,5 | ≥ 3 | ≥ 3 | 0,482–0,510 | **0,344 / 0,346** | 125,49° |
| Trójkąt Ciasny | 918 | **0,108** | **0,110** | ≥ 15 | ≥ 3 | ≥ 3 | 0,245–0,290 | **0,234 / 0,203** | 167,50° |
| Trójkąt Standardowy | 918 | **0,159** | **0,160** | ≥ 15 | ≥ 3 | ≥ 3 | 0,355–0,394 | **0,284 / 0,247** | 167,46° |
| Trójkąt Luźny | 918 | **0,221** | **0,220** | ≥ 15 | ≥ 3 | ≥ 3 | 0,485–0,518 | **0,343 / 0,308** | 167,46° |

Interpretacja:

- **Brak jakiegokolwiek wniknięcia** w żadnej z 4590 póz. Minimalny luz jest równy `b/2` (0,11 / 0,16 / 0,22) z
  dokładnością do ok. 0,005 mm. Obwiednie są więc sprzężone z **dokładną** kinematyką, a nie tylko z dyskretną
  kinematyką oracle.
- Trzy fazy mieszczą się przy **wspólnym** kącie pierścienia, więc R jest spójną bryłą.
- ψ na płat: 125,49°/1,05 ≈ 119,5° wobec teoretycznych 120° dla kwadratu oraz 159,5° wobec 160° dla trójkąta.
  Różnica wynika z próbkowania od s = 0,5 kroku, a nie z dryfu. Luz nie spada za granicą płatu, więc okres jest
  domknięty.
- Wniknięcie przy przesunięciu osiowym o jeden stopień wynosi 0,20–0,35 mm. Jest to 1,6–2× więcej niż luz na
  flankę, zgodnie z założeniem `δ·cos α − b/2`. Retencja istnieje geometrycznie. Jej trwałość w PLA to F5.

Poza wydruku (`static.mjs`, stałe `ncg_mount_*` z SCAD, pierścień 0°) daje luzy S–P 0,113–0,226 mm i P–R 0,110–0,226 mm
we wszystkich fazach. Przesunięcie pozy SCAD względem pozy dokładnej (0,025 mm, 0,11°) mieści się w luzie.

## Tabela C: rampa nad kanałem (`ramp.mjs`)

Ostatnia warstwa rampy to `profil ∩ offset(kanał, ramp_h)`. Część zęba dalej od kanału niż `ramp_h` jest drukowana
jako **poziomy nawis** w pierwszej warstwie górnego pasa.

| | ramp_h | Brakujący nawis P / S / R |
|---|---|---|
| Kwadrat Ciasny | 2,2 | 0,90 / **0,98** / 0,95 mm |
| Kwadrat Std / Luźny | 2,4 | 0,70 / 0,83–0,88 / 0,80–0,85 mm |
| Trójkąt Ciasny / Std | 2,0 | 0,77 / 0,83–0,87 / 0,74–0,79 mm |
| Trójkąt Luźny | 2,2 | 0,57 / 0,72 / 0,63 mm |

## Tabela D: WASM (`@lofcz/openscad-wasm`, Manifold, Node 24; czas przeglądarki niemierzony)

| Wariant | Render | STL | Trójkąty | Składowe | Status Manifold | Trójkąty zdegenerowane (float32) |
|---|---|---|---|---|---|---|
| Kwadrat Ciasny / Std / Luźny, `output_mode=0` | 10,6 / 11,2 / 10,7 s | 25,0 / 25,5 / 25,5 MB | ~0,50–0,51 M | 6 / 6 / 6 | NoError | 5946 / 4990 / 5072 |
| Trójkąt Ciasny / Std / Luźny | 9,0 / 8,7 / 8,9 s | 20,0 / 19,8 / 20,6 MB | ~0,40 M | 5 / 5 / 5 | NoError | ~5000 |
| Kwadrat Std, H = 12,2 | 9,9 s | 25,5 MB | | 6 | NoError | |
| Trójkąt Luźny, H = 12,2 | 8,2 s | 20,5 MB | | 5 | NoError | |
| Kwadrat, koło centralne, otwór 24 | 4,2 s | 4,1 MB | | 1 | NoError | `WARNING` zmniejszenia otworu działa |
| Kwadrat, ukryte `outer_diameter=70` | 8,6 s | 24,5 MB | | 6 | NoError | brak asercji (N8) |
| Trójkąt Std, `output_mode=1` | 8,1 s | 19,8 MB | | 5 | NoError | |

Budżet planu §8.3 (≤ 30 s) jest spełniony w Node z zapasem około 3×.

## Tabela E: przekroje SCAD a dane (kwadrat Standardowy, H = 8,6)

W tabeli podano procent 60 000 losowych punktów pierścienia 8–45 mm niezgodnych z kompozycją danych w pozie montażowej.
Wartość 0 oznacza identyczność.

| z [mm] | 0,5 | 1,1 | 2,2 | 3,1 | 6,4 | 7,5 | 8,3 |
|---|---|---|---|---|---|---|---|
| Najlepsze dopasowanie | faza 2δ: **0** | faza δ: **0** | faza 0: **0** | kanał: **0** | faza 0: **0** | faza δ: **0** | faza 2δ: **0** |

Warstwy przejściowe (z = 0,7; 1,5; 7,1; 7,9) leżą między dwiema sąsiednimi fazami, czyli są ich przecięciem.
Warstwy z = 0,1 i 0,3 są zwężone przez fazkę. Kolejność stopni jest więc lustrzana, zgodnie z koncepcją: 2δ, δ, 0,
kanał, rampa, 0, δ, 2δ.

## Mapowanie K1–K6 (i W1–W5) z poprzedniego review

| ID | Problem w 0.1 | Stan w 0.2 | Dowód |
|---|---|---|---|
| **K1** | S jako obwiednia jednej pozy, 8/6 zębów | **Naprawione** | S ma 24/27 zębów (tab. A). Obwiednia z pełnego płatu × symetria (`geometry.mjs:129-132`). Min S–P w cyklu 0,107–0,221 mm, zero wniknięć (tab. B). |
| **K2** | Okrągła jama `3R − 1,1m` w pierścieniu | **Naprawione** | Jama usunięta. Pierścień to obwiednia wszystkich 3n płatów (`geometry.mjs:136-141`). 72/81 zęby, P–R ≥ 0,110 mm dla wszystkich N planet przy wspólnym ψ. |
| **K3** | Wymyślone wzory kinematyki w SCAD | **Naprawione (zmiana architektury)** | SCAD nie liczy ruchu, tylko składa prekomputowane profile (opcja C planu). `ncg_kinematics.scad` zawiera 3 stałe z oracle. Poza montażowa odbiega od dokładnej o 0,025 mm / 0,11°, co jest nieszkodliwe (luz statyczny ≥ 0,110). Uwaga: `k` służy już tylko do `INFO` i asercji. |
| **K4** | Stopnie przesunięte o ~0,002 mm (mm → °) | **Naprawione** | Faza to przesunięcie zębatki o δ wzdłuż łuku (`geometry.mjs:109`) z osobną obwiednią S/R na każdą fazę. Blokada osiowa 0,20–0,35 mm (tab. B). Przekroje potwierdzają kolejność (tab. E). |
| **K5** | Kanał z zębami, bez cofnięcia | **Naprawione** | Kanał P leży 1,80 / 1,63 mm pod centroidą i ≥ 0,71 mm pod uzębieniem. Brak zębów (wygładzenie o 1 podziałkę). Szczeliny w kanale ≥ 3 mm. |
| **K6** | Oracle bez zębów, testy samopotwierdzające | **Naprawione w zakresie geometrii, częściowo w zakresie testów** | Zębatka wzdłuż normalnej, prawdziwe zęby. Walidacja na 64/podziałkę ≠ 8/podziałkę generacji. Dodano S–R i eksportowane profile. Pozostaje: test eksportu tylko dla profilu Ciasny; `validateAxialProfiles` nadal obraca profil (niezgodny z produktem); `boundaryMetrics` dla R nadal bada okrąg zewnętrzny; brak testu blokady; brak CI (N6). |
| W1 | Faza trójkąta naroże na naroże | **Naprawione** | Dokładna poza: β = −240,000°, styk naroża S z bokiem P. |
| W2 | Domknięcie jako tautologia | **Bez znaczenia dla produktu** | `closureError` nadal jest tautologiczny, ale niezależne śledzenie ψ potwierdza domknięcie (tab. B). |
| W3 | Trywialne testy osiowe | **Nadal** | `oracle.test.mjs:52-55` i `validateAxialProfiles` bez zmian merytorycznych (N6). |
| W4 | Brak SCAD ↔ oracle i CI | **Częściowo** | Dane SCAD są wprost eksportem oracle (odtwarzalność: 0 różnic). Nadal brak CI i testów przekrojów w repo. |
| W5 | Próbkowanie/progi | **Naprawione** | Siatka walidacji jest niezależna. Miara odległościowa w tym review potwierdza brak wniknięć. |
| S2 | Granice stref poza siatką 0,2 mm | **Częściowo** | Nadal dla 2 z 6 kombinacji (N4). |
| S3 | Fazka na całym stopniu | **Naprawione** | −0,4 mm dla 0–0,2 mm i −0,2 mm dla 0,2–0,4 mm (`ncg_axial.scad:43-45`). |
| S1 | Rampa pozorna | **Częściowo** | Rampa startuje od kanału, ale jest za niska (N5). |
| S6 | `INFO` mylące | **Nadal** | `min_odstęp_planet` = 9,55 (kw.) / 7,16 (tr.), a rzeczywiście 7,43 / > 15 mm. |

## Nowe i pozostałe ustalenia wg severity

Nie znaleziono ustaleń **krytycznych** ani **wysokich**.

### ŚREDNIE

**N1. Brak luzu wierzchołkowego `c_tip`.** Plan (§4.9, l. 255 i 283) przewiduje `Tool_P = offset(+b/2)` planety
**z wydłużoną głową (+c_tip = 0,08/0,14/0,22)**. Generator (`geometry.mjs:128`) stosuje tylko `offsetOuter(b/2)`, a
`tip_clearance` z `main.scad:42` wpływa wyłącznie na `ramp_h`. Zębatka tnie dno planety na głębokość m, czyli bez
standardowego luzu 0,25m.

Skutek: promieniowy luz głowa–dno wynosi ok. 0,12 / 0,18 / 0,24 mm. Przykład dla kwadratu Std: głowa P +1,136 wobec dna
S −1,313, czyli 0,177 mm. Plan zakładał wyraźnie więcej. Na FDM głowa jest najbardziej narażona na „stopkę” i
zwis. Rozstrzyga F1.

**N2. Minimalny luz boczny 0,107–0,110 mm dla profilu „Ciasny”.** Jest zgodny z definicją (b/2 na flankę), ale leży
poniżej szerokości typowej linii FDM. Dla print-in-place przy dyszy 0,4 mm jest to wariant graniczny. Zalecam
prototyp od „Standardowego”. Rozstrzyga F1/F2.

**N3. Szczelina osiowa między półkami to 1 warstwa (0,2 mm) dla Ciasny/Std.** Pas zakładki `P(2δ) ∩ S(δ)` o szerokości
ok. 0,23–0,35 mm drukuje się 0,2 mm nad półką sąsiada, bez warstwy pośredniej. Ryzyko sklejenia ciał. Jest to
świadoma decyzja planu, więc potwierdzić ją muszą F1 i F11.

**N4. Granice stref poza siatką 0,2 mm (reszta S2).** Dla kwadratu „Ciasny” (`ramp_h = 2,2`) i trójkąta „Luźny”
(`ramp_h = 2,2`) `band_h = 2,9 / 3,7 / 4,7` (H = 8,6 / 10,2 / 12,2). Granice kanału i rampy wypadają na 2,9 / 3,5 / 5,7
(dla 8,6), a **cały górny pas z warstwami przejściowymi g_ax = 0,2** jest przesunięty o 0,1 mm względem warstw.
Slicer może scalić albo zgubić warstwę przejściową, czyli luz osiowy. `INFO:pas_zębów=2.9` i `kanał=2.8` widać w
echo. Pozostałe 4 kombinacje leżą na siatce.

**N5. Rampa nie sięga głowy zęba (reszta S1).** `ramp_h = ceil((2,25m + c_tip + 0,5 − 0,8)/0,2)·0,2` z założenia zostawia
nawis ok. 0,8 mm, ale kanał jest liczony od wygładzonego profilu minus `1,25m + 0,5`. Faktyczny nawis pierwszej warstwy
górnego pasa wynosi 0,57–**0,98** mm (tab. C). Kupon F11 (0,4/0,8/1,2 mm) pokryje ten zakres, ale wartość 0,98 mm dla
S w wariancie Ciasnym przekracza cel 0,8 mm z formuły.

### NISKIE

- **N6. Pokrycie testami i CI.** `oracle.test.mjs:93-132` waliduje eksport wyłącznie dla profilu Ciasny. Profile
  Standardowy i Luźny, które trafiają do produktu, nie są sprawdzane w repo. Tabela B tego review pokrywa je z wynikiem
  pozytywnym. Test `validateAxialProfiles` (`geometry.mjs:319-332`) nadal obraca profil planety wokół środka, czyli
  sprawdza zakazany §4.10 wariant, a nie eksportowane fazy. Nie ma testu blokady osiowej, test regularności R bada
  okrąg zewnętrzny (`boundaryMetrics` → `mp[0][0]`), a `wasm-smoke.mjs` sprawdza tylko liczbę brył. Żaden z tych testów
  nie działa w CI.
- **N7. Rozmiar STL.** Wynik to 20–25,5 MB i 0,40–0,51 mln trójkątów. W pliku jest ok. 5 tys. trójkątów zdegenerowanych
  po zapisie float32; pochodzą z nakładek `h + 0,01` (`linear_extrude(height=0.21)` w rampie). Manifold zwraca
  `NoError`, a slicery zwykle to tolerują, ale plik jest duży do pobrania w przeglądarce.
- **N8. Parametry i INFO.** Ukryte `outer_diameter`, `pressure_angle`, `curve_samples`, `envelope_samples` i `k_max` nie
  mają asercji zgodności z prekomputowanymi danymi (render z `outer_diameter = 70` przechodzi bez błędu).
  `min_odstęp_planet` jest błędne (S6). `FITS[2].axialGap = 0,3` w oracle różni się od `axial_gap = 0,4` w SCAD.
  Wybór fazy progiem `phase < 0,25 / < 0,75` (`ncg_teeth.scad:6`) działa dla obecnych δ = 0,393–0,635, ale jest kruchy.
  Asercje `ncg_validate.scad` pozostają stałymi lub tautologiami (S4).
- **N9. Cienkie głowy S w wariancie Luźnym.** Szerokość głowy 0,15 mm pod wierzchołkiem wynosi 0,41 mm (trójkąt Luźny)
  i 0,47 mm (kwadrat Luźny), czyli blisko szerokości linii. Głów pierścienia nie zmierzono wiarygodnie; metoda
  radialna nie nadaje się do falistej obręczy.
- **N10. Test backendu** uruchamia się tylko z katalogu `backend/` (import `app`). Jest to kwestia dokumentacji.

## Pozytywy (zweryfikowane)

- **Prawdziwe nieokrągłe zęby.** Stała podziałka na nieokrągłej centroidzie. Zęby P są generowane zębatką 25° wzdłuż
  normalnej, S i R są obwiedniami P z luzem. Liczby zębów 24/24/72 i 27/27/81 zgadzają się z `INFO`. Brak podcięć
  traconych przez radializację (0 wielokrotnych przecięć).
- **Pełne obwiednie S/P/R i kinematyka** potwierdzone niezależną kinematyką dokładną, z niezależnym wyznaczaniem kąta
  pierścienia, na siatce 97/podziałkę przez granicę okresu. Nie ma żadnego wniknięcia.
- **Dwa pasy z gładkim kanałem i lustrzanymi stopniami** (tab. E), retencja 0,20–0,35 mm. W kanale nie ma kontaktu
  (≥ 3 mm).
- **Eksport i radializacja:** dane są odtwarzalne bit w bit (poza CRLF). Sprawdzenie na niezależnej siatce dotyczyło
  **dokładnie** eksportowanych wielokątów, a nie źródłowych obwiedni oracle.
- **Wyłącznie browser/WASM:** `frontend/src` i `backend/app` bez zmian. Worker (`scadWasm.worker.ts:52`) rozpakowuje
  ZIP modułu i renderuje lokalnie. Oracle działa tylko w czasie budowy; jest to dopuszczalne w zleceniu jako
  precomputed build-time.
- **Rozmiar/limit importu:** 4,00 MB rozpakowane, czyli 38% limitu 10 MiB (`repository.py:25,203,227`); ZIP ma 1,39 MB.
- **Regresja klasyka:** `examples/scad/planetary-fidget` bez zmian od `74e8487`. Testy parsera i repozytorium: 13/13.
- **Wydajność:** 8–11 s na pełny print-in-place w Node, budżet 30 s.

## Czego nie da się potwierdzić bez F1–F11

Numerycznie potwierdzone jest tylko to, że idealne, sztywne bryły 2D/2.5D z eksportu obracają się bez kolizji i
blokują osiowo. **Nie** są potwierdzone:

- rozdzielenie ciał po druku przy luzach 0,11–0,22 mm, zwłaszcza na głowach (N1, N2) oraz przy szczelinie osiowej
  1 warstwy (N3): F1, F2, F4, F8;
- jakość nawisów rampy 0,57–0,98 mm i półek δ·cos α (N5): F11;
- faktyczna retencja przy zakładce 0,20–0,35 mm w PLA/PETG, przy nacisku 5 N i wstrząsaniu: F5, F6;
- „czucie” pulsowania i stuki od oddychania orbity 0,04–0,06 mm: F3, F4;
- zachowanie warstw poza siatką (N4) w realnym slicerze: F1 lub F11 dla wariantów Ciasny-kwadrat i Luźny-trójkąt;
- trwałość, upadki, druga drukarka i A/B z rewizją 1: F7, F8, F9, F10.

## Rekomendacje (bez implementacji w tym review)

1. Przed produkcją: wydłużyć głowę narzędzia o `c_tip` (N1). Wyrównać `ramp_h`/`band_h` do siatki 0,2 dla wszystkich
   profili (N4). Liczyć `ramp_h` od faktycznej odległości głowa–kanał (N5).
2. Testy w repo: walidacja eksportu dla wszystkich 3 profili; test blokady osiowej na fazach eksportowanych (w miejsce
   obrotu profilu); przekroje SCAD ↔ dane; poprawny `min_odstęp_planet`; asercja zgodności ukrytych parametrów z danymi;
   uruchamianie oracle i smoke WASM w CI.
3. Wydruki w kolejności: F1 (kupon luzów, w tym szczelina osiowa 1 warstwy) i F11, następnie F2/F4 na profilu
   „Standardowy”, potem F5.
