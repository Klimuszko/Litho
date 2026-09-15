# REVIEW.md — Rygorystyczny code review V1 (Generator Litofanii)

Reviewer: Claude (jako reviewer, zgodnie z ownership: Codex nanosi poprawki).
Zakres: `backend/app`, `backend/tests`, `frontend`, `docker-compose.yml` +
Dockerfile'e, `README.md`, w odniesieniu do kontraktów wiążących w
`ARCHITECTURE.md`. Żaden plik aplikacji ani `ARCHITECTURE.md` nie został
zmieniony w ramach tego review.

## Werdykt

**Nie gotowe do merge bez poprawek.** Rdzeń pipeline'u (luminancja→grubość,
triangulacja, watertight/manifold, binary STL, brak zapisu plików na dysk)
jest **poprawny i zweryfikowany** — patrz sekcja "Sprawdzenie testów" i
"Potwierdzone bez zastrzeżeń" poniżej. Nie ma blokerów P0 (nic nie jest
totalnie zepsute na ścieżce happy-path). Jest jednak **6 usterek P1**, które
naruszają wprost wymagania z `ARCHITECTURE.md` §5/§6/§7.3/§8.4/§3/§11 i mogą
prowadzić do cichego zepsucia wyniku (ramka zjadająca całe zdjęcie, brak
`mirror`, zniekształcenie proporcji zdjęcia, luka w ochronie przed
image-bombą, zerowe testy frontendu/walidacji klienckiej) — te należy naprawić
przed wydaniem V1. Dodatkowo 6 usterek P2 i 5 uwag P3, głównie o pokryciu
testami i drobnych rozjazdach z dokumentacją.

## Sprawdzenie testów

- Backend: uruchomiono `pytest tests -v` (8 testów: `test_api.py`×2,
  `test_heightmap.py`×3, `test_mesh.py`×3) — **wszystkie 8 przeszły**.
  Środowisko: repo pina `numpy==2.3.3`/Python 3.11+ (patrz
  `backend/requirements.txt`, `backend/Dockerfile`), ale to środowisko review
  miało tylko Python 3.10 i brak Dockera — testy uruchomiono w tymczasowym
  venv z najbliższymi kompatybilnymi wersjami (numpy 2.2.6, pozostałe pakiety
  identyczne z pinami). Venv usunięto po teście, repo nie zostało
  zmodyfikowane. **Rekomendacja:** Codex/CI powinien odpalić `pytest` w
  docelowym obrazie Docker (Python 3.12-slim, dokładne piny) dla pewności —
  logika nie jest wersyjnie wrażliwa, ale to niepotwierdzone 1:1.
- Frontend: **brak jakichkolwiek testów** — `frontend/package.json` nie ma
  ani zależności Vitest/RTL, ani skryptu `test`. Nie da się "sprawdzić
  testów", bo ich nie ma — patrz P1 #6.
- Pokrycie testami backendu jest węższe niż wymaga §11.2/§11.5: brak testów
  dla większości `error_code` z §5, brak testu ramki/`add_frame`, brak testu
  orientacji/rogu obrazu (§12 "Błędna orientacja osi Y" — mitygacja wymaga
  testu, którego nie ma) — patrz P2 #8.

## Blokery (P0–P1)

### [P1] Ramka bez limitu może skonsumować całe zdjęcie
**Plik:** `backend/app/mesh.py:47-58` (`apply_border`), brak walidacji
krzyżowej w `backend/app/models.py` (`LithophaneParams`, `physical_relations`,
linie 34-44).
**Skutek:** `border_width_mm` (zakres 0–30, `models.py:29`) i `width_mm`/
`height_mm` (zakres 20–400, `models.py:20-21`) są walidowane niezależnie.
Legalna kombinacja, np. `width_mm=20, border_width_mm=15` (albo
`border_width_mm=30` przy dowolnym `width_mm≤60`), daje
`x_cells = round(border_width_mm/width_mm*(cols-1))` pokrywające ≥połowę
siatki z **obu** stron jednocześnie — `framed[:, :x_cells]` i
`framed[:, -x_cells:]` się nakładają i cała mapa wysokości zostaje
nadpisana stałą `border_height_mm`. Wynik: request kończy się sukcesem
(200, poprawny watertight STL), ale **całe zdjęcie znika**, zastąpione
płaskim prostopadłościanem. Brak jakiegokolwiek błędu walidacyjnego mimo że
to całkowicie błędny wynik.
**Poprawka:** dodać w `LithophaneParams.physical_relations` warunek typu
`if self.border_width_mm > 0 and 2*self.border_width_mm >= min(self.width_mm, self.height_mm): raise ValueError(...)`
(→ `PARAM_OUT_OF_RANGE`), oraz analogiczny guard w `apply_border` jako
druga linia obrony.

