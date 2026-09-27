# Plan: fidget planetarny z nieokrągłymi (kwadratowymi i trójkątnymi) kołami zębatymi

Status: **plan techniczny i produktowy, bez implementacji geometrii**
Baza: commit `74e8487` (gałąź `Main_Frame`), moduł `examples/scad/planetary-fidget` w wersji 2.3.0
Zakres dokumentu: geometria sprzężonych kół nieokrągłych, integracja z klientowym OpenSCAD WebAssembly, testy, etapy i kryteria go/no-go.

---

## 0. Streszczenie decyzji

1. **Chodzi o prawdziwe koła nieokrągłe.** Krzywa podziałowa (centroida) koła centralnego i planet jest zaokrąglonym kwadratem albo zaokrąglonym trójkątem. Krzywa pierścienia wewnętrznego jest falista (ma wiele płatów). Zęby leżą *wzdłuż* tej krzywej. To nie są okrągłe koła rozstawione w trójkąt lub kwadrat. Nie są to też okrągłe koła z wielokątnym otworem. Nie są to proste zęby doklejone do boków wielokąta.
2. **Geometria powstaje z kinematyki, a nie z kształtu.** Najpierw liczymy ruch planety toczącej się po kole centralnym. Z twierdzenia Aronholda–Kennedy’ego wynika wtedy centroida pierścienia. Zęby koła centralnego i pierścienia wyznaczamy jako **obwiednię zębów planety** w ruchu względnym. Dzięki temu są z nią sprzężone z definicji.
3. **Dokładne domknięcie pierścienia wymaga korekty prawa ruchu pierścienia.** Wstępne obliczenia (§4.6) pokazują, że dla nieokrągłych kształtów „naturalna” liczba płatów pierścienia jest nieznacznie większa od całkowitej: 12,01–12,07 zamiast 12. Plan to naprawia: narzucamy okresowe prawo obrotu pierścienia ze współczynnikiem korekty `k ≈ 1,000–1,002` i generujemy zęby pierścienia jako obwiednię dla *tego* ruchu. Sprzężenie pozostaje ścisłe, a centroida pierścienia przesuwa się o ułamek milimetra (odpowiednik przesunięcia zarysu).
4. **Liczba planet nie jest swobodna.** Kwadrat: dokładnie 4 planety. Trójkąt: dokładnie 3 planety. Warianty rozszerzone są opcjonalne (§5.4).
5. **Osobny moduł.** Klasyczny moduł `planetary-fidget` zostaje bez zmian. Nowy moduł `planetary-fidget-noncircular` zawiera oba kształty (kwadrat i trójkąt) w jednym pliku `main.scad` z biblioteką `lib/` wewnątrz katalogu modułu (§7).
6. **Całe generowanie w przeglądarce.** Działa na obecnym `@lofcz/openscad-wasm` z backendem Manifold w Web Workerze. Nie wymaga zmian w backendzie ani w silniku. Obliczenia numeryczne są napisane w czystym OpenSCAD. Referencyjny „oracle” w TypeScript/Node służy tylko do testów.
7. **Osiowe zatrzymanie.** Zamiast `linear_extrude(twist=…)` używamy **schodkowej jodełki**: warstw z przesunięciem fazy zębów wzdłuż krzywej. Obrót nieokrągłego profilu wokół środka nie jest zębem śrubowym, więc twist jest dla tych kół zabroniony.

---

## 1. Stan obecny i kontekst

### 1.1 Klasyczny moduł (musi zostać bez regresji)

`examples/scad/planetary-fidget/main.scad` (commit `74e8487`):

- Solver szuka tablicy kandydatów `(zs, zp, zr = zs + 2·zp, m)`. Sprawdza fazowanie `(zs + zr) % N == 0`, odstęp planet `spacing_margin` i miejsce na otwór na palec.
- Zęby ewolwentowe (kąt przyporu 25°) powstają z segmentów `involute_tooth_segments`. Pierścień powstaje przez odjęcie `internal_gap_cutter_2d`.
- Jodełka to dwa `linear_extrude` z `twist = ±helix_twist_deg(rp, h/2, β)`. Jest poprawna **wyłącznie dla kół okrągłych**.
- Luzy FDM: `mesh_backlash` 0,22 / 0,32 / 0,44 mm, `extra_tip_clearance` 0,08 / 0,14 / 0,22 mm, `planet_spacing_clearance` 0,25 / 0,40 / 0,58 mm.
- Projektant obudowy (`grip_style` 0–4) i walidacja przez `echo("INFO:…")` i `assert`.

### 1.2 Błędne podejścia, które nie mogą wrócić

- `a0dbf70` „Add equal-gear planetary layouts”. Dodawał `gear_layout` (Trójkąt/Kwadrat/Krąg) jako **okrągłe koła równej wielkości** (`zs == zp`) rozstawione w 3 lub 4 planety. To zła interpretacja zdjęć. Commit `74e8487` ją wycofał.
- Niezacommitowana próba **przyklejania prostych zębów do boków wielokąta**. Zęby na prostym boku nie tworzą pary sprzężonej z niczym, co się toczy. Na narożach powstają kolizje albo szczeliny. Nie może wrócić w żadnej formie (§11).

### 1.3 Potok renderowania (z kodu)

- `frontend/src/scadWasm.worker.ts`: `createOpenSCAD()` z `@lofcz/openscad-wasm`. Rozpakowuje ZIP modułu do `/module/…` (ścieżki walidowane przez `safePath`) i wywołuje `callMain([entry, "--backend", "Manifold", "--export-format", binstl|3mf, ...-D…, "-o", out])`.
- `frontend/src/scadWasm.ts`: `buildScadDefinitions` serializuje parametry do `-Dname=value`. Jeśli moduł nie ma parametru `mode`, dopisuje `-Dmode="model"`. **Nowy moduł nie może więc używać nazwy `mode` w innym znaczeniu.**
- `backend/app/scad/parser.py`: parser metadanych Customizera (a nie interpreter SCAD). Obsługuje:
  - sekcje `/* [..] */`, zakresy `[min:step:max]` i listy `[0:Etykieta,…]`;
  - tagi `@label`, `@unit`, `@advanced`, `@hidden`, `@group`, `@order`;
  - sekcję „Ukryte”, która ukrywa parametry.

  Parser **nie obsługuje warunkowej widoczności** parametrów. `validate_source_tree` pozwala na `include/use <…>` tylko wewnątrz katalogu modułu.
- `backend/app/scad/repository.py::seed_bundled_examples` rejestruje każdy katalog `examples/scad/*` jako moduł oficjalny. Test `backend/tests/test_scad_repository.py:76` zakłada dziś zbiór `{"planetary-fidget"}`. Przy dodaniu modułu trzeba go świadomie zaktualizować.
- Komunikaty `INFO:` i `WARNING:` ze stdout parsuje `parseLocalMetadata` (`ScadModules.tsx`).

---

## 2. Interpretacja zdjęć referencyjnych

Zdjęcia służą wyłącznie do zrozumienia *kategorii* mechanizmu. Nie odczytujemy z nich wymiarów ani nie odtwarzamy cudzego modelu (§11). Wymiary poniżej są szacunkami rzędu wielkości, a nie danymi projektowymi.

### 2.1 `orca-paste-1790544480170-8f28aa96…png`: sześć fidgetów na szarym tle (główna referencja)

