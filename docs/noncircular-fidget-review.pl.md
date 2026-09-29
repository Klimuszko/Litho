# Code review: nieokrągły fidget planetarny (rewizja 2)

Data: 2026-09-29. Przedmiot: gałąź `Main_Frame` @ `91fef41` („Keep triangular planets separate from ring”), czyli
`7272435` → `4f401cb` → `91fef41` względem bazy planu `74e8487`.
Zakres: `examples/scad/planetary-fidget-noncircular/`, `tools/noncircular-oracle/`, testy backendu i skrypt WASM,
porównane z `docs/noncircular-fidget-plan.pl.md`, `docs/noncircular-phase0-report.pl.md` i
`docs/noncircular-physical-tests-protocol.pl.md`. Review jest niezależny i nie zmienia kodu.

## Werdykt

**NO-GO dla prototypowego wydruku. NO-GO dla raportu fazy 0 (jego „GO” jest nieuzasadnione).**

Model renderuje się jako manifold i daje wymaganą liczbę brył (6 / 5). Nie jest jednak przekładnią:

- koło centralne i pierścień mają zęby tylko w miejscach odciśniętych przez planety w pozycji montażowej;
- mechanizm zakleszcza się po przetoczeniu o ułamek podziałki;
- stopnie „jodełki” są przesunięte o tysięczne części milimetra, więc retencja osiowa nie istnieje;
- kanał centralny nadal ma zęby (to tylko profil zwężony o 0,5 mm);
- oracle, na którym opiera się „GO”, generuje planety praktycznie bez zębów, pierścień nachodzący na koło
  centralne i dwie z czterech planet. Testy tego nie wykrywają, bo w dużej mierze same się potwierdzają.

Wydruk F1–F11 na tej geometrii nie ma sensu. Wynik jest przesądzony (brak obrotu, brak retencji), a pomiar nic
by nie skalibrował.

## Odpowiedzi na pytania zlecenia (skrót)

| # | Pytanie | Ocena | Najważniejszy dowód |
|---|---|---|---|
| 1 | Czy planety są prawdziwymi zębatkami o obrysie kwadratu/trójkąta? | **Nie.** Obrys jest nieokrągły (±4,1% / ±5,0% promienia), ale uzębienie to 12 nieregularnych szczelin z 12 „stempli” dłutaka, a nie `z` zębów o stałej podziałce. Koło centralne ma 8 (kwadrat) / 6 (trójkąt) zębów zamiast 24 / 27. | K1, K2 |
| 2 | Kinematyka i współpraca S/P/R | **Błędna.** Prawo ruchu w SCAD to wymyślone wzory. Obwiednia S ma 1 pozę (×symetria), R ma N + n póz. Symulacja z prawem toczenia z oracle daje kolizje od pierwszych ~0,3 mm łuku. Faza montażowa trójkąta jest przesunięta o 60° (naroże na naroże). | K1, K3, W1 |
| 3 | Koncepcja osiowa: dwa pasy + cofnięty kanał | **Niezrealizowana.** Przesunięcie stopni wynosi ~0,002 mm zamiast 0,5 mm (błąd jednostek mm → stopnie). Kanał to profil z zębami, zwężony `offset(-0,5)`, bez cofnięcia pod linię stóp. Rampa jest pozorna. | K4, K5, S1 |
| 4 | Poprawka jamy pierścienia | **Maskuje błąd.** Okrągła jama `r = 3R − 1,1m` zajmuje 55% / 69% obwodu. Pierścień jest okrągły, a nie 12-/9-płatowy, i nie ma zębów poza odciskami. Mosty zniknęły dlatego, że cały obwód zamieniono w gładką ścianę, a nie dzięki poprawnej obwiedni. | K2 |
| 5 | Czy oracle/testy są samopotwierdzające? | **Tak, w kluczowych punktach.** Domknięcie jest tautologią. Kolizje sprawdza się na tych samych klatkach, z których cięto obwiednię. Pierścień sprawdza się tylko z planetą 0. „Regularność” pierścienia bada zewnętrzny okrąg. Test axial sprawdza tylko niepustość przecięć. SCAD nie jest porównywany z oracle. | K6, W2–W5 |
| 6 | Druk FDM, prześwity, mosty, manifold, 6/5 | Manifold i liczba brył: **OK**. Granice stopni nie leżą na wielokrotnościach 0,2 mm. Cały pierwszy stopień jest zwężony. Statyczny luz ok. 0,16 mm na flankę. Realność ruchu: nie dotyczy, bo mechanizm jest zablokowany. | S2, S3, N-lista |
| 7 | Wyłącznie browser/WASM | **OK.** Brak zmian w `frontend/src` i `backend/app`. Moduł jest czystym SCAD, a smoke używa `@lofcz/openscad-wasm`. | pozytyw P3 |
| 8 | Klasyczny `planetary-fidget` bez zmian | **OK.** `git diff 74e8487 HEAD -- examples/scad/planetary-fidget` jest pusty. | pozytyw P4 |

