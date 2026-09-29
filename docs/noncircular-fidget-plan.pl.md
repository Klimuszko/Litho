# Plan: fidget planetarny z nieokrągłymi (kwadratowymi i trójkątnymi) kołami zębatymi

Status: **plan bazowy oraz zapis decyzji implementacyjnych** (rewizja 2: rozdzielone pasy zębów z kanałem centralnym; implementacja 0.2 wymaga jeszcze prób fizycznych F1–F11)
Baza: commit `74e8487` (gałąź `Main_Frame`), moduł `examples/scad/planetary-fidget` w wersji 2.3.0
Zakres dokumentu: geometria sprzężonych kół nieokrągłych, integracja z klientowym OpenSCAD WebAssembly, testy, etapy i kryteria go/no-go.

## Stan implementacji 0.2 (2026-09-30)

Po krytycznym review z `docs/noncircular-fidget-review.pl.md` odrzucono
pierwszą implementację obwiedni. Aktualna wersja nie udaje dowolnie
parametrycznej geometrii. Udostępnia dwa sprawdzone kształty (kwadrat i trójkąt)
oraz trzy profile dopasowania przy stałej średnicy 90 mm. Oracle Node wylicza
pełne obwiednie koła centralnego, planet i pierścienia, a następnie zapisuje je
do `lib/ncg_profiles.scad`. OpenSCAD WebAssembly w przeglądarce tworzy z tych
profili finalny STL/3MF; obliczenia i rendering nie trafiają na serwer.

Walidacja ruchu używa osobnej siatki 64 pozycji na podziałkę, a nie klatek,
które zbudowały obwiednię. Obejmuje P–P, S–P, P–R oraz S–R i dokładnie profile
po radializacji eksportowane do SCAD. Interfejs pozostaje celowo dyskretny,
dopóki dodatkowe średnice lub kanciastości nie przejdą tego samego procesu.
Próby fizyczne F1–F11 pozostają bramką przed oznaczeniem modelu jako
produkcyjnie potwierdzony.

---

## 0. Streszczenie decyzji

1. **Chodzi o prawdziwe koła nieokrągłe.** Krzywa podziałowa (centroida) koła centralnego i planet jest zaokrąglonym kwadratem albo zaokrąglonym trójkątem. Krzywa pierścienia wewnętrznego jest falista (ma wiele płatów). Zęby leżą *wzdłuż* tej krzywej. To nie są okrągłe koła rozstawione w trójkąt lub kwadrat. Nie są to też okrągłe koła z wielokątnym otworem. Nie są to proste zęby doklejone do boków wielokąta.
2. **Geometria powstaje z kinematyki, a nie z kształtu.** Najpierw liczymy ruch planety toczącej się po kole centralnym. Z twierdzenia Aronholda–Kennedy’ego wynika wtedy centroida pierścienia. Zęby koła centralnego i pierścienia wyznaczamy jako **obwiednię zębów planety** w ruchu względnym. Dzięki temu są z nią sprzężone z definicji.
3. **Dokładne domknięcie pierścienia wymaga korekty prawa ruchu pierścienia.** Wstępne obliczenia (§4.6) pokazują, że dla nieokrągłych kształtów „naturalna” liczba płatów pierścienia jest nieznacznie większa od całkowitej: 12,01–12,07 zamiast 12. Plan to naprawia: narzucamy okresowe prawo obrotu pierścienia ze współczynnikiem korekty `k ≈ 1,000–1,002` i generujemy zęby pierścienia jako obwiednię dla *tego* ruchu. Sprzężenie pozostaje ścisłe, a centroida pierścienia przesuwa się o ułamek milimetra (odpowiednik przesunięcia zarysu).
4. **Liczba planet nie jest swobodna.** Kwadrat: dokładnie 4 planety. Trójkąt: dokładnie 3 planety. Warianty rozszerzone są opcjonalne (§5.4).
5. **Osobny moduł.** Klasyczny moduł `planetary-fidget` zostaje bez zmian. Nowy moduł `planetary-fidget-noncircular` zawiera oba kształty (kwadrat i trójkąt) w jednym pliku `main.scad` z biblioteką `lib/` wewnątrz katalogu modułu (§7).
6. **Całe generowanie modelu w przeglądarce.** Działa na obecnym `@lofcz/openscad-wasm` z backendem Manifold w Web Workerze. Nie wymaga renderowania po stronie serwera. Kosztowne obwiednie zwalidowanych wariantów są wyliczane wcześniej przez oracle TypeScript/Node i dołączane do modułu jako dane SCAD; przeglądarka składa z nich finalny model STL/3MF.
7. **Osiowe zatrzymanie: rozdzielona schodkowa jodełka (rewizja 2).** Każdy element ma **dwa rozdzielone pasy zębów**, górny i dolny. Między nimi jest **centralny kanał bez zębów** z rdzeniem cofniętym pod linię stóp. Zmniejsza to powierzchnię kontaktu i tarcie oraz ułatwia pierwsze uruchomienie po wydruku. Pasy mają przeciwną orientację schodków (lustrzane „V” przerwane kanałem), co zapewnia retencję osiową. Rozwiązanie **zastępuje** ciągłą schodkową jodełkę z rewizji 1 jako jedyną geometrię produkcyjną. Wariant ciągły zostaje tylko jako przypadek porównawczy w oracle i testach (§4.10). Twist (`linear_extrude(twist=…)`) nadal jest zabroniony: obrót nieokrągłego profilu wokół środka nie jest zębem śrubowym.

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
- Na boku pierścienia widać zielone prostokątne „schodki” wzdłuż obwodu. To dekoracja lub zmiana koloru na zewnętrznym boku obręczy. Konstrukcję zazębienia wzdłuż wysokości (pasy zębów i cofnięty pas środkowy) analizuje §2.6.
- Skala: średnica zewnętrzna jest porównywalna z szerokością dłoni, szacunkowo 80–95 mm. Otwór w kole centralnym mieści opuszek palca, około 15–18 mm. Oba wymiary są niepewne i nie służą jako dane projektowe. Pokazują jednak, że **wariant równych kół wymaga większej średnicy niż klasyczny** (§6.3).