- Sześć egzemplarzy tego samego typu mechanizmu w różnych kolorach.
- **Koło centralne:** zaokrąglony kwadrat (4 płaty) z okrągłym otworem. Na narożach otworu widać małe kostki w drugim kolorze.
- **Planety:** 4 sztuki. Ich *zewnętrzny obrys zębów* to zaokrąglony kwadrat. Wielkość jest zbliżona do koła centralnego. Zęby biegną nieprzerwanie wzdłuż boków i naroży, a ich podziałka wygląda na stałą wzdłuż krzywej. W środku jest kwadratowy otwór z zaokrąglonymi narożami i „pikselowymi” schodkowymi kostkami w drugim kolorze. To dekoracja albo element wielokolorowego wydruku, bez funkcji kinematycznej.
- **Pierścień:** wewnętrzna krzywa zębów jest falista. Zewnętrzny obrys obręczy podąża za nią ze stałą grubością ścianki. Przy powiększeniu (egzemplarz szary/zielony i turkusowy) naliczam około 12 wybrzuszeń. To zgadza się z przewidywaniem modelu `n_r = n_s + 2·n_p = 4 + 2·4 = 12` (§4.3).
- Planety mają różną orientację względem pierścienia, ale względem kierunku promieniowego wyglądają jak kopie obrócone o 90°. To zgadza się z symetryczną konfiguracją N = 4.
- Po bokach widać warstwę w drugim kolorze pod spodem (zieleń pod szarym, fiolet pod białym). To może być zmiana filamentu w połowie wysokości albo warstwowa (schodkowa) konstrukcja zębów. **Nie da się tego rozstrzygnąć ze zdjęcia.**

**Wniosek:** główny wzorzec to wariant kwadratowy, N = 4, sun ≈ planety, pierścień 12-płatowy.

### 2.2 `orca-paste-1790538511441-4f45db81…png`: cztery przekładnie na stole drukarki (obudowa „koło zębate”)

- Klasyczne okrągłe przekładnie planetarne z zębami skośnymi lub jodełkowymi. Mają 6–7 okrągłych planet z okrągłymi otworami.
- Obudowa ma obrys „koła zębatego” z prostokątnymi okienkami.
- **Nie dotyczy nieokrągłości.** To referencja dla zachowanego wariantu okrągłego i ewentualnego przyszłego stylu obudowy. W obecnym module `grip_style` nie ma okienek. Nie jest to zakres tego planu.

### 2.3 `orca-paste-1790538612746-54f41fdd…png`: te same przekładnie z zewnętrznym uzębieniem

- Okrągłe planetarne z widocznym uzębieniem skośnym. Obręcz ma na zewnątrz drobne zęby, co odpowiada `grip_style = 4` („Zewnętrzne ząbki”).
- **Nie dotyczy nieokrągłości.** Potwierdza, że wariant okrągły ma pozostać i działać jak dziś.

### 2.4 `orca-paste-1790538694322-a20d663a…png`: fidgety z kolcami i trójkątnymi otworami (kontrprzykład)

- Planety są **okrągłymi** kołami z otworami w kształcie zaokrąglonego trójkąta lub koniczyny z wkładkami na trzy piny. Koło centralne jest okrągłe z heksagonalną piastą. Obręcz ma kolce w drugim kolorze.
- **To dokładnie przypadek, którego zadanie wyklucza:** wielokątny otwór w okrągłym kole. Trójkątność jest tu wyłącznie dekoracyjna.
- Zdjęcie przydaje się jako źródło przyszłych pomysłów na obudowę (kolce, wkładki), ale nie jako wzorzec geometrii.

### 2.5 `orca-paste-1790538854416-59b4ef10…png`: szaro-zielony fidget w dłoni

- Ten sam typ co w §2.1, z bliska. Mamy 4 planety o obrysie zaokrąglonego kwadratu i koło centralne podobnej wielkości z palcem w otworze. Pierścień jest falisty, ma około 12 płatów, a zewnętrzny obrys jest równoległy do krzywej zębów.
- Na boku pierścienia widać zielone prostokątne „schodki” wzdłuż obwodu. Sugeruje to warstwową konstrukcję: druga warstwa ma zęby przesunięte lub inny kolor. **Hipoteza, niepotwierdzona.** Plan i tak proponuje schodkową jodełkę z niezależnych powodów (§4.10).
- Skala: średnica zewnętrzna jest porównywalna z szerokością dłoni, szacunkowo 80–95 mm. Otwór w kole centralnym mieści opuszek palca, około 15–18 mm. Oba wymiary są niepewne i nie służą jako dane projektowe. Pokazują jednak, że **wariant równych kół wymaga większej średnicy niż klasyczny** (§6.3).

### 2.6 Czego zdjęcia nie pokazują

- **Wariantu trójkątnego jako koła nieokrągłego nie ma na żadnym zdjęciu.** Trójkąty na §2.4 to otwory. Wariant trójkątny w tym planie jest wyprowadzony analogicznie (`n = 3`) i wymaga walidacji tak samo jak kwadratowy.
- Nie widać profilu zęba w przekroju osiowym, więc nie wiadomo, czy zęby są proste, skośne czy schodkowe. Nie widać też luzów ani wysokości modelu.

---

## 3. Definicja produktu

| Cecha | Wariant okrągły (zachowany) | Wariant kwadratowy | Wariant trójkątny |
|---|---|---|---|
| Krzywa podziałowa koła centralnego | okrąg | zaokrąglony kwadrat, 4 płaty | zaokrąglony trójkąt, 3 płaty |
| Krzywa podziałowa planety | okrąg | zaokrąglony kwadrat, 4 płaty | zaokrąglony trójkąt, 3 płaty |
| Krzywa podziałowa pierścienia | okrąg | falista, 12 płatów | falista, 9 płatów |
| Liczba planet | 3–12 (solver) | **4** | **3** |
| Uczucie w dłoni | równy obrót | pulsujący obrót: planety przyspieszają i zwalniają, lekko „oddychają” promieniowo | jak kwadrat, mocniej wyczuwalny |
| Moduł w katalogu | `planetary-fidget` (bez zmian) | `planetary-fidget-noncircular`, `shape = 0` | `planetary-fidget-noncircular`, `shape = 1` |

Obrót jest pulsujący, bo przełożenie chwilowe koła nieokrągłego zmienia się okresowo. To zaleta produktowa (inne „czucie” niż klasyk), ale też ryzyko: przy za dużej kanciastości pojawia się zacinanie (§11).

---

## 4. Model matematyczny i algorytm generowania

### 4.1 Oznaczenia

- `O`: wspólna oś koła centralnego (S) i pierścienia (R).
- `n_s`, `n_p`, `n_r`: liczba płatów (okres kształtu) krzywej podziałowej koła centralnego, planety i pierścienia.
- `N`: liczba planet. `t`: liczba zębów na płat.
- `r_X(θ)`: równanie biegunowe centroidy ciała X względem jego środka. `L_X`: długość (obwód) centroidy.
- `m`: moduł rozumiany jako podziałka wzdłuż centroidy, `p = π·m`.
- `s`: długość łuku wzdłuż centroidy koła centralnego (parametr ruchu).

### 4.2 Rodzina krzywych podziałowych

Bazowa rodzina (gładka, analityczne pochodne):

```
r(θ) = R · (1 + e₁·cos(n·θ) + e₂·cos(2n·θ))
```

- `e₁`: „kanciastość” (główny parametr UI).
- `e₂`: spłaszczenie boków (parametr zaawansowany albo stały). Ujemne `e₂` prostuje boki i zaostrza naroża.
- Warunek wypukłości krzywej biegunowej: `κ ∝ r² + 2r′² − r·r″ > 0`. Dla samego `e₁` daje to `e₁ < 1/(n² + 1)`, czyli **e₁ < 0,0588 dla kwadratu** i **e₁ < 0,10 dla trójkąta**. Powyżej tych wartości boki stają się wklęsłe.

  Wklęsłość jest dopuszczalna, ale ma dwa skutki: (a) wyklucza generowanie zębów zębatką prostą; (b) wymaga, by wypukłe naroże partnera miało mniejszy promień krzywizny niż wklęsły bok (§4.7, §4.12).