### [P1] Ramka nie jest "obramowaniem dookoła", tylko wycina fragment zdjęcia
**Plik:** `backend/app/mesh.py:47-58`; kontrakt: `ARCHITECTURE.md` §5 (wiersz
121: "szerokość ramki **wokół** płyty"), §7.3 (`add_frame`, linie 250-258),
§8.4 (linie 404-426: ramka jako osobna bryła **otaczająca płytę na
zewnątrz**, zwiększająca ślad modelu).
**Skutek:** `apply_border` działa na heightmapie *przed* budową mesha i
nadpisuje **istniejące** komórki brzegowe siatki na stałą wysokość —
fizyczny rozmiar modelu (`width_mm × height_mm`) się nie zmienia,
niezależnie od `border_width_mm`. Zamiast dokładać ramkę na zewnątrz, funkcja
**zjada** zewnętrzny pas fotografii. `README.md:45` dokumentuje to jako
świadome uproszczenie V1 ("ramka jest realizowana jako płaski, grubszy pas
brzegowy wspólnego mesha"), ale UI (`frontend/src/App.tsx:89`, suwak
"Szerokość ramki") nie ostrzega użytkownika, że zwiększanie ramki obcina
zdjęcie — w połączeniu z brakiem limitu (P1 wyżej) to może całkowicie
zniszczyć wynik bez ostrzeżenia.
**Poprawka:** Zaimplementować ramkę zgodnie z §7.3/§8.4 jako dodatkową
geometrię na zewnątrz płyty (rozszerzającą bounding box o
`border_width_mm` z każdej strony), albo — jeśli uproszczenie ma zostać
utrzymane jako świadoma decyzja V1 — dodać w UI wyraźne ostrzeżenie
("ramka nadpisuje brzeg zdjęcia") i twardy limit z P1 wyżej.

### [P1] Parametr `mirror` z kontraktu API jest całkowicie niezaimplementowany
**Plik:** brak w `backend/app/models.py` (`LithophaneParams`), brak w
`backend/app/image_processing.py`, brak w `frontend/src/App.tsx`.
Kontrakt: `ARCHITECTURE.md` §5, wiersz 124: `mirror | bool | nie | odbicie
lustrzane przed generacją`.
**Skutek:** to jawnie wymagany w kontrakcie API parametr (opcjonalny, ale
musi istnieć) — obecnie nie ma go nigdzie: nie da się wygenerować lustrzanej
litofanii (częsta potrzeba przy negatywach/formach do odlewu). Sprawdzone
`grep -i mirror` w całym repo — zero wystąpień poza samym
`ARCHITECTURE.md`.
**Poprawka:** dodać `mirror: bool = False` do `LithophaneParams`, zastosować
`ImageOps.mirror(image)` w `prepare_image` (analogicznie do istniejącej
rotacji orientacji), dodać checkbox w UI.

### [P1] `height_mm` nie jest wyprowadzane z proporcji obrazu — zdjęcia są cicho rozciągane
**Plik:** `backend/app/models.py:21` (`height_mm: float = Field(75, ...)`),
`frontend/src/App.tsx:10` (`height_mm: 75` na stałe w stanie startowym).
Kontrakt: `ARCHITECTURE.md` §5, wiersz 118: `height_mm | ... | nie | ...
jeśli brak — liczona z proporcji obrazu`.
**Skutek:** `height_mm` jest w praktyce zawsze wymagane (ma sztywny default),
nigdy nie jest wyliczane z proporcji przesłanego zdjęcia. Ponieważ
`resample_luminance` (`backend/app/image_processing.py:47-49`) robi
`image.resize((cols, rows))` — twarde rozciągnięcie do dokładnie zadanej
siatki — każde zdjęcie, którego proporcje nie zgadzają się ręcznie dobranym
`width_mm`/`height_mm`, wychodzi widocznie zniekształcone (spłaszczone/
rozciągnięte). To nie edge case — to domyślne zachowanie dla każdego
zdjęcia o innych proporcjach niż 100:75, a UI nie ma żadnej funkcji
"dopasuj do zdjęcia" ani blokady proporcji kadru.
**Poprawka:** uczynić `height_mm` faktycznie opcjonalnym; gdy nieobecne,
wyliczyć je backendowo z proporcji zdekodowanego (po kadrowaniu) obrazu
przed resamplingiem. Dodatkowo w UI dodać akcję "dopasuj wysokość do
zdjęcia" wywoływaną przy wyborze pliku/zmianie kadru.