### 2.6 Ponowna analiza osiowa (rewizja 2)

Powiększenia `…59b4ef10…png` (krawędź pierścienia i okolice palca) oraz egzemplarzy szaro-zielonego i turkusowego z `…8f28aa96…png` pokazują przekrój wzdłuż wysokości:

- **Zęby są tylko w warstwie zewnętrznej.** Na koło centralne, planety i pierścień patrzymy od góry. Szary pas z pełnymi zębami ma wysokość rzędu ⅓ grubości elementu.
- **Pod szarym pasem jest gładki, zielony pas bez zębów.**
  - Na planetach jest to gładki obrys w kształcie zaokrąglonego kwadratu, położony **na poziomie stóp zębów lub nieco głębiej** (cofnięty do środka planety).
  - Na wewnętrznej stronie pierścienia jest to gładka, falista ścianka cofnięta **na zewnątrz poza linię stóp** zębów pierścienia.
  - Między zielonymi powierzchniami sąsiednich elementów widać wyraźną szczelinę, więc nie ma tam kontaktu.
- Na zdjęciach z góry widać, że zielony kolor wypełnia też dół elementów. Nie widać spodu, więc **nie da się potwierdzić, że dolny pas zębów istnieje**, choć symetria konstrukcji print-in-place i sposób podparcia planet silnie to sugerują.
- Zielone „schodki” na zewnętrznym boku pierścienia są dekoracją lub efektem zmiany koloru. Nie ma to związku z zazębieniem.
- **Nie widać, jak osiągnięto retencję osiową**: skośność, schodki czy fazki w pasach. Nie da się tego odczytać ze zdjęcia z takiej perspektywy.

**Wniosek projektowy:** referencja jest zgodna z wymaganiem użytkownika. Elementy mają pasy zębów przy powierzchniach górnej i dolnej oraz wolny, cofnięty pas środkowy, który zmniejsza pole styku. Geometria retencji jest naszą własną konstrukcją (§4.10), a nie odczytem ze zdjęcia.

### 2.7 Czego zdjęcia nie pokazują

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
| Zazębienie wzdłuż wysokości | jodełka ze skrętem na całej wysokości | dwa pasy schodkowe (góra/dół) + cofnięty kanał środkowy | jak kwadratowy |
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
| luz radialny w kanale `g_ch` (rdzeń–rdzeń, rdzeń–ścianka pierścienia) | ≥ 0,8 | ≥ 1,0 | ≥ 1,2 mm | wynika z cofnięcia `r_rec`; minimum w całym cyklu (§4.10) |
| luz osiowy `g_ax` (warstwa przejściowa między stopniami) | 0,2 | 0,2 | 0,3 mm | pionowa szczelina między poziomymi powierzchniami różnych ciał; wielokrotność wysokości warstwy |
| ścianka minimalna w pasach | 1,4 mm (sun), 1,0 mm (planeta), 1,8 mm (obręcz) | | | mierzona od linii stóp |
| ścianka minimalna w kanale | 1,4 mm (sun), 1,2 mm (planeta), 2,0 mm (obręcz) | | | mierzona od cofniętego rdzenia; wymusza większą obręcz i mniejsze otwory |

- Luz nadajemy wyłącznie po stronie narzędzia tnącego S i R: `offset(r = +b_n/2)`. Planeta zostaje nominalna. Luz obwodowy na każdą flankę wynosi `b_n/2`, a luz obrotowy pary (suma po obu flankach) `b_n`. Luzu nie nakładamy podwójnie (na narzędzie i na planetę). Faza 3 kalibruje na wydruku F1, czy potrzebne jest dodatkowe zmniejszenie planety.
- Offset po obrysie to luz *normalny*. Przy zmiennej krzywiźnie jest to właściwsze niż luz kątowy stosowany w klasyku (`rad_to_deg(b/(2·rp))`), bo dla nieokrągłych nie istnieje jedno `rp`.
- **Pierwsza warstwa (elephant foot):** fazka 0,4 mm × 45° na dolnych krawędziach wszystkich zębów dolnego pasa (S, P i R), żeby uniknąć zgrzania (§4.11).
- Wszystkie luzy są w sekcji „Ukryte” i wynikają z `fit_profile`. Użytkownik nie ustawia ich osobno.

### 4.10 Osiowe zatrzymanie print-in-place: rozdzielone pasy zębów z kanałem centralnym (rewizja 2)

**Powód zmiany.** Użytkownik zgłosił, że po wydruku ruch jest zbyt ciasny. Pełnowysokościowe zazębienie ma kontakt na całej grubości elementu, więc każda nierówność ścian, stopa słonia, szew i zwis dokłada tarcie. Rewizja 2 ogranicza kontakt do dwóch pasów przy górnej i dolnej powierzchni. Pas środkowy staje się wolną, cofniętą strefą bez zębów, zgodnie z referencją (§2.6). Podobne rozwiązanie jest standardem w przemysłowych kołach daszkowych z rowkiem środkowym (wybieg narzędzia).

**Dlaczego nadal nie `twist`:** `linear_extrude(twist=τ)` obraca cały przekrój wokół osi. Dla okręgu jest to równoważne przesunięciu zębów wzdłuż krzywej. Dla nieokrągłego profilu obrót przemieszcza płaty, a nie zęby, więc warstwy przestają być sprzężone. **Zakaz, także w obrębie pojedynczego pasa.**

#### 4.10.1 Przekrój wzdłuż wysokości (od stołu drukarki w górę)