Solver w fazie 0 porówna tę rodzinę z alternatywą w postaci „superelipsy biegunowej” o regulowanym promieniu naroża. Wybierzemy tę, która przy tym samym wizualnym „kwadratowym” wyglądzie daje większy minimalny promień krzywizny.

### 4.3 Zasada zgodności płatów i liczby zębów

Płaty koła centralnego, planety i pierścienia muszą „przechodzić” przez siebie 1:1. Planeta przetaczająca się o jeden swój płat przesuwa się dokładnie o jeden płat koła centralnego i jeden płat pierścienia.

- Długości łuku płatów są równe: `L_S / n_s = L_P / n_p`. Przy `n_s = n_p` koło centralne i planety mają **równy obwód**, co zgadza się ze zdjęciami.
- W granicy kołowej (`e → 0`): `n_r = n_s + 2·n_p`. To analogia do `z_r = z_s + 2·z_p`. **Kwadrat: 4 + 8 = 12. Trójkąt: 3 + 6 = 9.**
- Zęby: `t` zębów na płat na każdym kole, więc `z_s = n_s·t`, `z_p = n_p·t`, `z_r = n_r·t`. Moduł wynika z obwodu: `m = L_P / (π·z_p)`. Dzięki temu każdy płat ma identyczny układ zębów, a obrót o okres płatu przenosi uzębienie w siebie. To konieczne dla §4.8.

### 4.4 Kinematyka: planeta toczy się po kole centralnym

Pracujemy w układzie związanym z kołem centralnym (S nieruchome). Planeta jest ciałem swobodnym, bo fidget nie ma jarzma.

1. Parametryzujemy centroidy łukiem: `S(s)`, `P(σ)` z jednostkowymi stycznymi `T_S`, `T_P`.
2. Toczenie bez poślizgu: punkt styku to `C₁(s) = S(s)` na kole centralnym i `P(σ₀ − s)` na planecie. `σ₀` to faza startowa, np. naroże koła centralnego naprzeciw środka boku planety.
3. Pozycja planety: obrót `β(s)` taki, że `Rot(β)·T_P = −T_S` (kierunki przeciwne, bo obieg jest przeciwny), oraz przesunięcie `c(s) = S(s) − Rot(β)·P(σ₀ − s)`.
4. Chwilowy środek obrotu planety względem S leży w `C₁`.

W wariancie kołowym środek planety porusza się po okręgu. W nieokrągłym **promień orbity środka planety zmienia się okresowo** (wstępnie ±0,4–0,8% dla umiarkowanej kanciastości). Fidget bez jarzma to dopuszcza. Trzeba jednak sprawdzić kolizje sąsiednich planet w całym cyklu (§4.12).

### 4.5 Centroida pierścienia z twierdzenia Aronholda–Kennedy’ego

Trzy ciała S, P i R mają chwilowe środki obrotu względnego I_SP = C₁, I_PR i I_SR = O. **Leżą one na jednej prostej.** Zatem punkt styku planety z pierścieniem leży na promieniu z `O` przez `C₁`, po przeciwnej stronie planety:

```
C₂(s) = najdalsze przecięcie półprostej O→C₁(s) z krzywą planety w położeniu (β(s), c(s))
```

Prędkość planety w `C₂` wynosi `ω_P·|C₁C₂|`, a punktu pierścienia w `C₂` wynosi `χ′·|OC₂|`. Obie są prostopadłe do promienia. Toczenie bez poślizgu daje kinematyczne prawo względnego obrotu pierścienia:

```
dχ_kin/ds = (dβ/ds) · |C₁C₂| / |OC₂|
```

Centroida pierścienia we własnym układzie: `R(s) = Rot(−χ(s)) · C₂(s)`.

### 4.6 Domknięcie pierścienia: wynik wstępny i korekta

Okres płatu pierścienia to `Δθ_R = Δθ_{C₂} − Δχ` na jeden płat koła centralnego. Pierścień domyka się, gdy `2π / |Δθ_R|` jest liczbą całkowitą `n_r`.

**Wstępne obliczenia** (prototyp numeryczny poza repozytorium, 20 000 próbek krzywej, rodzina `r = 1 + e·cos(nθ)`, sun = planeta, faza „naroże naprzeciw boku”):

| Kształt | e | naturalne `n_r` (po odjęciu błędu dyskretyzacji odniesionego do okręgu) | zmiana promienia orbity planety |
|---|---|---|---|
| kwadrat | 0,00 | 12,000 | 0 |
| kwadrat | 0,03 | 12,007 | ≈ 0,1% |
| kwadrat | 0,06 | 12,021 | ≈ 0,35% |
| kwadrat | 0,09 | 12,070 | ≈ 0,75% |
| trójkąt | 0,03 | 9,002 | ≈ 0,1% |
| trójkąt | 0,06 | 9,015 | ≈ 0,35% |
| trójkąt | 0,09 | 9,039 | ≈ 0,75% |

Dodatkowe obserwacje z prototypu:

- Próba „dostrojenia” kształtu koła centralnego (osobne `e_s`, skala dopasowana do równości obwodów płatów) **nie sprowadziła** `n_r` do liczby całkowitej w badanym zakresie. Residuum było zawsze dodatnie.
- Wcześniejszy model ze stałym promieniem jarzma dał podobny wniosek analitycznie. Średnie `r_p/(a − r_p)` (funkcja wypukła) i `r_p/(a + r_p)` (funkcja wklęsła) odchylają się z nierówności Jensena w kierunkach, których nie da się jednocześnie skompensować.

**Hipoteza robocza, do potwierdzenia w fazie 0:** przy zgodności płatów 1:1 dokładne `n_r = n_s + 2·n_p` osiągają tylko okręgi. Dla kształtów nieokrągłych naturalne `n_r` jest nieco większe.

**Rozwiązanie (ściśle sprzężone):**

1. Narzucamy prawo `χ(s) = k · χ_kin(s)`, gdzie `k = Δχ* / Δχ_kin(płat)` oraz `Δχ* = 2π/n_s + 2π/n_r` (moduł; znak zgodnie z konwencją obiegu). Wstępnie `k − 1 ≈ 0,0002–0,0016`.
2. Ruch względny planeta↔pierścień jest wtedy okresowy z okresem dokładnie `2π/n_r`, więc pierścień domyka się z definicji.
3. Zęby pierścienia wyznaczamy jako **obwiednię zębów planety w tym ruchu** (§4.7). Obwiednia dowolnego regularnego ruchu jednoparametrowego jest sprzężona z narzędziem. Sprzężenie *nie wymaga*, żeby centroida pierścienia pokrywała się z przyjętą „ładną” krzywą. Jej chwilowy środek `I_PR` przesuwa się wzdłuż promienia o ułamek `m`. Jest to odpowiednik przesunięcia zarysu w kołach okrągłych.
4. Walidujemy regularność obwiedni (brak podcięcia, brak ostrych wierzchołków) i ograniczamy `|k − 1| ≤ k_max`. Wstępnie `k_max = 0,5%`, do kalibracji w fazie 0. To pośrednio ogranicza maksymalną kanciastość `e₁`.

W fazie 0 szukamy też dokładnych rozwiązań w bogatszych rodzinach (niesymetryczna faza startowa, wyższe harmoniczne, różne kształty S i P). Jeśli się znajdą, korekta `k` będzie zbędna. Plan nie zakłada jednak ich istnienia.

### 4.7 Generowanie zębów

**Zasada:** jedna planeta-wzorzec jest narzędziem dla wszystkich par. Twierdzenie Camusa i teoria obwiedni (Litvin) gwarantują sprzężenie profili generowanych przez to samo narzędzie w danym ruchu względnym.

**(a) Planeta: wirtualny dłutak (koło narzędziowe).**