## Co uruchomiono

| Polecenie | Wynik |
|---|---|
| `tools/noncircular-oracle`: `npm ci && npm test` | 5/5 pass, 67 s |
| `node wasm-smoke.mjs 0 0 1` (kwadrat, print-in-place, Standardowy) | `WASM_OK components=6`, manifold `NoError`, genus 21, render OpenSCAD 9,9 s, całość procesu Node 42 s |
| `node wasm-smoke.mjs 1 0 1` (trójkąt) | `WASM_OK components=5`, manifold `NoError`, genus 14, render 6,7 s, całość 28 s |
| `py -3 -m pytest backend/tests/test_scad_parser.py backend/tests/test_scad_repository.py` | 13 pass |
| Własne skrypty review (poza repo, w katalogu roboczym sesji) | opis metody poniżej, wyniki w tabelach dowodów |

**Metoda własnej weryfikacji.**

1. Ten sam pakiet WASM renderuje profile 2D `ncg_profile(kind, …, phase)` dla S, P i R z domyślnymi parametrami
   `main.scad` (D = 90, kanciastość 55%, Standardowy). Eksport SVG jest parsowany do wielokątów (`polygon-clipping`).
2. Liczba zębów i odchylenia promieniowe są liczone na 7200 promieniach.
3. Przesunięcie stopni to pole XOR profilu planety dla faz 0 / δ / 2δ podzielone przez obwód, czyli średnie
   przesunięcie normalne.
4. Symulacja toczenia używa `solveKinematics` z oracle, z promieniem i `e` z SCAD. S jest nieruchome, planeta jest
   w pozie klatki, a R jest obrócone o `k·χ_kin`. Mierzono pole przenikania co ok. 0,34 mm łuku.
5. Geometrię oracle (`generateMechanism`, kwadrat e = 0,05 i trójkąt e = 0,08, jak w teście) sprawdzono:
   (a) na 8× gęstszej siatce klatek, (b) dla wszystkich N planet względem pierścienia, (c) dla pary S–R.
6. Wyrenderowane przekroje obejrzano jako PNG (rasteryzacja wielokątów).

Pliki STL i PNG nie są częścią commitu.

## Ustalenia wg severity

### KRYTYCZNE (każde osobno blokuje wydruk)

**K1. Koło centralne jest obwiednią jednej pozy planety, a nie ruchu.**
`lib/ncg_teeth.scad:32-36`: `for(i=[0:n-1]) let(a=360*i/n, …)` daje `n` póz rozstawionych co `360/n`. Ponieważ S
ma symetrię `n`-krotną, wszystkie są tą samą pozą montażową. `envelope_samples = 8` (`main.scad:32`) nie jest
nigdzie użyte.

Skutek:

- 56% (kwadrat) / 72% (trójkąt) obwodu S to nietknięty blank `r_S(θ) + 1,1m`;
- S ma tylko po 2 zęby przy każdym styku (8 / 6 zamiast deklarowanych `INFO:zęby_koła_centralnego = 24 / 27`);
- symulacja toczenia: przenikanie S–P 0,09 mm² po 0,34 mm łuku, 0,78 mm² po 1 mm i 2,35 mm² po 2,4 mm.
  Mechanizm zakleszcza się po ok. ⅓ podziałki (podziałka ≈ 3,37 mm).

**K2. Pierścień jest okrągłą jamą z odciskami, a nie falistym, uzębionym pierścieniem.**
`lib/ncg_teeth.scad:38-51`: jama `circle(r=3*R-1.1*m)` (l. 43) plus N kopii planety w pozie montażowej (l. 46-47)
i `n` póz z `chi = k·a·(1+2/n)` (l. 48-49). To łącznie 8 / 6 odcisków.