Wszystkie ciała (S, P ×N, R) mają **identyczny podział wysokości**. Granice stref leżą na tych samych `z` i na wielokrotnościach wysokości warstwy 0,2 mm.

| Strefa | Wysokość (przykład H = 8,4 mm, m ≈ 1) | Reguła | Zawartość |
|---|---|---|---|
| Pas dolny `B` | 2,8 mm | `h_b = (H − h_ch − h_ramp)/2`, `h_b ≥ max(2,2 mm; 2,2·m; 11 warstw)` | 3 stopnie zębów, fazka pierwszej warstwy w dolnych 0,4 mm |
| Kanał płaski `C` | 0,8 mm | `h_ch ≥ 0,6 mm` (3 warstwy) | tylko cofnięte rdzenie, zero zębów |
| Rampa `Rp` | 2,0 mm | `h_ramp = max(0; d_ov − o_max)/tan(45°)`, gdzie `d_ov = 2,25·m + c_tip + r_rec` | przejście 45° od rdzenia do pełnego zęba; bez kontaktu |
| Pas górny `T` | 2,8 mm | `h_t = h_b` | 3 stopnie zębów |

- **Strefa bez kontaktu** to `C + Rp`, czyli ≈ 1/3 wysokości. Powierzchnia współpracujących flank spada do ≈ 67% (5,6 / 8,4 mm). Wartość jest orientacyjna. Faza 0 policzy ją dokładnie jako pole flank w pasach.
- `H_min` rośnie względem klasyka. Dla `m ≈ 1`: `2·2,2 + 0,6 + 2,0 ≈ 7,0 mm`, zaokrąglone do 7,2 mm. Dla grubych zębów (`m ≈ 1,25`) wynosi ≈ 8,2 mm. Solver wylicza `H_min` i `assert` zgłasza przekroczenie z komunikatem „Zwiększ grubość modelu albo wybierz drobniejsze zęby”.
- Rampa istnieje tylko pod pasem górnym, bo tylko tam zęby wisiałyby nad kanałem (nawis). Górna krawędź pasa dolnego jest płaska: powierzchnia skierowana w górę nie potrzebuje fazki, a dzięki temu nie traci kontaktu. Asymetria jest celowa i wynika z druku FDM.
- `o_max`, dopuszczalny poziomy nawis pierwszej warstwy rampy, wynosi wstępnie 0,8 mm. Kalibruje go kupon F11.

#### 4.10.2 Cofnięcie rdzenia w kanale

- Koło centralne i planety (zewnętrzne): w strefie `C` profil = krzywa stóp `offset(−r_rec)`.
- Pierścień (wewnętrzny): w strefie `C` ścianka = krzywa stóp pierścienia `offset(+r_rec)`, czyli cofnięta na zewnątrz.
- `r_rec = 0,5 mm` (ukryte; zakres walidacji 0,4–0,8 mm).
- Rampa to stos warstw co 0,2 mm. Każda jest profilem pasu górnego (stopień o fazie 0) z `offset(−d(z))`, gdzie `d(z)` maleje liniowo od `d_ov` do 0. Dla pierścienia offset jest dodatni, czyli materiał odsuwa się na zewnątrz.
- Dzięki cofnięciu luz radialny w kanale wynosi co najmniej `2,25·m + 2·r_rec − c_tip` między rdzeniami sąsiednich ciał. Jest on wielokrotnie większy od `b_n`, więc ewentualny zwis lub nitki w kanale nie łączą elementów.

#### 4.10.3 Orientacja pasów i retencja osiowa („przeciwne fazowanie”)

1. Każdy pas ma `K_b = 3` stopnie o wysokości ≈ `h_b/3`, zaokrąglonej do 0,2 mm. Stopień `i` ma przesunięcie fazy zębów wzdłuż łuku `δ_i`.
2. **Przesunięcia rosną od kanału na zewnątrz w obu pasach:** pas dolny ma od góry do dołu `0, δ, 2δ`, a pas górny od dołu do góry `0, δ, 2δ`. Otrzymujemy lustrzane „V” (jodełkę) przerwane kanałem. Pasy mają więc **przeciwną orientację**, analogicznie do przeciwnych kierunków linii zęba w kole daszkowym.
3. Stopień `i` planety to dłutak przesunięty o `δ_i`. Stopień `i` koła centralnego i pierścienia to obwiednia *tego* stopnia planety. Kinematyka i centroidy są wspólne dla wszystkich stopni.
4. **Dlaczego to trzyma osiowo:**
   - Przesunięcie planety w górę o `Δz > g_ax` sprawia, że w pasie górnym jej stopień `i` wchodzi w strefę stopnia `i+1` koła centralnego lub pierścienia (faza +δ). Wymaga to obrotu planety o +δ.
   - W pasie dolnym jej stopień wchodzi w strefę stopnia o fazie −δ, co wymaga obrotu o −δ.
   - Sprzeczne wymagania blokują ruch, pod warunkiem że `δ` przekracza cały luz obwodowy.
   - Ruch w dół działa symetrycznie.
5. **Warunek blokady:** `δ ≥ j_t + 0,15 mm`, gdzie `j_t = b_n / cos α` to całkowity luz obwodowy pary. Dla profilu standardowego (α = 25°) daje to `j_t ≈ 0,35 mm`, więc `δ ≥ 0,50 mm`. Dla luźnego `δ ≥ 0,64 mm`. `δ` jest ukryte i wyliczane z `fit_profile`.
6. **Warunek druku półki:** pozioma półka na flance ma ≈ `δ·cos α ≤ 0,7 mm` (wstępnie). Przy „Luźnym” jest to ≈ 0,58 mm i mieści się w limicie. Kupon F11 weryfikuje limit.
7. **Warstwy przejściowe (luz osiowy `g_ax`), poprawka względem rewizji 1:**
   - Na każdej granicy stopni nakładanie w rzucie (warunek blokady) oznacza poziome powierzchnie różnych ciał na tym samym `z`. Bez szczeliny zgrzałyby się na wydruku.
   - Dlatego między stopniami `i` i `i+1` wstawiamy warstwę o wysokości `g_ax`, w której **każde ciało ma przecięcie** profili obu stopni (`P_i ∩ P_{i+1}`, `S_i ∩ S_{i+1}`, `R_i ∩ R_{i+1}`).
   - Warstwa przejściowa nie koliduje, bo jest podzbiorem profili sprzężonych. Daje przy tym pionową szczelinę `g_ax` nad każdą nakładką.
   - Luz osiowy planety (swobodny ruch przed zablokowaniem) ≈ `g_ax`.