- Okrągłe koło ewolwentowe o `z_c ≈ 8–12` zębach i kącie przyporu 20–25° toczy się *po zewnętrznej stronie* centroidy planety. Planeta powstaje jako wypełnienie „krzywa + m” pomniejszone o sumę pozycji narzędzia.
- Warunek: promień podziałowy dłutaka `r_c < 0,8 · min |ρ_wklęsłe|` centroidy planety.
- Zębatka prosta jest dopuszczalna tylko przy krzywej w pełni wypukłej. Dłutak obsługuje oba przypadki, więc jest domyślny.
- Zęby rozmieszczamy w stałych odstępach łuku `π·m`. Oś symetrii zęba (albo wrębu) leży na osi symetrii płatu, co zapewnia powtarzalność płatów.

**(b) Koło centralne: obwiednia planety-narzędzia.**

```
S_2D = blank_S  \  ⋃_{j} [ Rot/Trans(β(s_j), c(s_j)) · Tool_P ]
Tool_P = offset(+b_n/2) planety z wydłużoną głową (+ c_tip)
blank_S = obszar ograniczony krzywą S(θ) przesuniętą o +m (głowa zęba)
```

- Próbki `s_j`: wstępnie 24–48 na podziałkę. Gęstość dobieramy tak, żeby „ząbkowanie” obwiedni (błąd cięciwy) było mniejsze niż 0,02 mm.
- Wystarczy wygenerować **jeden płat** (wycinek kątowy z marginesem ±½ płatu), przyciąć klinem i skopiować `n_s` razy obrotem. To `n_s` razy mniej operacji logicznych.

**(c) Pierścień: obwiednia planety-narzędzia w ruchu z korektą `k`.**

- Analogicznie w układzie pierścienia: `R_2D = obręcz \ ⋃ poses`. Generujemy jeden płat i kopiujemy go `n_r` razy.

**(d) Alternatywa analityczna (optymalizacja, faza 4).** Zamiast operacji logicznych liczymy punkty obwiedni z równania zazębienia `n · v₁₂ = 0` (Litvin). Otrzymujemy listy punktów i bezpośredni `polygon()`, co jest szybsze i pozwala na łączenie warstw przez `polyhedron`. Metoda jest trudniejsza do zrobienia odpornie (osobliwości, pętle), dlatego nie jest pierwszym wyborem.

### 4.8 Fazowanie przekładni (phasing) i liczba planet

- W układzie koła centralnego planeta `k` musi być kopią planety 0 w stanie przesuniętym o całkowitą liczbę płatów `j_k`. Cały mechanizm jest wtedy symetryczny względem obrotu o `2π·j_k/n_s`.
- Warunek zgodności z pierścieniem: `j_k · (2π/n_s) ≡ 0 (mod 2π/n_r)`.
- Przy równomiernym rozstawie `N` planet: **N | n_s oraz N | n_r**, czyli `N | gcd(n_s, n_r)`. Dodatkowo `N ≥ 3`: przy N ≤ 2 koło centralne i pierścień nie są centrowane w kierunku prostopadłym i mechanizm „lata”.
- Z `z_X = n_X·t` wynika, że uzębienie też ma tę symetrię. Wystarczy wygenerować planetę 0 i powielić ją obrotem o `2π/N` wokół `O`, podobnie jak `planet_phase()` w module klasycznym.
- Rozstawy niesymetryczne i fazy pół-płatowe są kinematycznie możliwe w szczególnych przypadkach (§5.4), ale produkt ich nie udostępnia.

### 4.9 Luz FDM

Profile luzów pozostają zgodne z klasykiem, żeby użytkownik miał te same odczucia:

| Parametr | Ciasny | Standardowy | Luźny | Uwagi dla nieokrągłych |
|---|---|---|---|---|
| luz normalny `b_n` (łącznie na parę) | 0,22 | 0,32 | 0,44 mm | realizowany wyłącznie jako `offset(+b_n/2)` narzędzia przy cięciu S i R (patrz niżej) |
| luz głowy `c_tip` | 0,08 | 0,14 | 0,22 mm | wydłużenie głowy narzędzia |
| odstęp planet–planeta | 0,25 | 0,40 | 0,58 mm | **minimum w całym cyklu**, nie w pozycji startowej |
| ścianka minimalna | 1,2 mm (sun), 0,8 mm (planeta), 1,8 mm (obręcz) | | | |

- Luz nadajemy wyłącznie po stronie narzędzia tnącego S i R: `offset(r = +b_n/2)`. Planeta zostaje nominalna. Luz obwodowy na każdą flankę wynosi `b_n/2`, a luz obrotowy pary (suma po obu flankach) `b_n`. Luzu nie nakładamy podwójnie (na narzędzie i na planetę). Faza 3 kalibruje na wydruku F1, czy potrzebne jest dodatkowe zmniejszenie planety.
- Offset po obrysie to luz *normalny*. Przy zmiennej krzywiźnie jest to właściwsze niż luz kątowy stosowany w klasyku (`rad_to_deg(b/(2·rp))`), bo dla nieokrągłych nie istnieje jedno `rp`.
- **Pierwsza warstwa (elephant foot):** fazka 0,3–0,4 mm × 45° na dolnych krawędziach *powierzchni współpracujących* (zęby S, P i R), żeby uniknąć zgrzania. Wymaga to generowania warstwy dolnej z profilu `offset(−0,3)` (§4.11).

### 4.10 Osiowe zatrzymanie print-in-place: schodkowa jodełka

**Dlaczego nie `twist`:** `linear_extrude(twist=τ)` obraca cały przekrój wokół osi. Dla okręgu jest to równoważne przesunięciu zębów wzdłuż krzywej. Dla nieokrągłego profilu obrót przemieszcza płaty, a nie zęby, więc warstwy przestają być sprzężone. **Zakaz.**

**Konstrukcja:**

1. Dzielimy wysokość `H` na `K` warstw (domyślnie `K = 6`, zakres 4–8). Warstwa `i` ma przesunięcie fazy zębów wzdłuż łuku `δ_i`, np. profil V: `0, δ, 2δ, 2δ, δ, 0`. Unikalnych generacji jest tylko `K/2`.
2. Warstwa `i` planety to dłutak przesunięty o `δ_i` wzdłuż centroidy. Warstwa `i` koła centralnego i pierścienia to obwiednia *tej* warstwy planety. Centroidy i kinematyka są identyczne dla wszystkich warstw, bo przesunięcie fazy zęba nie zmienia toczenia.
3. **Warunek blokady:** ząb planety w warstwie `i` musi w rzucie osiowym zachodzić na ząb koła centralnego lub pierścienia w warstwie `i ± 1`. Wymaga to `δ ≥ b_n + 0,15·p` (wstępnie). Faza 0 liczy to numerycznie jako minimalne pole nakładania rzutów w całym cyklu.
4. **Warunek druku:** każdy stopień to półka o szerokości ≈ `δ`. Dla FDM przyjmujemy `δ ≤ 0,6 mm` przy warstwie 0,2 mm, do weryfikacji wydrukiem. Stopnie wypadają na granicach warstw druku: `H/K` jest wielokrotnością 0,2 mm.
5. Warstwy łączymy przez `union()` z nakładaniem 0,01 mm (bez szczelin manifoldu).

**Alternatywa (fallback, tylko przy no-go w fazie 3):** wargi osiowe na pierścieniu nad i pod planetami (półki 0,8–1,2 mm) albo stożkowe fazowanie głów. Zmieniają one charakter „otwartego” fidgetu, więc wymagają decyzji produktowej.

### 4.11 Fazki krawędzi (chamfer)

- Dolna fazka przeciw „stopie słonia” na współpracujących krawędziach (§4.9) domyślnie jest włączona.
- Górna fazka estetyczna 0,4 mm na zewnętrznym obrysie obręczy i na otworze na palec (komfort).
- Fazki robimy przez `offset()` warstw skrajnych. `minkowski()` jest zbyt kosztowny w WASM.

### 4.12 Walidacja geometryczna (asercje i ostrzeżenia w SCAD, testy w oracle)