Skutek:

- wewnętrzny obrys R leży dokładnie na okręgu jamy przez 55% (kwadrat) / 69% (trójkąt) obwodu;
- centroida pierścienia nie ma 12 / 9 płatów;
- przenikanie P–R w symulacji: 0,30 mm² po 0,68 mm, 3,46 mm² po 2,4 mm i ok. 11 mm² na końcu płatu.

„Poprawka” z `91fef41` (komentarz l. 41-45) usunęła mosty między S i R, które powstawały z powodu rzadkich póz.
Zrobiła to przez wycięcie wszystkiego wewnątrz `3R − 1,1m`. To klasyczne ukrycie błędu obwiedni w luzie, czyli
zakazany skrót z §11.2 pkt 7–8 planu. Odpowiedź na pytanie 4: poprawka nie tworzy luzu w miejscach styku. Wycina
natomiast całe uzębienie poza odciskami, a w ruchu naroża planet (sięgające `3R + eR + 1,05m`) wchodzą ok. 2,8 mm
w gładką ścianę.

**K3. Kinematyka w SCAD nie jest liczona, tylko wpisana.**
`lib/ncg_kinematics.scad:2-4`:

- `ncg_k = 1 + 0.0003 + 0.016e` (liniowe dopasowanie);
- `orbit = 2R(1 + 0.004e·cos(na))`;
- `spin = 180/n − a + 12e·sin(na)`.

Brak toczenia po łuku, twierdzenia Kennedy’ego i wyznaczania `χ`. Narusza to §0 pkt 2 i §4.4–4.6 planu („geometria
powstaje z kinematyki”). Komentarz l. 1 („próbkowany odpowiednik oracle”) jest nieprawdziwy: nie ma żadnego testu
zgodności SCAD ↔ oracle (testy 9 i 9a planu nie istnieją). `INFO:korekta_pierścienia_k` pochodzi z tej formuły,
a nie z obliczeń.

**K4. Stopnie „jodełki” są przesunięte o ~0,002 mm zamiast o δ ≈ 0,5 mm, więc retencji osiowej brak.**
`δ` jest długością łuku w mm (`main.scad:51`), a `ncg_planet_profile` traktuje ją jako kąt w stopniach:

- blank obracany o `phase/n` (`ncg_teeth.scad:25`);
- dłutak obracany o `phase/z` stopni (`ncg_teeth.scad:27`).

Pomiar (średnie przesunięcie normalne profilu planety):

| Kształt | faza δ | faza 2δ | wymagane |
|---|---|---|---|
| kwadrat | 0,0015 mm | 0,0030 mm | 0,503 mm (δ) i blokada > `j_t` = 0,353 mm |
| trójkąt | 0,0011 mm | 0,0022 mm | jw. |

Wszystkie 6 stopni każdego ciała są praktycznie identyczne, czyli zęby są proste na całej wysokości. Planety,
koło centralne i pierścień mogą się swobodnie rozsunąć osiowo. Warstwy przejściowe `P_i ∩ P_{i+1}`
(`ncg_axial.scad:8-13`) są w tej sytuacji równe profilom, a „pionowa szczelina g_ax” nie ma czego oddzielać.
Obrót całego nieokrągłego profilu wokół środka (nawet w poprawnych jednostkach) jest dokładnie tym, co plan
zabrania w §4.10 („obrót przemieszcza płaty, a nie zęby”). Poprawna realizacja wymaga dłutaka przesuniętego
o δ **wzdłuż centroidy** i obwiedni S/R liczonej osobno dla każdego stopnia.

**K5. Kanał centralny ma zęby i nie jest cofnięty pod linię stóp.**
`ncg_axial.scad:26`: kanał = `offset(delta=-recess)` pełnego, uzębionego profilu. Plan (§4.10.2) wymaga
„krzywa stóp `offset(−r_rec)`, zero zębów”.

Pomiar na planecie kwadratowej:

- najdalszy punkt profilu w kanale leży **+0,63 mm nad** centroidą;
- wymagane jest ≤ −1,25m − r_rec = −1,84 mm (pod centroidą);
- w kanale nadal są 20 „zęby” (tyle samo przejść co w pasie).