8. Warstwy łączymy przez `union()` z nakładaniem 0,01 mm wewnątrz jednego ciała (bez szczelin manifoldu). Między różnymi ciałami nakładania nie ma.

#### 4.10.4 Porównanie i decyzja

| Kryterium | Rewizja 1: ciągła schodkowa jodełka | Rewizja 2: rozdzielone pasy + kanał |
|---|---|---|
| Pole współpracujących flank | 100% H | ≈ 60–70% H |
| Pierwsze uruchomienie | trudniejsze, zgrzania na całej wysokości | łatwiejsze: kanał nie może się zgrzać, a nawis rampy opada w wolną przestrzeń |
| Retencja osiowa | V ciągłe | V przerwane; ta sama zasada, 2×3 stopnie |
| Odporność na przechył planety | kontakt na całej wysokości | dobra: dwa pasy daleko od siebie tworzą szeroką bazę |
| Wytrzymałość zębów | wyższa | niższa (krótsze pasy), wymaga minimów z §4.10.5 |
| Minimalna grubość | ≈ 6 mm | ≈ 7,2–8,2 mm |
| Ryzyko druku | półki stopni | półki stopni + rampa 45° nad kanałem |
| Koszt generacji | 3 unikalne profile/ciało | 3 unikalne profile/ciało + tanie offsety rampy i przecięcia przejść |

**Decyzja: rewizja 2 jest wariantem schodkowej jodełki (ta sama zasada sprzężonych stopni o przeciwnej orientacji) i zastępuje wersję ciągłą jako jedyną geometrię produkcyjną.** Wersja ciągła, uzupełniona o warstwy przejściowe z pkt 7, zostaje:

- w oracle jako przypadek porównawczy (ten sam generator, `h_ch = h_ramp = 0`);
- jako wydruk kontrolny A/B w teście F9;
- jako drugi krok fallbacku.

Użytkownik nie dostaje przełącznika między wersjami.

**Kolejność fallbacków (tylko przy NO-GO w fazie 3):**

1. Korekta rampy (`o_max`, kąt 45° → 50°) i `r_rec`.
2. Wersja ciągła z warstwami przejściowymi.
3. Wargi osiowe na pierścieniu, co wymaga decyzji produktowej, bo zmienia charakter „otwartego” fidgetu.

#### 4.10.5 Minimalna wytrzymałość (reguły walidacji)

- Wysokość pasa `h_b ≥ max(2,2 mm; 2,2·m)` oraz co najmniej 11 warstw 0,2 mm. Każdy stopień ≥ 0,6 mm.
- Liczba przyporu w każdym stopniu z osobna ≥ 1,1 w całym cyklu. Każdy stopień przenosi moment samodzielnie, gdy sąsiedni jest w luzie.
- Grubość zęba na głowie ≥ max(0,25·m; 0,4 mm) we wszystkich stopniach i warstwach przejściowych. Przecięcie `P_i ∩ P_{i+1}` jest cieńsze, co ogranicza `δ` od góry: `δ ≤ 0,35·p`.
- Ścianki w kanale według §4.9: sun ≥ 1,4 mm, planeta ≥ 1,2 mm, obręcz ≥ 2,0 mm. Otwór na palec i otwory w planetach liczymy od **cofniętego rdzenia**, a nie od linii stóp.
- Obciążenia fidgetu są małe i nie są liczone metodą MES. Wytrzymałość potwierdzają fizycznie: upadek (F10), ściskanie obręczy dłonią i wypychanie planet (F5).

### 4.11 Fazki krawędzi (chamfer)