| Warunek | Reguła | Reakcja |
|---|---|---|
| Wypukłość / krzywizna | `ρ_min(wypukłe) ≥ 2,5·m`; `|ρ_wklęsłe| ≥ 1,25·r_c` | `assert` z komunikatem „Zmniejsz kanciastość” |
| Korekta pierścienia | `|k − 1| ≤ k_max` | `assert` |
| Regularność obwiedni | grubość zęba na głowie `s_a ≥ 0,25·m` oraz ≥ 0,4 mm; brak podcięcia (grubość u stopy ≥ grubość na podziałce · 0,8) | oracle: test; SCAD: ostrzeżenie `WARNING:` |
| Odstęp planet | `min_cykl dist(P_k, P_{k+1}) ≥ planet_spacing_clearance` | `assert` |
| Otwór na palec | `hole/2 ≤ min_θ r_root,S(θ) − 1,2 mm` | automatyczne zmniejszenie + `WARNING:` (jak `safe_grip_depth`) |
| Otwór w planecie | kształt = krzywa stopy planety `offset(−max(0,8 mm; wall))`, skalowany procentem | automatyczne ograniczenie |
| Liczba zębów | `t` całkowite, `m ∈ [0,6; 1,6] mm` | solver dobiera `t` |
| Symetria | `N | gcd(n_s, n_r)` | wymuszone przez wariant, nie przez UI |
| Ścianka obręczy | `min_θ (r_outer − r_root,R) ≥ 1,8 mm` | wymuszone (obrys równoległy) |

---

## 5. Warianty

### 5.1 Kwadratowy (`shape = 0`)

- `n_s = n_p = 4`, `n_r = 12`, `N = 4`, `z = (4t, 4t, 12t)`.
- Domyślnie `e₁` ≈ 0,05 (wypukły, bezpieczny), zakres UI do granicy walidacji (wstępnie ≈ 0,09).
- Planeta i koło centralne mają równy obwód. Koło centralne jest *prawie* kopią planety obróconą o 45°. Nie jest identyczne, bo różni się obwiednią.

### 5.2 Trójkątny (`shape = 1`)

- `n_s = n_p = 3`, `n_r = 9`, `N = 3`, `z = (3t, 3t, 9t)`.
- Przy `n = 3` przeciwległy punkt planety (`ψ + π`) wypada na środku boku, a nie na narożu. Styk z pierścieniem ma więc inną fazę niż z kołem centralnym. Model z §4.4–4.5 obsługuje to bez zmian.
- Większa granica wypukłości (`e₁ < 0,10`), ale silniejsze pulsowanie przełożenia. Wymaga osobnej kalibracji fizycznej.
- Brak referencji fotograficznej (§2.6), więc przed publikacją potrzebny jest obowiązkowy wydruk testowy.

### 5.3 Okrągły (zachowany)

- Moduł `planetary-fidget` **bez zmian w geometrii, parametrach i domyślnych wartościach**.
- Nowy moduł **nie** oferuje „kształtu okrągłego”. `e₁ = 0` jest tylko przypadkiem testowym (§9.1), który porównuje oracle z klasyczną ewolwentą.

### 5.4 Warianty rozszerzone (opcjonalne, nie w MVP)

| Nazwa robocza | n_s / n_p / n_r | N dozwolone | Uwagi |
|---|---|---|---|
| Kwadrat+ (sun 8-płatowy) | 8 / 4 / 16 | 4 (8 zwykle się nie mieści) | sun 2× obwód planety; większy otwór na palec przy tej samej średnicy |
| Trójkąt+ (sun 6-płatowy) | 6 / 3 / 12 | 3, 6 (6 do sprawdzenia kolizji) | jw. |
| Mieszane (sun 4 / planety 3) | 4 / 3 / 10 | brak N ≥ 3 (`gcd(4,10) = 2`) | **odrzucone** |
| Mieszane (sun 3 / planety 4) | 3 / 4 / 11 | brak (`gcd = 1`) | **odrzucone** |

Warianty rozszerzone wchodzą dopiero po DoD dla MVP. Muszą przejść te same bramki.

---

## 6. Macierz parametrów UI i ograniczeń

### 6.1 Parametry nowego modułu (Customizer; parser obecny, bez zmian)

| Sekcja | Parametr | Typ / zakres | Domyślnie | Uwagi |
|---|---|---|---|---|
| Główne | `output_mode` | `[0:Kompletny print-in-place,1:Kolorowy podgląd,2:Tylko pierścień,3:Tylko koło centralne,4:Jedna planeta]` | 0 | nazwa ≠ `mode` (§1.3) |
| Główne | `shape` | `[0:Kwadratowy,1:Trójkątny]` | 0 | wyznacza `n_s, n_p, n_r, N` |
| Główne | `outer_diameter` | `[70:1:130]` mm | 90 | większe niż klasyk, bo sun ≈ planety |
| Główne | `squareness` | `[0:1:100]` % | 55 | mapowane na `e₁ ∈ [0, e₁_max(shape)]`; UI nie pokazuje surowego `e` |
| Główne | `tooth_style` | `[0:Drobne,1:Standardowe,2:Grube]` | 1 | cel `m` 0,8 / 1,0 / 1,25 mm; solver dobiera całkowite `t` |
| Główne | `gear_thickness` | `[6:0.2:14]` mm | 8 | zaokrąglane do wielokrotności `K·0,2` |
| Dopasowanie | `fit_profile` | `[0:Ciasny,1:Standardowy,2:Luźny]` | 1 | §4.9 |
| Dopasowanie | `first_layer_chamfer` | bool | true | §4.11 |
| Otwory | `finger_hole_diameter` | `[10:1:24]` mm | 16 | auto-ograniczenie + `WARNING:` |
| Otwory | `planet_holes` | bool | true | otwór = zaokrąglony kwadrat/trójkąt |
| Otwory | `planet_hole_percent` | `[30:1:65]` % | 50 | |
| Obudowa | `rim_style` | `[0:Równoległa do fali,1:Gładka okrągła]` | 0 | 0 jak na zdjęciach; 1 = okrąg opisany na obręczy |
| Zaawansowane | `axial_layers` | `[4:2:8]` | 6 | `@advanced`; K warstw jodełki |
| Zaawansowane | `layer_shift_percent` | `[20:5:50]` % podziałki | 30 | `@advanced`; δ, z auto-limitem ≤ 0,6 mm |
| Zaawansowane | `side_flatness` | `[0:1:100]` % | 0 | `@advanced`; `e₂`, dostępne po fazie 0 tylko jeśli poprawia krzywiznę |
| Zaawansowane | `pressure_angle` | `[20:25]` | 25 | `@advanced`; kąt dłutaka |
| Ukryte | `envelope_samples`, `curve_samples`, `k_max` | — | — | sekcja „Ukryte” |

**Nie ma parametru „liczba planet”.** Wynika ona z kształtu. Użytkownik zobaczy ją w `INFO:liczba_planet=…`. Nie ma też `helix_angle`, bo twist jest zabroniony (§4.10). Ozdobne style obudowy z klasyka (`grip_style`) **nie są przenoszone w MVP**, bo wymagają adaptacji do falistej obręczy. To osobne zadanie.

### 6.2 Macierz liczby planet

| Kształt | n_s | n_p | n_r | gcd(n_s,n_r) | N dozwolone (N ≥ 3) | N w produkcie |
|---|---|---|---|---|---|---|
| Okrągły (klasyk) | — | — | — | — | 3–12 (solver: `(zs+zr) % N = 0`, odstęp) | 3–12 |
| Kwadratowy | 4 | 4 | 12 | 4 | 4 | **4** |
| Trójkątny | 3 | 3 | 9 | 3 | 3 | **3** |
| Kwadrat+ | 8 | 4 | 16 | 8 | 4, 8 | 4 (opcja) |
| Trójkąt+ | 6 | 3 | 12 | 6 | 3, 6 | 3 / 6 (opcja) |