Jest to zakazany skrót §11.2 pkt 12 („kanał bez cofnięcia rdzenia poniżej linii stóp”). Statycznie w kanale jest
szczelina ≈ b/2 + 1,0 mm, więc kontaktu brak. Nie jest to jednak „wolny pas bez zębów” z koncepcji użytkownika,
a rampa (pkt S1) jest przez to pozorna.

**K6. „GO” fazy 0 opiera się na oracle, którego geometria jest błędna, a testy tego nie wykrywają.**
Sprawdzenie `generateMechanism` z parametrami testu (`radius 12, module 1, posesPerPitch 4`), kwadrat e = 0,05:

| Ciało | Wynik |
|---|---|
| planeta | `r − r_pitch` ∈ [−1,10; −0,78] mm: cały obrys leży **pod** centroidą, a „zęby” to ząbkowanie 0,32 mm, bez ewolwenty |
| koło centralne | `r − r_pitch` ∈ [+0,78; +1,04] mm: gładki blob |
| pierścień vs planety w klatce 0 | przenikanie: planeta 0 = 0, planeta 1 = **385 mm²**, planeta 2 = **385 mm²** (cała planeta), planeta 3 = 0 |
| pierścień vs koło centralne | przenikanie **507 mm²** |

Pierścień tnie tylko wycinek jednego płatu, a reszta dysku jest pełna (rys. 1 poniżej, opis).

Mimo to testy przechodzą, bo:

- `validateCycle` (`geometry.mjs:137-150`) porównuje pierścień wyłącznie z planetą 0 (l. 145-146) i nigdy z S;
- kolizje liczy na **tych samych klatkach**, z których wycięto obwiednie (`samples: 360/lobes`, l. 82).
  Na 8× gęstszej siatce przenikanie P–R rośnie do 0,067 / 0,073 mm², czyli 10⁴× ponad próg `1e-5`;
- `boundaryMetrics` (`geometry.mjs:126-135`) bada tylko `mp[0][0]`, czyli dla pierścienia **zewnętrzny okrąg**
  (1080 wierzchołków, `minTurn ≈ π`). Wewnętrzny obrys pierścienia oracle ma w obu badanych przypadkach `regular: false` (dla trójkąta `minEdge 1,5e-13`);
- planet brak kontroli głębokości zęba. Test sprawdza grubości **dłutaka** (`shaper.tipThickness`), a nie
  wygenerowanych zębów, i raport fazy 0 podaje je jako „grubość głowy”.

Twierdzenia raportu fazy 0 („maksymalne pola przenikania S–P i P–R poniżej 1e-5 mm²”, „regularne pojedyncze
granice”, „GO dla implementacji programowej”) są więc nieuprawnione. Prawdopodobne przyczyny braku zębów planety:

- środek dłutaka jest przesuwany wzdłuż **promienia**, a nie normalnej do centroidy (`geometry.mjs:67-68`), więc
  punkt styku się ślizga (dla e = 0,05, n = 4 kąt promień–normalna sięga ~11°, przesunięcie boczne ok. 1,2 mm);
- zbyt rzadkie pozy (4 na podziałkę).

Samo odwrócenie znaku `s/rp` nie pomaga (sprawdzone: głębokość 0,4–0,7 mm). Przyczyny nie dowodzę do końca.

Szkic geometrii oracle (rys. 1, klatka 0, kwadrat): planety i S to zaokrąglone kwadraty bez widocznych zębów.
Pierścień (szary) jest pełnym dyskiem z jednym białym wycięciem obejmującym S i dwie planety, a pozostałe dwie
planety leżą w materiale pierścienia.

### WYSOKIE

**W1. Faza montażowa trójkąta: naroże planety naprzeciw naroża koła centralnego.**
`main.scad:87` i `ncg_teeth.scad:46`: `rotate(180/n)` dla n = 3 to 60°. Kierunek do S w układzie planety to
wtedy 120°, a `cos(3·120°) = 1`, czyli naroże. Plan §4.4 wymaga „naroże naprzeciw boku”. Rozstaw 2R przy
narożu na naroże daje nominalne nakładanie centroid 2eR ≈ 1,26 mm, które S „przyjmuje” jako wgłębienie
(widoczne na przekroju). Poza oracle frame 0 różni się dla trójkąta o 60,1° (kwadrat: 0,1°). Commit `91fef41`
(„Keep triangular planets separate from ring”) leczył objaw, a nie tę przyczynę.