- **Pierwsza warstwa:** fazka 0,4 mm × 45° na dolnych krawędziach zębów pasa dolnego wszystkich ciał. Realizacja: warstwa 0–0,2 mm = profil `offset(−0,4)`, warstwa 0,2–0,4 mm = `offset(−0,2)`. Dla pierścienia offset działa w stronę materiału, czyli zęby są węższe, a wręby szersze. Zawsze włączona, ukryta. Pas dolny ma wtedy efektywnie 2,4 mm kontaktu, co uwzględnia reguła `h_b`.
- **Rampa pod pasem górnym** (§4.10.1) to funkcjonalne „fazowanie” nawisu, a nie ozdoba.
- **Górna fazka estetyczna** 0,4 mm tylko na zewnętrznym obrysie obręczy i na otworze na palec (komfort). Nie dotyczy zębów, żeby nie skracać pasa górnego.
- Fazki robimy przez `offset()` warstw. `minkowski()` jest zbyt kosztowny w WASM.

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
| Ścianka obręczy | `min_θ (r_outer − r_root,R − r_rec) ≥ 2,0 mm` (kanał) i `≥ 1,8 mm` (pasy) | wymuszone (obrys równoległy, szersza obręcz) |
| Podział wysokości | `H ≥ H_min(m)`; `h_b`, `h_ch`, `h_ramp` według §4.10.1, wszystkie granice na wielokrotnościach 0,2 mm | `assert` „Zwiększ grubość modelu albo wybierz drobniejsze zęby” |
| Retencja osiowa | `δ ≥ j_t + 0,15 mm`; `δ·cos α ≤ 0,7 mm`; `δ ≤ 0,35·p` | `assert` (gdy nie da się spełnić wszystkich trzech naraz przy danym `fit_profile` i `m`) |
| Szczeliny poziome | każda pozioma nakładka dwóch różnych ciał ma pionową szczelinę ≥ `g_ax` | oracle: test; SCAD: konstrukcyjnie przez warstwy przejściowe |
| Kanał bez kontaktu | `min_cykl` odległość ciał w strefie `C + Rp` ≥ `g_ch` | oracle: test |
| Nawis | pierwsza warstwa rampy ≤ `o_max`; dalej ≤ 45°; półki stopni ≤ 0,7 mm | oracle: test; SCAD: konstrukcyjnie |

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
- Brak referencji fotograficznej (§2.7), więc przed publikacją potrzebny jest obowiązkowy wydruk testowy.

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
| Główne | `gear_thickness` | `[7:0.2:14]` mm | 8,4 | dolna granica efektywna = `H_min(m)` z §4.10.1 (`assert` z podpowiedzią); podział na pasy i kanał liczony automatycznie |
| Dopasowanie | `fit_profile` | `[0:Ciasny,1:Standardowy,2:Luźny]` | 1 | §4.9 |
| Otwory | `finger_hole_diameter` | `[10:1:24]` mm | 16 | auto-ograniczenie + `WARNING:` |
| Otwory | `planet_holes` | bool | true | otwór = zaokrąglony kwadrat/trójkąt |
| Otwory | `planet_hole_percent` | `[30:1:65]` % | 50 | |
| Obudowa | `rim_style` | `[0:Równoległa do fali,1:Gładka okrągła]` | 0 | 0 jak na zdjęciach; 1 = okrąg opisany na obręczy |
| Zaawansowane | `side_flatness` | `[0:1:100]` % | 0 | `@advanced`; `e₂`, dostępne po fazie 0 tylko jeśli poprawia krzywiznę |
| Zaawansowane | `pressure_angle` | `[20:25]` | 25 | `@advanced`; kąt dłutaka |
| Ukryte | `envelope_samples`, `curve_samples`, `k_max` | — | — | sekcja „Ukryte” |
| Ukryte | `band_steps` (3), `band_min_height` (2,2 mm / 2,2·m), `channel_flat_height` (0,6–0,8 mm), `recess_depth` `r_rec` (0,5 mm), `ramp_overhang_max` `o_max` (0,8 mm), `ramp_angle` (45°), `axial_gap` `g_ax` (z `fit_profile`), `step_shift` `δ` (z `fit_profile`), `first_layer_chamfer` (0,4 mm, zawsze), `debug_section_z` (tylko testy) | — | — | wartości bezpieczne, kalibrowane wydrukami F1, F5, F9, F11; **nie są widoczne w UI** |

**Rewizja 2 nie dodaje żadnego parametru widocznego dla użytkownika.** Geometria pasów i kanału oraz wszystkie luzy osiowe i radialne są funkcją `gear_thickness`, `tooth_style` i `fit_profile`. Dotychczasowe `axial_layers`, `layer_shift_percent` i `first_layer_chamfer` przeniesiono do sekcji „Ukryte”. Użytkownik nie ma podstaw, by je zmieniać, a złe wartości wprost powodują wypadanie planet albo zgrzanie. Jedynym „pokrętłem” ciasności ruchu pozostaje `fit_profile`. Jeśli F9 pokaże, że potrzebny jest wybór szerokości kanału, dodamy co najwyżej jedną listę `[0:Standardowy,1:Szeroki]`, ale dopiero po danych z wydruków.

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

Dla równych kół: `D ≈ 2·(3R(1 + e₁) + 1,25m + c + rim)` i `hole ≤ 2·(R(1 − e₁) − 1,25m − c − r_rec − 1,4)`. W rewizji 2 otwór liczymy od cofniętego rdzenia w kanale, ze ścianką koła centralnego 1,4 mm.

Przykład dla kwadratu, `e₁ = 0,05`, `m ≈ 1`, `rim = 3,8`:

- `D = 90 mm` → `R ≈ 12,6 mm` → otwór ≤ ≈ 17 mm;
- `D = 70 mm` → otwór ≤ ≈ 11 mm.

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
  lib/ncg_teeth.scad       # dłutak, obwiednie, stopnie pasów, warstwy przejściowe, luzy
  lib/ncg_axial.scad       # podział wysokości: pasy, kanał, rampa, cofnięcie rdzenia, fazki
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
- Obwiednie: jeden płat na koło × 3 unikalne stopnie (`0, δ, 2δ`), wspólne dla pasa dolnego i górnego. Warstwy przejściowe (`intersection()` dwóch profili 2D), rdzeń kanału i rampa (≈ 10 warstw `offset()` jednego profilu) są tanie w porównaniu z obwiedniami. Rewizja 2 nie zwiększa istotnie kosztu. Szacunkowo `(24–48 poz./podziałkę) × t` pozycji narzędzia na płat. Operacje 2D w Clipperze są rzędu setek wielokątów na płat.
- **Cel:** pełny print-in-place ≤ 30 s na referencyjnym laptopie (Chrome, 4 rdzenie; WASM jest jednowątkowy), podgląd `output_mode = 1` ≤ 15 s. **Limit twardy:** 90 s albo przekroczenie pamięci WASM. Wtedy przechodzimy na opcję C i/lub metodę analityczną z §4.7(d).
- Pomiar: `durationSeconds` z workera, logowany w teście E2E (§9.1).

### 8.4 Kontrakt wyjścia