Dla N = 4 przy równych kołach: środki planet leżą ≈ 2R od osi, a odległość sąsiadów wynosi ≈ 2,83R. Obrys głów planety ma ≤ 2·(R(1 + e₁) + m). Dla `e₁ ≤ 0,09` i `m ≈ R/12` zapas wynosi około 0,6R. Ostateczną weryfikacją jest minimum w cyklu z §4.12.

### 6.3 Relacja średnica ↔ otwór na palec (szacunek do weryfikacji w fazie 0)

Dla równych kół: `D ≈ 2·(3R(1 + e₁) + 1,25m + c + rim)` i `hole ≤ 2·(R(1 − e₁) − 1,25m − c − 1,2)`.

Przykład dla kwadratu, `e₁ = 0,05`, `m ≈ 1`, `rim = 3,8`:

- `D = 90 mm` → `R ≈ 12,6 mm` → otwór ≤ ≈ 18 mm;
- `D = 70 mm` → otwór ≤ ≈ 12 mm.

Stąd domyślne 90 mm i minimum 70 mm. Dokładne progi wyliczy solver, a UI pokaże je komunikatem.

---

## 7. Decyzja: jeden SCAD czy osobne moduły

**Decyzja: nowy, osobny moduł `examples/scad/planetary-fidget-noncircular/`. Kwadrat i trójkąt są w jednym pliku `main.scad`. Klasyk pozostaje nietknięty.**

Uzasadnienie:

1. **Brak regresji klasyka.** Jego solver (`gear_candidates`), zęby i twist są zasadniczo różne od potoku nieokrągłego. Wspólny plik wymusiłby rozgałęzienia w każdej funkcji i zwiększył ryzyko regresji. Właśnie to stało się w `a0dbf70`.
2. **Parser nie ma warunkowej widoczności.** W jednym SCAD użytkownik klasyka widziałby „kanciastość” i „warstwy”, a użytkownik nieokrągłego widziałby „liczbę planet 3–12” i „kąt skosu”, które nic by nie robiły.
3. **Inny budżet wydajności.** Obwiednie są wyraźnie cięższe (§8.3), a klasyk ma pozostać szybki.
4. **Kwadrat i trójkąt dzielą 100% algorytmu** i różnią się tylko `(n_s, n_p, n_r, N)` oraz granicami `e₁`. Osobne moduły oznaczałyby duplikację biblioteki: `include` nie może wyjść poza katalog modułu (`validate_source_tree`), więc biblioteka musiałaby być skopiowana. Jeden moduł z przełącznikiem `shape` jest prostszy.
5. Produktowo można później dodać dwa „presety” w katalogu. Nie wymaga to kopii kodu, tylko różnych domyślnych `-D`. Jeśli platforma nie obsługuje presetów, zostaje jeden moduł.

Struktura:

```
examples/scad/planetary-fidget-noncircular/
  module.json              # id: planetary_fidget_noncircular, version 0.1.0 → 1.0.0 po DoD
  main.scad                # parametry Customizera, wybór output_mode, raport INFO/WARNING
  lib/ncg_curves.scad      # rodziny centroid, łuk, krzywizna, próbkowanie
  lib/ncg_kinematics.scad  # toczenie planety, Kennedy, prawo χ, korekta k
  lib/ncg_teeth.scad       # dłutak, obwiednie, warstwy jodełki, luzy, fazki
  lib/ncg_validate.scad    # asercje i ostrzeżenia
```

Licencja kodu: własny kod Litho. Nie kopiujemy kodu z BOSL2 ani z innych bibliotek (BOSL2 służy tylko jako punkt odniesienia dla konwencji ewolwenty, §14).

---

## 8. Architektura integracji z obecnym WebAssembly

### 8.1 Zasada

Całe generowanie odbywa się w przeglądarce, w istniejącym Web Workerze (`scadWasm.worker.ts`) z `@lofcz/openscad-wasm` i `--backend Manifold`. **Nie trzeba zmieniać frontendu ani backendu, poza rejestracją nowego przykładu i aktualizacją testu `test_scad_repository.py`.** Nie ma renderowania po stronie serwera, a backend nadal tylko przechowuje i paczkuje pliki modułu (ZIP).

### 8.2 Gdzie liczyć numerykę

| Opcja | Opis | Ocena |
|---|---|---|
| **A. Czysty OpenSCAD (wybrana)** | Całkowanie łuku, toczenie, przecięcie promienia z wielokątem, korekta `k` i wybór `t` jako funkcje SCAD (listy składane, rekurencja ogonowa). Obwiednie przez `difference()`/`union()` 2D. | Moduł jest samowystarczalny i działa też w desktopowym OpenSCAD po pobraniu ZIP. Brak zmian w potoku. |
| B. Prekompilacja w TS w workerze | Worker liczy punkty i wstrzykuje plik `generated.scad` do FS WASM przed `callMain`. | Łamie model „moduł = SCAD”, wymaga zmian frontendu i utrudnia pobieranie. Odrzucona dla MVP. |
| C. Tablica stałych w `lib/` | Offline wyliczone `(e₁ → a, k, σ₀, e₂)` dla siatki wartości „kanciastości”, wygenerowane skryptem deweloperskim i zacommitowane jako dane. | **Fallback**, jeśli A jest za wolne w części numerycznej. To nie jest renderowanie serwerowe: kilka liczb liczonych raz przy budowie. |

### 8.3 Budżet wydajności (bramka w fazie 2)

- Numeryka: ≤ 2 s w WASM (próbkowanie 2000–4000 punktów na krzywą).
- Obwiednie: jeden płat na koło × `K/2` unikalnych warstw. Szacunkowo `(24–48 poz./podziałkę) × t` pozycji narzędzia na płat. Operacje 2D w Clipperze są rzędu setek wielokątów na płat.
- **Cel:** pełny print-in-place ≤ 30 s na referencyjnym laptopie (Chrome, 4 rdzenie; WASM jest jednowątkowy), podgląd `output_mode = 1` ≤ 15 s. **Limit twardy:** 90 s albo przekroczenie pamięci WASM. Wtedy przechodzimy na opcję C i/lub metodę analityczną z §4.7(d).
- Pomiar: `durationSeconds` z workera, logowany w teście E2E (§9.1).

### 8.4 Kontrakt wyjścia

- `echo("INFO:kształt=…")`, `INFO:liczba_planet`, `INFO:zęby_koła_centralnego/planety/pierścienia`, `INFO:moduł_zęba`, `INFO:korekta_pierścienia_k`, `INFO:min_odstęp_planet`, `INFO:rzeczywista_średnica`. Te same prefiksy parsuje już `parseLocalMetadata`.
- `assert(...)` z komunikatami po polsku. Worker mapuje je na „Wybrane parametry tworzą nieprawidłową geometrię”. Rozważyć (poza zakresem) przekazywanie treści asercji do UI.
- Wyjście STL i 3MF jak dziś. `output_mode = 1` koloruje S, P i R (3MF zachowuje kolory tylko przy obsłudze przez eksporter, do sprawdzenia).

---

## 9. Plan testów

### 9.1 Automatyczne

**Oracle referencyjny (TypeScript, Node, Vitest; katalog np. `tools/noncircular-oracle/`, uruchamiany w CI frontendu):**