### [P1] Sprawdzenie wymiarów obrazu następuje po pełnej dekompresji — luka w ochronie przed image-bombą
**Plik:** `backend/app/image_processing.py:16-29` (`decode_image`) —
`image.load()` w linii 23, sprawdzenie `max(image.size) > MAX_IMAGE_DIMENSION`
dopiero w linii 27.
**Skutek:** cel limitu `MAX_IMAGE_DIMENSION` w `ARCHITECTURE.md` §9
(wiersz 443) to jawnie "ochrona przed dekompresją 'image bomb'". Pillow
rzuca `DecompressionBombError` dopiero powyżej ok. 179 mln pikseli
(2× `Image.MAX_IMAGE_PIXELS`, domyślnie ~89,5 mln); obraz np. 13000×13000 px
(169 mln pikseli, mieszczący się bez trudu w limicie 20 MB dla dobrze
kompresowalnego PNG) zostanie w pełni zdekodowany do pamięci (setki MB jako
RGB) **zanim** kod odrzuci go za przekroczenie 8000 px na bok. W tym V1 bez
kolejki (własne ryzyko z §12: "duża siatka w połączeniu z wieloma
równoległymi requestami przeciąża kontener") to łatwy do wywołania,
nieautoryzowany wektor wyczerpania pamięci pojedynczym małym plikiem.
**Poprawka:** sprawdzać `image.size` (dostępne od razu po `Image.open()`,
bez dekodowania pikseli) i odrzucać zbyt duże wymiary **przed** wywołaniem
`image.load()`.

### [P1] Frontend nie ma żadnych testów ani walidacji klienckiej — kontrakt §3/§10/§11.4 niespełniony
**Plik:** `frontend/package.json` (brak zależności Vitest/React Testing
Library, brak skryptu `test`), `frontend/src/App.tsx` (`generate()`,
linie 54-65 — request leci zawsze, bez sprawdzenia zakresów z §6 przed
wysyłką).
**Skutek:** `ARCHITECTURE.md` §3 wprost wymienia "Vitest + React Testing
Library" jako stos testowy frontendu, §11.4 opisuje konkretne testy
(walidacja blokująca submit, mapowanie błędów, happy path), §11.5 pkt 4
zakłada CI uruchamiające `vitest` na każdym PR — nic z tego nie istnieje.
W praktyce: nic nie stoi na przeszkodzie, by użytkownik ustawił
`min_thickness_mm=4` i `max_thickness_mm=0.5` (suwaki są sterowane
niezależnie, `App.tsx:83-84`) — dowie się o błędzie dopiero po pełnym
round-tripie do backendu, wbrew jawnemu wymaganiu §10 "natychmiastowy
feedback".
**Poprawka:** dodać pakiet testowy Vitest+RTL i pokryć przypadki z §11.4;
dodać client-side replikację reguł z §6 (blokada submitu + inline komunikat)
zamiast polegać wyłącznie na błędzie z backendu.

## Sugestie (P2)

### [P2] Brak globalnego handlera wyjątków — kontrakt `INTERNAL_ERROR` nie jest gwarantowany
**Plik:** `backend/app/main.py` (brak `@app.exception_handler(Exception)`).
**Skutek:** każdy wyjątek niezłapany jawnie (np. przyszły `ValueError` z
`build_plate`, `backend/app/mesh.py:16`, albo nieoczekiwany błąd PIL) trafia
do domyślnej obsługi FastAPI/Starlette — odpowiedź 500 **nie** ma kształtu
`{"error_code": ..., "message": ...}` wymaganego w §5 dla wszystkich 4xx/5xx.
To łamie też zakładany przez frontend kontrakt parsowania
(`problem.detail?.message`, `App.tsx:60`) w nietypowych ścieżkach błędów.
Ten sam problem dotyczy braków pól na poziomie FastAPI (np. brak pliku
`image` w multipart) — Starlette zwraca własny format walidacji, inny niż
`{error_code, message}`.
**Poprawka:** dodać generyczny exception handler zwracający
`{"error_code": "INTERNAL_ERROR", "message": "..."}` przy 500, oraz
dedykowany handler dla `RequestValidationError` mapujący na
`PARAM_INVALID_TYPE`/`PARAM_OUT_OF_RANGE`.

### [P2] Pokrycie testami backendu nie realizuje wymagań §11.2/§11.5
**Plik:** `backend/tests/test_api.py` (2 testy), `backend/tests/test_mesh.py`
(brak testu ramki).
**Skutek:** brak dedykowanych testów dla `INVALID_IMAGE_FORMAT`,
`IMAGE_TOO_LARGE`, `IMAGE_DIMENSIONS_INVALID`, `PARAM_INVALID_TYPE`, dla
odrzucenia `border_height_mm < max_thickness_mm`, oraz — kluczowe — dla
`border_width_mm=0 → brak ramki` i ogólnie zachowania `apply_border`
(dokładnie ten test złapałby błąd z P1 #1/#2). Test property-based
manifoldu (`test_mesh.py:10-18`) ogranicza `rows`/`cols` do 2–12 zamiast
zalecanego w §11.3/§11.5 zakresu 2–50.
**Poprawka:** dopisać testy per `error_code` z §5, test regresyjny dla
ramki (w tym przypadek nakładania się z P1 #1), rozszerzyć zakres hypothesis.

### [P2] `resolution` jako bezpośredni parametr użytkownika narusza §6
**Plik:** `backend/app/models.py:27`, `frontend/src/App.tsx:88`.
**Skutek:** `ARCHITECTURE.md` §6 wprost zastrzega: rozdzielczość siatki
"jest wyprowadzana z rozdzielczości obrazu po resamplingu... a nie podawana
bezpośrednio przez użytkownika". Tu jest odwrotnie — `resolution` to suwak
UI przekazywany wprost do `grid_resolution`. Nie psuje to poprawności
geometrycznej (nadal jest degradacja przy przekroczeniu limitu), ale łamie
udokumentowany kontrakt i, w połączeniu z `MAX_GRID_POINTS=180_000`
(`backend/app/heightmap.py:6`, wobec `1_000_000` z §9), oznacza że spora
część zakresu suwaka (do 600 "pkt") jest cicho przycinana bez informacji dla
użytkownika (patrz też P2 niżej o `X-Grid-Downsampled`).
**Poprawka:** rozważyć usunięcie suwaka "Rozdzielczość" na rzecz
automatycznego wyprowadzania gęstości z obrazu (zgodnie z §6), albo — jeśli
świadomie zostaje jako funkcja V1 — udokumentować odstępstwo i podnieść/
zrównać `MAX_GRID_POINTS` z wartością z §9 (lub jawnie uzasadnić niższą).

### [P2] Cicha degradacja jakości siatki bez sygnału dla użytkownika
**Plik:** `backend/app/heightmap.py:9-18` (`grid_resolution`),
`backend/app/main.py` (brak nagłówka `X-Grid-Downsampled`).
**Skutek:** §9 rekomenduje (nice-to-have, ale jednak) nagłówek
`X-Grid-Downsampled: true` gdy gęstość jest automatycznie obniżana. Obecnie
downscale jest całkowicie niewidoczny — użytkownik ustawiający
"Rozdzielczość" na maksimum dla większej płyty dostaje istotnie rzadszą
siatkę bez żadnego wyjaśnienia w UI.
**Poprawka:** dodać nagłówek odpowiedzi i/lub pokazać w UI rzeczywistą
(a nie tylko żądaną) gęstość siatki.

### [P2] `border_height_mm` ma inny górny limit niż w dokumentacji
**Plik:** `backend/app/models.py:30` (`le=22`) vs `ARCHITECTURE.md` §6
(wiersz 172: zakres "0 – 20").
**Skutek:** drobny rozjazd kontraktu — użytkownik może ustawić
`border_height_mm=21` lub `22`, mimo że specyfikacja ogranicza to do 20 mm.
Nie psuje geometrii, ale to niezamierzona (najpewniej) niespójność ze
źródłem prawdy dla walidacji.
**Poprawka:** ujednolicić stałą z `ARCHITECTURE.md` §6 albo potwierdzić, że
zmiana zakresu jest świadoma.

### [P2] Szerokość ramki po zaokrągleniu do komórek siatki może istotnie odbiegać od żądanej
**Plik:** `backend/app/mesh.py:51-52` (`x_cells`/`y_cells`).
**Skutek:** `max(1, round(...))` wymusza **co najmniej jedną pełną komórkę**
ramki nawet gdy proporcjonalna szerokość zaokrągla się do zera, a sama
szerokość ramki jest kwantowana do całych komórek siatki, nie do mm. Przy
niskiej rozdzielczości (np. `resolution=24`) żądana cienka ramka (np. 1 mm)
może fizycznie wyjść jako pas szerokości kilku-kilkunastu mm (szerokość
jednej komórki na dużej płycie).
**Poprawka:** liczyć maskę ramki na podstawie ciągłych współrzędnych
(`xs < border_width_mm` itp.), nie liczby komórek, żeby szerokość fizyczna
nie zależała od rozdzielczości siatki.

## Uwagi (P3)

### [P3] Przykładowe indeksowanie trójkątów w `ARCHITECTURE.md` §8.2 nie zgadza się z własnymi wzorami — kod jest poprawny, dokument myli
**Plik referencyjny (bez edycji):** `ARCHITECTURE.md` §8.2 (linie 349-355);
kod: `backend/app/mesh.py:32-33`.
Policzone wprost ze wzorów z §8.2 (`x=j·skala`, `y=i·skala`, normalna
`(v1-v0)×(v2-v0)`): trójkąt `(v00, v10, v11)` opisany w architekturze daje
składową Z normalnej **ujemną** (do wnętrza), nie dodatnią jak twierdzi
tekst. Kod używa odwrotnej kolejności `(v00, v11, v10)`/`(v00, v01, v11)`,
która daje poprawną, skierowaną na zewnątrz normalną (+Z) — potwierdzone
niezależnym przeliczeniem i przechodzącym testem
`test_face_normals_point_outward_on_flat_plate`
(`backend/tests/test_mesh.py:28-37`). To nie jest błąd kodu — kod jest
geometrycznie poprawny — tylko niespójność ilustracyjnego przykładu w
architekturze z jej własnymi wzorami współrzędnych. Zgłaszane wyłącznie
informacyjnie (nie mogę edytować `ARCHITECTURE.md`), żeby ktoś czytający
oba dokumenty równolegle się nie pogubił.

### [P3] Brak testu round-trip dla `stl_writer` wymaganego w §11.1
**Plik:** `backend/tests/test_mesh.py:21-25`
(`test_binary_stl_length_and_count`) sprawdza tylko długość i liczbę
trójkątów, nie odtwarza i nie porównuje faktycznych współrzędnych
wierzchołków/normalnych zapisanych w pliku.
**Poprawka:** dopisać prosty parser binarnego STL w teście (lub użyć
`numpy-stl` tylko w teście) i porównać wartości z `mesh.vertices`/`faces`
z tolerancją float32, zgodnie z §11.1.

### [P3] Nieużywane katalogi `data/uploads/` i `data/output/`
**Plik:** `data/uploads/.gitkeep`, `data/output/.gitkeep`, wzmianka w
`README.md:26`. Grep po zapisie na dysk w `backend/app` (`open(`,
`tempfile`, `.save(`, `makedirs`) nie znajduje żadnego zapisu do tych
katalogów ani gdziekolwiek indziej — backend rzeczywiście nic nie
zapisuje na dysk (potwierdzone, patrz sekcja "Potwierdzone bez
zastrzeżeń"). Te katalogi nie są też częścią struktury repo z
`ARCHITECTURE.md` §4. Nieszkodliwe, ale to martwe rusztowanie.
**Poprawka:** usunąć albo doprecyzować w README, do czego faktycznie służą.

### [P3] `/api/preview` jest martwym endpointem z punktu widzenia frontendu
**Plik:** `backend/app/main.py:62-70` (`preview`) vs
`frontend/src/App.tsx:32-44` (podgląd liczony lokalnie na `<canvas>` przez
filtry CSS, bez żadnego wywołania `/api/preview`).
**Skutek:** dwa niezależne, potencjalnie rozjeżdżające się podglądy —
serwerowy (prawdziwy PIL: jasność/kontrast/crop/orientacja) i kliencki
(przybliżenie CSS-owe, np. nie odzwierciedla auto-rotacji z
`image_processing.py:39-41`). Nie jest to wymóg `ARCHITECTURE.md` (podgląd
3D jest jawnie poza zakresem V1, a ten endpoint to PNG-podgląd 2D, nie
wspomniany w architekturze wcale), ale skoro istnieje, warto go albo
wykorzystać dla wiernego podglądu, albo usunąć jako nieużywaną powierzchnię
API.

### [P3] `vite.config.ts` proxy działa tylko wewnątrz Compose
**Plik:** `frontend/vite.config.ts:4` (`proxy: {"/api": "http://backend:8000"}`).
**Skutek:** hostname `backend` rozwiązuje się tylko w sieci Docker Compose;
lokalny `npm run dev` poza Dockerem nie znajdzie API. Czysto DX, zero wpływu
na ścieżkę wdrożeniową Docker Compose ocenianą w tym review.

## Potwierdzone bez zastrzeżeń (no-findings)

- **Mapowanie luminancja→grubość** (`backend/app/heightmap.py:21-34`):
  poprawne dla `invert=False/True` i dowolnego `gamma` — jasność 1.0→
  `min_thickness_mm`, 0.0→`max_thickness_mm` (i odwrotnie przy `invert`),
  zgodnie z §7.2. Potwierdzone wyprowadzeniem matematycznym i przechodzącymi
  testami `test_mapping_endpoints_and_gamma`, `test_invert_swaps_endpoints`.
- **Orientacja osi Y** (`backend/app/mesh.py:21`, `np.flipud(heightmap)`):
  zweryfikowane śledzeniem kodu — górny wiersz zdjęcia poprawnie trafia na
  większe Y w mesh-space (nie jest odbity pionowo), zgodnie z jawnym
  ostrzeżeniem w §8.2. Brak dedykowanego testu integracyjnego na rogu
  obrazu (por. P2 #8), ale sama logika jest poprawna.
- **Watertightness / manifold / orientacja normalnych**
  (`backend/app/mesh.py:61-77`, `validate_mesh`): liczenie krawędzi,
  spójności nawijania i objętości ze znakiem jest matematycznie poprawne i
  jest egzekwowane jako twarda bramka przed każdą odpowiedzią
  (`MESH_GENERATION_FAILED` w `backend/app/main.py:50-53`), zgodnie z
  wymogiem §11.5 pkt 1 (jedyna twarda bramka jakości V1). Property test
  hypothesis (`test_generated_plate_is_watertight`) przechodzi.
- **Integralność binarnego STL** (`backend/app/exporter.py`): układ
  80-bajtowy nagłówek + uint32 liczby trójkątów + 50 bajtów/trójkąt zgodny
  z §7.4, potwierdzony przechodzącym testem asercji na dokładną długość i
  pole liczby trójkątów.
- **Prywatność plików**: potwierdzone grepem po całym `backend/app` — brak
  jakiegokolwiek zapisu przesłanego obrazu lub wygenerowanego STL/PNG na
  dysk; cały pipeline działa w pamięci (`BytesIO`), zgodnie z wymogiem
  "brak trwałego stanu" z §2. `data/uploads`/`data/output` istnieją, ale są
  nieużywane (patrz P3).
- **Docker Compose**: topologia (nginx frontendu proxujący `/api/` do
  wewnętrznie `expose`owanego backendu, healthcheck bramkujący
  `depends_on`, `client_max_body_size 21m` spójne z limitem 20 MB) jest
  spójna i sensowna, mimo że strukturalnie różni się od ilustracyjnego
  szkicu w §13 — architektura wprost zaznacza ten szkic jako niewiążący
  ("szkic strukturalny"). Brak trwałych wolumenów, brak sekretów — zgodnie
  z §13.
- **`GET /api/health`**: zwraca dokładnie `200 {"status": "ok"}` zgodnie z
  §5.