- `echo("INFO:kształt=…")`, `INFO:liczba_planet`, `INFO:zęby_koła_centralnego/planety/pierścienia`, `INFO:moduł_zęba`, `INFO:korekta_pierścienia_k`, `INFO:min_odstęp_planet`, `INFO:rzeczywista_średnica`, a od rewizji 2 także `INFO:pas_zębów`, `INFO:kanał` (płaski + rampa), `INFO:cofnięcie_rdzenia`, `INFO:przesunięcie_stopnia_δ`, `INFO:luz_osiowy`, `INFO:udział_kontaktu` (% wysokości). Te same prefiksy parsuje już `parseLocalMetadata`.
- `assert(...)` z komunikatami po polsku. Worker mapuje je na „Wybrane parametry tworzą nieprawidłową geometrię”. Rozważyć (poza zakresem) przekazywanie treści asercji do UI.
- Ukryty `debug_section_z` (tylko testy): gdy ustawiony, model zwraca `projection(cut=true)` na wysokości `z`, co pozwala porównać przekroje stref z oracle (eksport SVG/DXF 2D w WASM).
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
6. **Blokada osiowa pasów (rewizja 2):** dla każdej pary S–P i P–R, w każdej chwili cyklu i w **obu pasach osobno**, pole nakładania rzutów stopnia `i` jednego ciała i stopnia `i ± 1` drugiego jest > 0 po uwzględnieniu całego luzu obwodowego `j_t`. Dodatkowo:
   - symulacja przesunięcia planety o `Δz = g_ax + 0,05 mm` w górę i w dół przy dowolnym obrocie w zakresie luzu kończy się kolizją, czyli planeta jest zablokowana;
   - wyznaczony luz osiowy ≤ `g_ax + 0,1 mm`.
7. **Planety:** minimalny odstęp w cyklu ≥ `planet_spacing_clearance`.
7a. **Kanał bez kontaktu:** w strefie `C + Rp` minimalna odległość między dowolnymi dwoma ciałami w całym cyklu ≥ `g_ch` (§4.9).
7b. **Szczeliny poziome:** w modelu 3D (stos przekrojów stref) każda para poziomych powierzchni różnych ciał, które nakładają się w rzucie, ma pionową szczelinę ≥ `g_ax`. Test wykrywa brak warstw przejściowych.
7c. **Nawisy:** pierwsza warstwa rampy ≤ `o_max`, dalej każda warstwa 0,2 mm wystaje ≤ 0,2 mm (45°); półki stopni ≤ 0,7 mm.
7d. **Wytrzymałość geometryczna (§4.10.5):** `h_b`, grubość głowy w stopniach i przejściach, liczba przyporu ≥ 1,1 w każdym stopniu osobno, ścianki w kanale.
7e. **Porównanie z rewizją 1:** ten sam generator z `h_ch = h_ramp = 0` przechodzi testy 4–7b. Raport podaje udział pola flank rewizji 2 względem rewizji 1 (oczekiwane 60–70%).

**SCAD w WASM (Node, ten sam pakiet `@lofcz/openscad-wasm`, rozszerzenie `scadWasm.test.ts`):**

8. Render każdego wariantu × `fit_profile` × {D min, D domyślne, D max}: kod wyjścia 0, STL jest manifoldem (1 bryła na część), a liczba brył w print-in-place wynosi `2 + N`.
9. Zgodność SCAD ↔ oracle: wartości `INFO:` (zęby, m, k, min odstęp, pas, kanał, δ, luz osiowy, udział kontaktu) równe z tolerancją 1e-3. Przekroje `debug_section_z` w każdej strefie (każdy stopień obu pasów, warstwa przejściowa, kanał płaski, 3 poziomy rampy, warstwa fazki) eksportowane jako SVG i porównane z wielokątami oracle (Hausdorff < 0,02 mm).
9a. Niezmienniki 3D w WASM: w eksporcie print-in-place żadne dwie bryły nie mają wspólnej objętości (`intersection()` każdej pary daje pusty wynik), a objętość każdej bryły mieści się w ±1% oracle.
10. Wydajność: czas renderu ≤ budżet z §8.3 (test oznaczony jako „perf”, raportowany, a nie flaky-fail).
11. Parametry niedozwolone dają oczekiwaną asercję, np. `outer_diameter = 70` z `finger_hole_diameter = 24` daje `WARNING` i auto-zmniejszenie; `squareness = 100` z drobnymi zębami daje `assert` albo auto-limit; `gear_thickness < H_min(m)` (np. 7 mm z grubymi zębami) daje `assert` z podpowiedzią.

**Regresja klasyka:**

12. `backend/tests/test_scad_parser.py` i `test_scad_repository.py`: klasyczny moduł ma te same parametry, domyślne wartości i wersję co w `74e8487`. Nowy moduł parsuje się bez ostrzeżeń.
13. Golden render klasyka (domyślne parametry): hash lub objętość STL i wartości `INFO:` są niezmienione względem `74e8487`.

### 9.2 Fizyczne (obowiązkowe przed publikacją; nie da się ich zastąpić symulacją)

Macierz minimalna: PLA na drukarce referencyjnej, warstwa 0,2 mm, 3 obrysy, bez podpór.