**W2. Domknięcie pierścienia jest tautologią.**
`oracle.mjs:89-91`: `k` jest wyznaczane tak, by okres był dokładnie `2π/n_r`, a `closureError` (l. 135) sprawdza
ten sam związek. `< 4e-16 rad` z raportu to błąd zaokrąglenia, a nie wynik. Wartościowy byłby test naturalnego
`n_r` względem przewidywań §4.6 oraz regularności obwiedni R po korekcie k. Ten drugi nie istnieje (patrz K6).

**W3. Pozostałe testy są trywialne lub niezależne od kodu.**
- `oracle.test.mjs:44-47` („phasing”): `(3·lobes) % lobes == 0` oraz `TAU/4*4 == TAU`.
- `oracle.test.mjs:32-42` („7a”): algebra stałych dla m = 1 i H = 8,4. Nie dotyka geometrii SCAD ani oracle.
- `validateAxialProfiles` (`geometry.mjs:152-165`): sprawdza tylko, że przecięcia są niepuste i mniejsze od
  profilu. Brak testu 6 planu (blokada przy Δz = g_ax + 0,05), 7a (odstęp w kanale), 7b (szczeliny poziome),
  7c (nawisy) i 7d (liczba przyporu).
- `minPlanetSpacing >= 0.58` (`oracle.test.mjs:65`) przechodzi z zapasem 10 mm. Nie jest to czułe kryterium.
- Oracle tnie S i R **bez luzu** (`geometry.mjs:86-88`, planeta nominalna), więc nie testuje profili luzów, które
  trafiają do SCAD.

**W4. Brak testów SCAD ↔ oracle i testów zachowania WASM.**
`wasm-smoke.mjs:216` sprawdza tylko liczbę składowych w `output_mode = 0` dla Standardowego. Nie sprawdza:
zgodności `INFO:` z oracle (test 9), przekrojów `debug_section_z` (test 9), wspólnej objętości (9a), asercji dla
złych parametrów (11), profili Ciasny/Luźny ani średnic min/max (8). Skrypt `test:noncircular-wasm` nie jest
podpięty do CI (jedyny workflow to `container-images.yml`). Oracle również nie działa w CI.

**W5. Próbkowanie i progi.**
- SCAD: `poses=12` stempli dłutaka na całą planetę (`ncg_teeth.scad:23`), niezależnie od `z` = 24/27.
  Planeta ma 12 nieregularnych szczelin (rys. przekroju), co przeczy `INFO:zęby_planety`.
- Oracle: 4 pozy/podziałkę dla planety i ok. 15 póz/podziałkę dla S/R, a walidacja na tych samych klatkach.
- Siatka `snap = 1e-5 mm` (`geometry.mjs:11`) i próg `1e-5 mm²` są porównywalne z artefaktami kwantyzacji. Przy
  ruchu między klatkami nie ma żadnego sprawdzenia, a `catch` z jitterem (l. 105-108) maskuje degeneracje.

### ŚREDNIE

- **S1. Rampa jest pozorna.** `ncg_axial.scad:28`: offset maleje od `recess` (0,5 mm) do 0, a nie od
  `d_ov = 2,25m + c_tip + r_rec` (§4.10.2). Przy `ramp_h = 2,4 mm` (12 warstw) nawis wynosi ok. 0,04 mm na
  warstwę. Zabiera 2,4 mm wysokości (29% H) i niczego nie „ratuje”, bo kanał nie jest cofnięty (K5).
  `INFO:udział_kontaktu = 59,5%` jest więc liczbą formalną.
- **S2. Granice stopni nie leżą na siatce 0,2 mm.** `step = (band − 2·g_ax)/3` = 0,767 mm (kwadrat) i 0,833 mm
  (trójkąt) (`ncg_axial.scad:17`). Plan §4.10.1 wymaga wielokrotności wysokości warstwy. Warstwy przejściowe
  0,2 mm mogą zniknąć albo się podwoić w slicerze.
- **S3. Fazka pierwszej warstwy zwęża cały pierwszy stopień.** `ncg_axial.scad:20`: `offset(-0.2)` obejmuje
  zakres 0,2…0,767 mm, a nie tylko 0,2–0,4 mm (§4.11). Dla każdej pary daje to +0,4 mm luzu normalnego w dolnym
  stopniu.