1. **Granica kołowa:** `e₁ = 0` daje `n_r = n_s + 2n_p`, `k = 1`, orbitę planety o stałym promieniu 2R, a profile zębów zgodne z ewolwentą w tolerancji 0,01 m.
2. **Domknięcie:** dla siatki `(shape, e₁, tooth_style, D)` pierścień domyka się (`|R(2π) − R(0)| < 1e-6·D`), `|k − 1| ≤ k_max`, `t` całkowite.
3. **Symetria i fazowanie:** obrót całego zespołu o `2π/N` odtwarza zespół (odległość Hausdorffa < 0,01 mm).
4. **Symulacja zazębienia:** 2000 kroków pełnego cyklu (co najmniej `lcm` okresów płatów):
   - brak przenikania wielokątów S/P/R/P (pole przecięcia = 0 przy luzie nominalnym);
   - luz minimalny ≥ 0,5·`b_n` i maksymalny ≤ 2·`b_n` (brak „dziur”, w których planeta traci prowadzenie);
   - liczba przyporu ≥ 1,1 w każdej chwili.
5. **Regularność obwiedni:** grubość głowy, brak podcięcia, brak samoprzecięć wielokątów.
6. **Blokada osiowa:** pole nakładania rzutów warstw `i`/`i ± 1` > 0 w każdej chwili cyklu.
7. **Planety:** minimalny odstęp w cyklu ≥ `planet_spacing_clearance`.

**SCAD w WASM (Node, ten sam pakiet `@lofcz/openscad-wasm`, rozszerzenie `scadWasm.test.ts`):**

8. Render każdego wariantu × `fit_profile` × {D min, D domyślne, D max}: kod wyjścia 0, STL jest manifoldem (1 bryła na część), a liczba brył w print-in-place wynosi `2 + N`.
9. Zgodność SCAD ↔ oracle: wartości `INFO:` (zęby, m, k, min odstęp) równe z tolerancją 1e-3. Eksport 2D (`--export-format svg` dla przekroju warstwy) porównany z wielokątami oracle (Hausdorff < 0,02 mm).
10. Wydajność: czas renderu ≤ budżet z §8.3 (test oznaczony jako „perf”, raportowany, a nie flaky-fail).
11. Parametry niedozwolone dają oczekiwaną asercję, np. `outer_diameter = 70` z `finger_hole_diameter = 24` daje `WARNING` i auto-zmniejszenie; `squareness = 100` z drobnymi zębami daje `assert` albo auto-limit.

**Regresja klasyka:**

12. `backend/tests/test_scad_parser.py` i `test_scad_repository.py`: klasyczny moduł ma te same parametry, domyślne wartości i wersję co w `74e8487`. Nowy moduł parsuje się bez ostrzeżeń.
13. Golden render klasyka (domyślne parametry): hash lub objętość STL i wartości `INFO:` są niezmienione względem `74e8487`.

### 9.2 Fizyczne (obowiązkowe przed publikacją; nie da się ich zastąpić symulacją)

Macierz minimalna: PLA na drukarce referencyjnej, warstwa 0,2 mm, 3 obrysy, bez podpór.

| # | Próbka | Cel | Kryterium |
|---|---|---|---|
| F1 | Kupon luzów: pasek 3 par S–P (każdy `fit_profile`), wysokość 4 mm, bez jodełki | kalibracja `b_n` dla krzywizn nieokrągłych | co najmniej „Standardowy” rozłącza się palcami bez narzędzi |
| F2 | Kwadrat, D = 90, domyślne | działanie print-in-place | uwolnienie ≤ 30 s ręcznie; ≥ 100 pełnych obrotów bez zacięcia |
| F3 | Kwadrat, `squareness` max | granica kanciastości | brak zacięć na narożach; subiektywne „pulsowanie” akceptowalne |
| F4 | Trójkąt, D = 90 | działanie wariantu bez referencji | jak F2 |
| F5 | Kwadrat, K = 4 / 6 / 8, δ min/max | blokada osiowa i jakość półek | planety nie wypadają przy wstrząsaniu; półki bez nitek > 0,3 mm |
| F6 | PETG, profil „Luźny” | drugi materiał | jak F2 |
| F7 | Długotrwałość: F2 po 1000 obrotach | zużycie | brak widocznego starcia głów; luz wzrasta ≤ 0,1 mm (pomiar szczelinomierzem) |
| F8 | Druga drukarka (inna kinematyka) | przenośność | co najmniej „Luźny” działa |

Każdy wynik trafia do `docs/` (protokół: parametry, zdjęcie, uwagi).

---

## 10. Etapy implementacji z kryteriami go/no-go

| Faza | Zakres | Wyjście | **GO** gdy | **NO-GO / reakcja** |
|---|---|---|---|---|
| **0. Oracle i dowód wykonalności** (TS, bez SCAD) | Rodziny krzywych, kinematyka, Kennedy, korekta `k`, dłutak, obwiednie, symulacja kolizji; poszukiwanie dokładnych rozwiązań bez `k` | `tools/noncircular-oracle`, testy 1–7, raport liczbowy w `docs/` | Kwadrat i trójkąt: dla co najmniej 3 wartości `e₁` z widocznym efektem (wizualnie „kwadratowe”) wszystkie testy 1–7 przechodzą, `|k − 1| ≤ 0,5%` | Jeśli regularne obwiednie wychodzą tylko dla `e₁` tak małych, że kształt jest ledwie widoczny: stop i decyzja produktowa (np. tylko Kwadrat+ z większym sun, albo rezygnacja). **Nie** przechodzimy na skróty z §11. |
| **1. SCAD: numeryka** | `lib/ncg_curves`, `ncg_kinematics`, `ncg_validate`; raport `INFO:` | moduł renderuje centroidy (2D) | wartości `INFO:` zgodne z oracle (test 9) | rozbieżność > 1e-3: poprawić przed fazą 2 |
| **2. SCAD: zęby 2D + wydajność** | dłutak, obwiednie jednego płatu, powielanie, luz | `output_mode` 2/3/4 i przekrój 2D | Hausdorff do oracle < 0,02 mm; czas ≤ budżet §8.3 | za wolno: opcja C (tablica) i/lub §4.7(d) przed dalszymi krokami |
| **3. 3D: jodełka schodkowa, fazki, print-in-place** | warstwy, fazki, otwory, obręcz | pełny model 3D, testy 8, 10, 11 | manifold, `2 + N` brył, testy zielone; **wydruki F1, F2, F5 pozytywne** | F5 negatywne: fallback wargi osiowe (decyzja produktowa); F1/F2: rekalibracja luzów |
| **4. Wariant trójkątny i kalibracja** | granice `e₁`, wydruki F3, F4, F6 | tabela limitów | F3, F4, F6 pozytywne | trójkąt nie działa: publikujemy tylko kwadrat, trójkąt pozostaje ukryty (`shape` z jedną opcją) |
| **5. Integracja produktu** | `module.json`, rejestracja przykładu, test `test_scad_repository.py`, testy regresji 12–13, opisy UI | PR do `main` | wszystkie testy + F7, F8 | brak |
| **6. (opcjonalnie) Rozszerzenia** | Kwadrat+, Trójkąt+, style obudowy | osobne PR | te same bramki | — |

---

## 11. Ryzyka i zakazane skróty

### 11.1 Ryzyka

| Ryzyko | Prawdopodobieństwo | Skutek | Mitygacja |
|---|---|---|---|
| Hipoteza z §4.6 jest prawdziwa, a korekta `k` daje nieregularne obwiednie przy dużej kanciastości | średnie | niższy limit `e₁`, mniej „kwadratowy” wygląd | faza 0 mierzy limit; `e₂` (spłaszczenie boków) jako dźwignia wizualna |
| Wydajność obwiedni w WASM | średnie | render > 90 s | jeden płat + powielanie, `K/2` unikalnych warstw, opcja C, metoda analityczna |
| Schodkowa jodełka nie trzyma osiowo albo półki drukują się źle | średnie | planety wypadają albo się zgrzewają | test 6 + F5; fallback wargi osiowe |
| Pulsowanie przełożenia odczuwalne jako zacinanie | średnie | gorsze „czucie” | limit `e₁` z F3; preset „łagodny” jako domyślny |
| Promieniowe „oddychanie” planet powoduje stuki | niskie–średnie | hałas | limit zmiany promienia orbity (≤ 1%) jako warunek walidacji |
| Różnice między drukarkami (luz) | wysokie | nie rozłącza się | 3 profile luzu, F8 |
| Regresja klasyka | niskie (osobny moduł) | utrata działającego produktu | testy 12–13, zakaz edycji `planetary-fidget` w tym projekcie |
| Pamięć WASM przy dużych unionach | niskie–średnie | crash workera | limit próbek; pomiar w fazie 2 |