| # | Próbka | Cel | Kryterium |
|---|---|---|---|
| F1 | Kupon luzów: pasek 3 par S–P (każdy `fit_profile`) z pełnym przekrojem rewizji 2 (pas–kanał–rampa–pas) | kalibracja `b_n`, `g_ax`, `r_rec` | co najmniej „Standardowy” rozłącza się palcami bez narzędzi; kanał czysty (brak mostków) |
| F2 | Kwadrat, D = 90, domyślne | działanie print-in-place | uwolnienie ≤ 30 s ręcznie; ≥ 100 pełnych obrotów bez zacięcia |
| F3 | Kwadrat, `squareness` max | granica kanciastości | brak zacięć na narożach; subiektywne „pulsowanie” akceptowalne |
| F4 | Trójkąt, D = 90 | działanie wariantu bez referencji | jak F2 |
| F5 | Kwadrat domyślny; warianty `δ` min/max dla „Standardowego” i „Luźnego” | retencja osiowa i ryzyko wypadnięcia | planety nie wypadają przy wstrząsaniu (30 s) ani przy nacisku palcem ≈ 5 N (waga kuchenna) na planetę z każdej strony; ściskanie obręczy dłonią nie wypycha planet; luz osiowy ≤ 0,5 mm (szczelinomierz) |
| F6 | PETG, profil „Luźny” | drugi materiał | jak F2 |
| F7 | Długotrwałość: F2 po 1000 obrotach | zużycie | brak widocznego starcia głów; luz wzrasta ≤ 0,1 mm (pomiar szczelinomierzem) |
| F8 | Druga drukarka (inna kinematyka) | przenośność | co najmniej „Luźny” działa |
| F9 | **A/B pierwszego uruchomienia:** rewizja 2 vs rewizja 1 (ciągła z warstwami przejściowymi), te same parametry, po 3 sztuki | czy kanał realnie ułatwia start | rewizja 2 uwalnia się szybciej lub łatwiej w ≥ 2 z 3 par (czas do pierwszego pełnego obrotu, ocena 1–5 przez 2 osoby); po 100 obrotach opór nie wyższy niż w rewizji 1 |
| F10 | Upadek: domyślny kwadrat z 1 m na twardą podłogę, 5 razy | minimalna wytrzymałość cieńszych pasów i ścianek w kanale | brak pęknięć pasów i zębów; planety pozostają na miejscu lub dają się wcisnąć ręką i dalej działają |
| F11 | Kupon nawisu rampy: `o_max` 0,4 / 0,8 / 1,2 mm × kąt 45° / 50°; półki `δ·cos α` 0,4 / 0,6 / 0,8 mm | kalibracja ukrytych stałych druku | wybrane wartości drukują się bez nitek łączących kanał z sąsiednim ciałem |

Każdy wynik trafia do `docs/` (protokół: parametry, zdjęcie, uwagi).

---

## 10. Etapy implementacji z kryteriami go/no-go

| Faza | Zakres | Wyjście | **GO** gdy | **NO-GO / reakcja** |
|---|---|---|---|---|
| **0. Oracle i dowód wykonalności** (TS, bez SCAD) | Rodziny krzywych, kinematyka, Kennedy, korekta `k`, dłutak, obwiednie, symulacja kolizji; model osiowy rewizji 2 (pasy, stopnie, przejścia, kanał, rampa); poszukiwanie dokładnych rozwiązań bez `k` | `tools/noncircular-oracle`, testy 1–7e, raport liczbowy w `docs/` (w tym `H_min(m)`, `δ` dla każdego `fit_profile`) | Kwadrat i trójkąt: dla co najmniej 3 wartości `e₁` z widocznym efektem (wizualnie „kwadratowe”) wszystkie testy 1–7e przechodzą, `|k − 1| ≤ 0,5%`, istnieje `δ` spełniające jednocześnie blokadę, limit półki i grubość głowy dla wszystkich `fit_profile` | Jeśli regularne obwiednie wychodzą tylko dla `e₁` tak małych, że kształt jest ledwie widoczny: stop i decyzja produktowa (np. tylko Kwadrat+ z większym sun, albo rezygnacja). **Nie** przechodzimy na skróty z §11. |
| **1. SCAD: numeryka** | `lib/ncg_curves`, `ncg_kinematics`, `ncg_validate`; raport `INFO:` | moduł renderuje centroidy (2D) | wartości `INFO:` zgodne z oracle (test 9) | rozbieżność > 1e-3: poprawić przed fazą 2 |
| **2. SCAD: zęby 2D + wydajność** | dłutak, obwiednie jednego płatu, powielanie, luz | `output_mode` 2/3/4 i przekrój 2D | Hausdorff do oracle < 0,02 mm; czas ≤ budżet §8.3 | za wolno: opcja C (tablica) i/lub §4.7(d) przed dalszymi krokami |
| **3. 3D: rozdzielone pasy, kanał, fazki, print-in-place** | podział wysokości (§4.10.1), stopnie, warstwy przejściowe, cofnięcie rdzenia, rampa, fazka pierwszej warstwy, otwory, obręcz | pełny model 3D, testy 7a–7e, 8, 9, 9a, 10, 11 | manifold, `2 + N` brył bez wspólnej objętości, testy zielone; **wydruki F1, F2, F5, F9, F10, F11 pozytywne**, w tym F9: rewizja 2 nie gorsza od rewizji 1 i lepsza przy pierwszym uruchomieniu | F11 negatywne: korekta `o_max`, kąta rampy, `r_rec`; F5 negatywne: zwiększ `δ`/liczbę stopni w granicach §4.10.5, potem fallback z §4.10.4; F9 bez poprawy: analiza przyczyn tarcia (zgrzania vs luz) przed dalszą pracą, rewizja 1 jako fallback |
| **4. Wariant trójkątny i kalibracja** | granice `e₁`, wydruki F3, F4, F6 | tabela limitów | F3, F4, F6 pozytywne | trójkąt nie działa: publikujemy tylko kwadrat, trójkąt pozostaje ukryty (`shape` z jedną opcją) |
| **5. Integracja produktu** | `module.json`, rejestracja przykładu, test `test_scad_repository.py`, testy regresji 12–13, opisy UI | PR do `main` | wszystkie testy + F7, F8 | brak |
| **6. (opcjonalnie) Rozszerzenia** | Kwadrat+, Trójkąt+, style obudowy | osobne PR | te same bramki | — |

---

## 11. Ryzyka i zakazane skróty

### 11.1 Ryzyka