- **S4. Asercje są tautologiczne lub stałe.** `ncg_validate.scad:5` (δ z definicji spełnia warunek),
  l. 8 (`channel_gap` to stała z tabeli, nie zmierzona szczelina), l. 4 (`H ≥ 7,2` zamiast `H_min(m)`), l. 7
  (`2,2` zamiast `max(2,2; 2,2m)`). Brak asercji krzywizny, odstępu planet w cyklu i ścianki obręczy (§4.12).
- **S5. Zakres kanciastości wychodzi poza walidację.** `main.scad:39`: `e_max = 0,075` dla kwadratu przekracza
  granicę wypukłości 0,0588 (§4.2), a oracle testuje tylko e ≤ 0,05 (kwadrat) i ≤ 0,08 (trójkąt). Suwak
  `squareness > 67%` (kwadrat) nie jest pokryty żadnym testem. Z drugiej strony domyślne e = 0,041 daje obrys
  ledwie „kwadratowy” (±0,53 mm przy wysokości zęba 2,4 mm).
- **S6. Raport `INFO:` wprowadza w błąd.** `min_odstęp_planet = 2R(√2 − 1 − e)` (`main.scad:68`) to wzór dla
  n = 4, użyty też dla trójkąta, i nie jest minimum w cyklu. `zęby_* = teeth` nie odpowiada geometrii (K1, W5).
  `korekta_pierścienia_k` pochodzi z formuły (K3).

### NISKIE

- Nieużywane parametry UI: `rim_style` (`main.scad:24`) i `side_flatness` (l. 27). Ukryte `curve_samples`,
  `envelope_samples` i `k_max` (l. 31-33) też nie są używane. `pressure_angle` (l. 28) wpływa tylko na δ, bo
  dłutak ma wpisane 25° (`ncg_teeth.scad:27`). Suwaki bez efektu to błąd produktowy.
- `tip_clearance` (`main.scad:48`) jest używany tylko do wysokości rampy i nie wydłuża głowy narzędzia (§4.9).
- Ukryte `output_mode` 5–7 (`main.scad:98-100`) nie są opisane w liście Customizera.
- Czas: w Node cały proces WASM trwał 42 s (kwadrat), a sam render OpenSCAD 9,9 s. Pomiaru w przeglądarce nie
  wykonano. Budżet §8.3 (≤ 30 s) jest możliwy do spełnienia, ale po poprawnym zagęszczeniu obwiedni koszt
  wzrośnie wielokrotnie.

## Dowody liczbowe (domyślne parametry, profil Standardowy)

| Wielkość | Kwadrat | Trójkąt |
|---|---|---|
| R, e, m, z (INFO) | 12,805 / 0,0413 / 1,074 / 24 | 12,705 / 0,0495 / 0,946 / 27 |
| Odchylenie obrysu od koła (±eR) | ±0,53 mm | ±0,63 mm |
| Szczeliny planety (przejścia) | 20 (12 głębokich) | 21 |
| Zęby S przy stykach / deklarowane | 8 / 24 | 6 / 27 |
| Nietknięty blank S | 56% obwodu | 72% obwodu |
| Wewnętrzny obrys R na okręgu jamy | 55% obwodu | 69% obwodu |
| Przenikanie statyczne (poza montażowa) S–P / P–R / S–R | 0 / 0 / 0 | 0 / 0 / 0 |
| Przenikanie S–P po 0,34 / 1,0 / 2,4 mm łuku | 0,09 / 0,78 / 2,35 mm² | — (faza startowa o 60° niezgodna z toczeniem: 1,2 mm² już w s = 0) |
| Przenikanie P–R, maksimum w płacie | 16,2 mm² | 20,0 mm² |
| Przesunięcie stopnia δ / 2δ (średnie normalne) | 0,0015 / 0,0030 mm | 0,0011 / 0,0022 mm |
| Profil kanału: najdalszy punkt względem centroidy | +0,63 mm (wymagane ≤ −1,84) | +0,49 mm (wymagane ≤ −1,68) |
| Składowe STL / manifold | 6 / NoError | 5 / NoError |

## Co jest w porządku (pozytywy)

- **P1.** Architektura modułu zgodna z planem §7: osobny katalog, `lib/` wewnątrz, polskie etykiety, parser bez
  ostrzeżeń (`backend/tests/test_scad_parser.py`), rejestracja przykładu w teście repozytorium.