### 11.2 Zakazane skróty (każdy oznacza automatyczne odrzucenie w review)

1. **Okrągłe koła równej wielkości rozstawione w trójkąt lub kwadrat** (podejście z `a0dbf70`) jako „wariant kwadratowy lub trójkątny”.
2. **Okrągłe koło z wielokątnym otworem** udające wariant nieokrągły (jak na zdjęciu §2.4).
3. **Przyklejanie prostych zębów (zębatki) do boków wielokąta** i łatanie naroży łukami.
4. **`linear_extrude(twist=…)`** albo `rotate_extrude` dla profili nieokrągłych.
5. **Skalowanie lub `resize()` okrągłego koła do elipsy lub „kwadratu”** (`scale([1, 1.1])`, `hull()` kół, `offset` kwadratu z zębami). Zniekształca podziałkę i zarys, więc profile nie są sprzężone.
6. **Generowanie pierścienia jako „offsetu” koła centralnego lub planety** zamiast obwiedni w ruchu względnym.
7. **Losowe dopasowywanie kształtu „na oko”** bez domknięcia z §4.6 i bez symulacji kolizji z §9.1.
8. **Ukrywanie błędu domknięcia pierścienia w luzie** (np. zwiększenie `b_n` zamiast korekty `k`).
9. **Renderowanie po stronie serwera** albo przenoszenie obliczeń geometrii do backendu.
10. **Kopiowanie kodu, plików STL/3MF lub wymiarów z zamkniętych modeli** ze zdjęć referencyjnych albo z serwisów z modelami. Wolno korzystać wyłącznie z teorii z otwartych lub cytowanych źródeł (§14).
11. **Zmiana parametrów, domyślnych wartości lub geometrii klasycznego `planetary-fidget`** w ramach tego projektu.

---

## 12. Czego nie da się potwierdzić bez wydruku fizycznego

- Rzeczywisty luz konieczny do rozdzielenia elementów print-in-place przy zmiennej krzywiźnie. Wartości z klasyka są tylko punktem startu.
- Czy schodkowa jodełka (półki δ) drukuje się czysto i czy trzyma osiowo przy realnym tarciu.
- Subiektywne „czucie”: pulsowanie przełożenia, hałas, opór, bezwładność, satysfakcja z obrotu.
- Czy promieniowe „oddychanie” planet (±0,5–1%) i korekta `k` nie powodują stuków ani zakleszczeń przy luzie realnym (nierównomiernym po obwodzie wydruku).
- Trwałość po wielu obrotach i zachowanie w PETG.
- Wpływ stopy słonia i szwu (z-seam) na narożach planet.
- Czy konstrukcja na zdjęciach (§2.1, §2.5) jest dwukolorowa z powodów funkcjonalnych, czy tylko estetycznych. Nie jest to potrzebne do naszej implementacji, ale nie da się tego ustalić bez fizycznego egzemplarza.
- Wszystkie liczby z §4.6 i §6.3 pochodzą z szybkiego prototypu numerycznego i muszą zostać odtworzone przez oracle w fazie 0.

---

## 13. Definition of Done

Projekt nieokrągłego fidgetu jest ukończony, gdy **wszystkie** punkty są spełnione:

1. Istnieje moduł `examples/scad/planetary-fidget-noncircular/` z `main.scad`, `lib/*.scad` i `module.json`. Parser Customizera ładuje go bez ostrzeżeń, a parametry odpowiadają §6.1.
2. Warianty kwadratowy (N = 4, pierścień 12-płatowy) i trójkątny (N = 3, pierścień 9-płatowy) mają **prawdziwe nieokrągłe centroidy** koła centralnego, planet i pierścienia. Zęby są wyznaczone metodą dłutaka i obwiedni z §4.7. Żaden zakazany skrót z §11.2 nie występuje (review kodu z listą kontrolną).
3. Oracle TS istnieje w repozytorium, a testy 1–7 przechodzą w CI dla pełnej siatki parametrów.
4. Testy WASM 8–11 przechodzą. Wyniki SCAD są zgodne z oracle (§9.1, test 9).
5. Pełny render print-in-place mieści się w budżecie z §8.3 na referencyjnym sprzęcie. Czas jest udokumentowany.
6. Całe generowanie odbywa się w przeglądarce przez istniejący worker WASM. Diff backendu ogranicza się do rejestracji przykładu i testów.
7. Klasyczny `planetary-fidget` jest bitowo niezmieniony (`main.scad`, `module.json`), a testy regresji 12–13 przechodzą.
8. Wydruki F1–F8 są wykonane, udokumentowane protokołem w `docs/` i pozytywne. Ewentualnie wariant trójkątny jest świadomie ukryty zgodnie z bramką fazy 4.
9. Limity (`e₁_max` na kształt, minimalna średnica, maksymalny otwór na palec) wynikają z pomiarów i są wymuszone w SCAD (asercje i ostrzeżenia).
10. Dokumentacja użytkownika (opis modułu, zalecenia druku) jest po polsku i uczciwie opisuje pulsujący charakter obrotu.

---

## 14. Źródła (teoria; bez kopiowania kodu)

- F. L. Litvin, A. Fuentes-Aznar, I. Gonzalez-Perez, K. Hayasaka, *Noncircular Gears: Design and Generation*, Cambridge University Press, 2009. Książka objęta prawem autorskim. Korzystamy wyłącznie z teorii (centroidy, generowanie zębatką i dłutakiem, warunki wypukłości, sprzężenie przez obwiednię), bez kopiowania treści ani kodu.
- F. L. Litvin, A. Fuentes, *Gear Geometry and Applied Theory*, 2nd ed., Cambridge University Press, 2004. Prawo autorskie. Równanie zazębienia i teoria obwiedni (§4.7(d)).
- Wikipedia, „Non-circular gear”, https://en.wikipedia.org/wiki/Non-circular_gear, licencja CC BY-SA 4.0. Definicje i przegląd.
- Wikipedia, „Instant centre of rotation” (sekcja o twierdzeniu Aronholda–Kennedy’ego), https://en.wikipedia.org/wiki/Instant_centre_of_rotation, CC BY-SA 4.0. Współliniowość chwilowych środków obrotu (§4.5).
- Wikipedia, „Involute gear”, https://en.wikipedia.org/wiki/Involute_gear, CC BY-SA 4.0. Zarys dłutaka.
- BOSL2 (BelfrySCAD), https://github.com/BelfrySCAD/BOSL2, licencja BSD-2-Clause. Tylko punkt odniesienia dla konwencji kół okrągłych w OpenSCAD. Nie zawiera kół nieokrągłych i nie będzie włączana do modułu.
- Podręcznik OpenSCAD, https://en.wikibooks.org/wiki/OpenSCAD_User_Manual, CC BY-SA. Semantyka `linear_extrude(twist)`, `offset`, operacji 2D.
- `@lofcz/openscad-wasm` (zależność frontendu, `frontend/package.json`). Przed wydaniem trzeba potwierdzić licencję pakietu i zgodność z licencją OpenSCAD (GPL-2.0). Nie wpływa to na ten plan, ale jest wymagane w DoD produktu komercyjnego.

Linki sprawdzić przy implementacji (fazy 0–1). Numery stron i rozdziałów w cytowanych książkach dopisać po weryfikacji z egzemplarzem.