| Ryzyko | Prawdopodobieństwo | Skutek | Mitygacja |
|---|---|---|---|
| Hipoteza z §4.6 jest prawdziwa, a korekta `k` daje nieregularne obwiednie przy dużej kanciastości | średnie | niższy limit `e₁`, mniej „kwadratowy” wygląd | faza 0 mierzy limit; `e₂` (spłaszczenie boków) jako dźwignia wizualna |
| Wydajność obwiedni w WASM | średnie | render > 90 s | jeden płat + powielanie, 3 unikalne stopnie wspólne dla obu pasów, opcja C, metoda analityczna |
| **Wypadanie planet**: `δ` za małe względem realnego luzu, zaokrąglone krawędzie stopni, zużycie albo owalizacja obręczy przy ściskaniu | średnie | planeta wysuwa się osiowo | warunek `δ ≥ j_t + 0,15`, 3 stopnie w każdym pasie, obręcz ≥ 2,0 mm w kanale, test 6, F5, F7, F10; fallback z §4.10.4 |
| Rampa nad kanałem drukuje się z nitkami, które łączą ciała | średnie | zgrzanie w kanale, trudny start | cofnięcie `r_rec` daje duży luz radialny, `o_max` i kąt z F11, test 7c |
| Poziome nakładki stopni zgrzewają się mimo `g_ax` | niskie–średnie | ciasny start mimo kanału | warstwy przejściowe (test 7b), `g_ax` 0,3 mm dla „Luźnego”, F1/F9 |
| Krótsze pasy łamią się lub ścinają zęby | niskie–średnie | uszkodzenie po upadku | minima §4.10.5, F10; drobne zęby wymagają wyższego `H_min` |
| Mniejsze pole kontaktu zwiększa zużycie lub luz po czasie | średnie | rosnący luz, stuki | F7 (1000 obrotów) na rewizji 2 |
| Kanał nie daje zauważalnej poprawy startu (tarcie pochodzi z innych źródeł) | średnie | brak korzyści przy wyższym `H_min` | test A/B F9 jako bramka fazy 3 |
| Wyższe `H_min` wyklucza cienkie modele | wysokie (z założenia) | minimum ≈ 7,2–8,2 mm | komunikat w `assert`; świadoma decyzja produktowa |
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
12. **Kanał wycięty tylko w jednym ciele** (np. rowek w pierścieniu przy pełnowysokościowych planetach) albo kanał bez cofnięcia rdzenia poniżej linii stóp. To nie zmniejsza kontaktu w sposób kontrolowany.
13. **Pasy o tej samej orientacji** (brak „V”) albo pasy bez stopni. Proste zęby w obu pasach nie dają retencji osiowej.
14. **Stopnie bez warstw przejściowych**, czyli poziome powierzchnie różnych ciał bez pionowej szczeliny `g_ax`.
15. **`twist` w obrębie pasa** jako „ułatwienie” zamiast stopni.
16. **Wystawienie w UI surowych stałych osiowych** (`δ`, `g_ax`, `r_rec`, `o_max`, liczba stopni) bez danych z wydruków uzasadniających taką potrzebę.

---

## 12. Czego nie da się potwierdzić bez wydruku fizycznego

- Rzeczywisty luz konieczny do rozdzielenia elementów print-in-place przy zmiennej krzywiźnie. Wartości z klasyka są tylko punktem startu.
- Czy rozdzielone pasy ze stopniami (półki δ) drukują się czysto i czy trzymają osiowo przy realnym tarciu i zużyciu.
- Czy kanał centralny **realnie** ułatwia pierwsze uruchomienie. Hipoteza: mniejsze pole zgrzań i brak kontaktu w pasie zwisów. Potwierdzi to dopiero test A/B F9.
- Jakość rampy 45° nad kanałem i to, czy nitki z nawisu nie łączą ciał.
- Czy `g_ax` = 1 warstwa wystarcza na danej drukarce (zależy od chłodzenia i kalibracji Z).
- Wytrzymałość krótszych pasów na upadki i ściskanie (F10).
- Czy referencja ze zdjęć ma dolny pas zębów. Spód nie jest widoczny (§2.6), co nie wpływa na naszą konstrukcję.
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
3. Oracle TS istnieje w repozytorium, a testy 1–7e przechodzą w CI dla pełnej siatki parametrów, w tym model osiowy rewizji 2.
4. Testy WASM 8–11 (z 9a) przechodzą. Wyniki SCAD są zgodne z oracle również w przekrojach wszystkich stref wysokości (§9.1, test 9).
4a. Każde ciało ma dwa rozdzielone pasy zębów (górny i dolny) po 3 stopnie o przeciwnej orientacji. Między nimi jest kanał bez zębów z rdzeniem cofniętym o `r_rec` pod linię stóp, rampa 45° pod pasem górnym, warstwy przejściowe `g_ax` na granicach stopni i fazka pierwszej warstwy. Wszystkie te stałe są ukryte i wynikają z `fit_profile`, `tooth_style` i `gear_thickness`. Rewizja 2 nie dodaje parametrów UI.
5. Pełny render print-in-place mieści się w budżecie z §8.3 na referencyjnym sprzęcie. Czas jest udokumentowany.
6. Całe generowanie odbywa się w przeglądarce przez istniejący worker WASM. Diff backendu ogranicza się do rejestracji przykładu i testów.
7. Klasyczny `planetary-fidget` jest bitowo niezmieniony (`main.scad`, `module.json`), a testy regresji 12–13 przechodzą.
8. Wydruki F1–F11 są wykonane, udokumentowane protokołem w `docs/` i pozytywne, w szczególności F5 (planety nie wypadają), F9 (A/B: rewizja 2 łatwiej uruchamia się po wydruku niż rewizja 1) i F10 (upadek). Ewentualnie wariant trójkątny jest świadomie ukryty zgodnie z bramką fazy 4.
9. Limity (`e₁_max` na kształt, minimalna średnica, maksymalny otwór na palec, `H_min(m)`, `δ` i `g_ax` na profil luzu) wynikają z pomiarów i są wymuszone w SCAD (asercje i ostrzeżenia).
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