- **P2.** Obrysy S i P są rzeczywiście nieokrągłe (`ncg_r` z `e₁·cos(nθ)`). Nie jest to okrągłe koło z
  wielokątnym otworem ani zębatka doklejona do boków. Kod nie używa `twist` ani `scale()` na kołach. Zakazane
  skróty §11.2 pkt 1–5 nie występują (pkt 7, 8 i 12 niestety tak, patrz K2 i K5).
- **P3.** Tylko przeglądarka/WASM: diff nie dotyka `frontend/src` ani `backend/app`. Smoke używa dokładnie
  `@lofcz/openscad-wasm` z backendem Manifold.
- **P4.** Klasyczny `examples/scad/planetary-fidget` jest bitowo niezmieniony względem `74e8487`.
- **P5.** Eksport print-in-place jest manifoldem z 2 + N rozdzielnymi bryłami. Statycznie w pozie montażowej
  bryły nie nachodzą na siebie, a luz wynosi b/2 na flankę.
- **P6.** Sama kinematyka centroid w `oracle.mjs::solveKinematics` (toczenie po łuku, Kennedy, χ_kin) wygląda
  poprawnie i jest dobrym fundamentem. Problem leży w generacji zębów, walidacji i w tym, że SCAD z niej nie
  korzysta.

## Czego nie da się potwierdzić bez testów fizycznych F1–F11

Na obecnej geometrii **wszystkie F1–F11 są przedwczesne**. Wynik F2/F4 (brak obrotu) i F5 (brak retencji)
wynika z analizy powyżej. Po naprawie K1–K6 wydruki pozostaną jedynym źródłem wiedzy o:

- rzeczywistym luzie potrzebnym do rozdzielenia przy zmiennej krzywiźnie (F1, F8);
- tym, czy półki stopni δ drukują się czysto i trzymają osiowo przy realnym tarciu, zużyciu i ściskaniu obręczy
  (F5, F7, F10);
- tym, czy kanał realnie ułatwia pierwsze uruchomienie względem rewizji 1 (F9);
- jakości rampy nad kanałem i ewentualnych nitkach łączących ciała (F11), wystarczalności `g_ax` = 1 warstwa;
- „czuciu” pulsowania, stukach od oddychania orbity, granicy kanciastości (F3), zachowaniu trójkąta (F4)
  i PETG (F6);
- wytrzymałości krótszych pasów na upadek (F10) i trwałości po 1000 obrotach (F7).

Symulacja numeryczna może natomiast i **powinna** z góry rozstrzygnąć:

- brak kolizji w pełnym cyklu (gęstsza siatka niż generacja);
- blokadę osiową jako test geometryczny;
- szczeliny poziome;
- odstęp w kanale;
- zgodność SCAD ↔ oracle.

Tego dziś brakuje. Nie należy przerzucać tych pytań na wydruki.

## Rekomendowana kolejność naprawy (bez implementacji w tym review)

1. Naprawić oracle: dłutak wzdłuż normalnej z poprawnym toczeniem, gęste pozy, test głębokości i grubości
   **wygenerowanych** zębów, pełna obwiednia R (wszystkie płaty i wszystkie planety), test S–R i wszystkich
   planet, walidacja na klatkach przesuniętych względem generacji, luz w cięciu. Dopiero potem ponownie ocenić
   fazę 0.
2. Stopnie: przesunięcie dłutaka o δ wzdłuż centroidy (w mm łuku) i osobna obwiednia S/R dla każdego stopnia.
   Test blokady osiowej zgodny z §9.1 pkt 6.
3. SCAD: kinematyka liczona (albo tablica z oracle, opcja C §8.2) zamiast wzorów z `ncg_kinematics.scad`.
   Obwiednie S/R z gęstego ruchu. Usunąć jamę `3R − 1,1m`. Poprawić fazę trójkąta.
4. Kanał: krzywa stóp `offset(−r_rec)` bez zębów. Rampa od `d_ov`. Granice stref na siatce 0,2 mm. Fazka tylko
   0–0,4 mm.
5. Testy 9/9a/11 (SCAD ↔ oracle, przekroje, wspólna objętość, asercje) i uruchamianie oracle i smoke w CI.
6. Dopiero wtedy F1 (kupon luzów), F11 i F2.
