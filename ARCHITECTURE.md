# Generator Litofanii — Architektura V1

Status: projekt architektury (brak kodu aplikacji). Właściciel implementacji: Codex.
Właściciel architektury: Claude (ten dokument).

## 1. Cel i zakres V1

Aplikacja webowa: użytkownik wgrywa obraz (JPEG/PNG), ustawia parametry fizyczne
litofanii (wymiary, grubości, orientacja, ramka), serwis generuje watertight mesh
i zwraca plik STL do pobrania.

**W zakresie V1:**
- Jeden obraz wejściowy → jeden model STL wyjściowy (płaska litofania prostokątna).
- Przetwarzanie synchroniczne, jeden request = jedno zadanie (bez kolejki, bez workerów).
- Docker Compose: 2 kontenery (frontend, backend), bez GPU, bez usług zewnętrznych.
- Generowanie mesha w 100% we własnym kodzie (numpy), bez zewnętrznych generatorów
  CAD/mesh (np. bez OpenSCAD, bez Blender, bez CGAL).

**Poza zakresem V1** (odnotowane jako przyszłe kierunki, nie projektowane szczegółowo):
- Litofanie zakrzywione/cylindryczne/sferyczne, litofanie wielowarstwowe/kolorowe.
- Konta użytkowników, historia zadań, przechowywanie plików długoterminowo.
- Kolejka zadań / przetwarzanie asynchroniczne / progres w czasie rzeczywistym.
- Podgląd 3D w przeglądarce (opcjonalne rozszerzenie — patrz §10).

## 2. Przegląd systemu

```
┌─────────────────┐       multipart/form-data        ┌──────────────────────┐
│  Frontend (SPA)  │ ───────────POST /api/generate──▶ │  Backend (FastAPI)   │
│  React + TS      │ ◀──────── 200: model/stl ──────  │  Python 3.11+        │
│  Vite            │           4xx: application/json  │                      │
└─────────────────┘                                    └──────────┬───────────┘
                                                                    │
                                                    in-process pipeline (sync)
                                                                    │
                                       ┌────────────────────────────┼────────────────────────────┐
                                       ▼                            ▼                             ▼
                                image_processing              heightmap                    mesh_builder
                                (dekodowanie,                 (mapowanie                    (siatka watertight,
                                 skala szarości,               wysokość↔jasność,             indeksacja trójkątów)
                                 resampling)                   inwersja, clamp)
                                                                                                    │
                                                                                                    ▼
                                                                                              stl_writer
                                                                                        (binary STL, normale)
```

Cały pipeline działa synchronicznie w jednym request/response (V1: obrazy do
rozsądnego rozmiaru, patrz limity w §6). Brak trwałego stanu po stronie backendu —
plik wynikowy jest strumieniowany do odpowiedzi i nigdzie nie zapisywany na dysku
poza katalogiem tymczasowym request-scoped.

## 3. Stos technologiczny

| Warstwa   | Technologia                                             |
|-----------|----------------------------------------------------------|
| Frontend  | React 18 + TypeScript, Vite, natywny `fetch`/`FormData`  |
| Backend   | Python 3.11+, FastAPI, Uvicorn                            |
| Przetw. obrazu | Pillow (dekodowanie, konwersja skali szarości, resampling) |
| Numeryka  | NumPy (heightmap, generacja siatki wektorowo)             |
| Mesh/STL  | numpy-stl **lub** ręczny zapis binarnego STL (decyzja w §7.5) |
| Kontenery | Docker, Docker Compose                                    |
| Testy backend | pytest, hypothesis (property-based dla geometrii)     |
| Testy frontend | Vitest + React Testing Library                        |

Brak baz danych, brak kolejek (Redis/Celery), brak GPU/CUDA, brak zewnętrznych
API. Wszystko działa lokalnie w kontenerze backendu.

## 4. Struktura repozytorium (docelowa, do wypełnienia przez Codex)

```
/frontend
  /src
    /api          # klient HTTP do /api/generate, typy DTO
    /components    # UploadForm, ParamsPanel, ErrorBanner, DownloadButton
    /validation    # walidacja parametrów po stronie klienta (lustro §6)
  vite.config.ts
  Dockerfile
/backend
  /app
    main.py                # FastAPI app, routing, error handlers
    /api
      generate.py           # POST /api/generate — orchestruje pipeline
      schemas.py             # Pydantic: LithophaneParams, ErrorResponse
    /pipeline
      image_processing.py    # decode_image, to_grayscale, resample
      heightmap.py            # brightness_to_height, normalize
      mesh_builder.py          # build_watertight_mesh, build_frame
      stl_writer.py             # write_binary_stl
    /core
      errors.py               # wyjątki domenowe → kody HTTP
      limits.py                 # stałe limitów (rozmiar, wymiary, DPI)
  /tests
    unit/           # per-moduł, czyste funkcje
    integration/    # pełny pipeline na małych obrazach syntetycznych
    property/       # hypothesis: manifold-ness, watertightness
  Dockerfile
  requirements.txt
/docker-compose.yml
ARCHITECTURE.md
```

Ta struktura jest **rekomendacją**, nie kontraktem sztywnym — Codex może ją
dostosować, ale granice modułów pipeline (image_processing → heightmap →
mesh_builder → stl_writer) i ich kontrakty funkcyjne (§7) są wiążące, bo od
nich zależy testowalność i poprawność geometryczna.

## 5. API — kontrakt HTTP

### `POST /api/generate`

**Request:** `multipart/form-data`

| Pole            | Typ            | Wymagane | Opis                                           |
|-----------------|----------------|----------|-------------------------------------------------|
| `image`         | plik (binary)  | tak      | JPEG lub PNG, RGB/RGBA/skala szarości           |
| `width_mm`      | float          | tak      | szerokość modelu w mm                           |
| `height_mm`     | float          | nie      | wysokość w mm; jeśli brak — liczona z proporcji obrazu |
| `min_thickness_mm` | float       | tak      | grubość w najjaśniejszym punkcie (najcieńsza)   |
| `max_thickness_mm` | float       | tak      | grubość w najciemniejszym punkcie (najgrubsza)  |
| `border_width_mm`  | float       | nie (domyślnie 0) | szerokość ramki wokół płyty (0 = brak ramki) |
| `border_height_mm` | float       | nie (domyślnie = max_thickness_mm) | wysokość ramki ponad max_thickness |
| `invert`        | bool           | nie (domyślnie false) | true = ciemne piksele → cienkie (negatyw) |
| `mirror`        | bool           | nie (domyślnie false) | odbicie lustrzane przed generacją        |

**Response 200:** `application/vnd.ms-pkistl` a w praktyce `model/stl` lub
`application/octet-stream` (nagłówek `Content-Disposition: attachment;
filename="lithophane.stl"`), body = binarny STL.

**Response 4xx:** `application/json`

```json
{
  "error_code": "IMAGE_TOO_LARGE",
  "message": "Obraz przekracza maksymalny rozmiar 20 MB.",
  "field": "image"
}
```

Kody błędów (enum, stabilny kontrakt dla frontendu):

| `error_code`            | HTTP | Przyczyna                                         |
|--------------------------|------|----------------------------------------------------|
| `INVALID_IMAGE_FORMAT`   | 422  | nie-JPEG/PNG, uszkodzony plik                       |
| `IMAGE_TOO_LARGE`        | 413  | plik > `MAX_UPLOAD_BYTES`                           |
| `IMAGE_DIMENSIONS_INVALID` | 422 | obraz zbyt mały (< 8×8 px) lub zbyt duży (> 8000×8000 px) |
| `PARAM_OUT_OF_RANGE`     | 422  | parametr fizyczny poza dozwolonym zakresem (§6)     |
| `PARAM_INVALID_TYPE`     | 422  | np. `width_mm` nie parsuje się jako float           |
| `MESH_GENERATION_FAILED` | 500  | wewnętrzny błąd pipeline'u mesh (bug, nie input)    |
| `INTERNAL_ERROR`         | 500  | nieoczekiwany wyjątek                                |

Walidacja parametrów jest wykonywana **dwukrotnie**: raz w warstwie Pydantic
(typy, obecność), raz w warstwie domenowej `core/limits.py` (zakresy fizyczne,
relacje między polami — patrz §6). Frontend replikuje te same reguły
(zaimportowane stałe/JSON schema lub ręcznie zsynchronizowane stałe) dla
natychmiastowego feedbacku, ale **backend jest źródłem prawdy** — nigdy nie
ufa walidacji klienta.

### `GET /api/health`

Zwraca `200 {"status": "ok"}`. Używane przez `docker-compose` healthcheck.

## 6. Walidacja parametrów — reguły i uzasadnienie

| Parametr            | Zakres dozwolony        | Uzasadnienie                                                        |
|----------------------|--------------------------|------------------------------------------------------------------------|
| `width_mm`            | 20 – 400                | poniżej 20 mm szczegóły giną w druku; powyżej 400 mm — poza typowym build volume |
| `height_mm`            | 20 – 400 (jeśli podane) | jw.                                                                     |
| `min_thickness_mm`      | 0.4 – 10                | poniżej 0.4 mm — niedrukowalne (mniej niż 1 linia ekstruzji przy typowej dyszy 0.4 mm); światło nie prześwituje przy dużej grubości |
| `max_thickness_mm`       | musi być > `min_thickness_mm`, oraz ≤ `min_thickness_mm` + 12 | zbyt duża rozpiętość → nadmierny czas druku i słaby kontrast lokalny |
| `border_width_mm`         | 0 – 30                | ramka ma usztywniać krawędzie, nie dominować nad obrazem                |
| `border_height_mm`         | 0 – 20, i musi być ≥ `max_thickness_mm` gdy `border_width_mm` > 0 | ramka musi wystawać ponad najgrubszy punkt płyty, inaczej nie spełnia funkcji usztywniającej/montażowej |
| rozmiar pliku obrazu         | ≤ `MAX_UPLOAD_BYTES` = 20 MB | ochrona pamięci/czasu przetwarzania (brak kolejki — request musi zakończyć się w rozsądnym czasie) |
| wymiary obrazu (px)            | 8×8 – 8000×8000        | dolna granica: sensowna siatka; górna granica: ochrona czasu generacji mesha (patrz §9 limity wydajności) |

Dodatkowa reguła spójności: rozdzielczość siatki (liczba wierzchołków na X/Y)
jest **wyprowadzana** z rozdzielczości obrazu po resamplingu (§7.2), a nie
podawana bezpośrednio przez użytkownika — unika to niespójności między
"jakością" obrazu a gęstością siatki.

Wszystkie reguły zakresowe są zdefiniowane jako stałe w
`backend/app/core/limits.py` i mają być jedynym miejscem prawdy (Codex nie
powinien duplikować liczb inline w handlerach).

## 7. Kontrakty modułów pipeline

Pipeline to czysta sekwencja transformacji danych — każdy moduł jest
funkcyjny (bez efektów ubocznych poza I/O na granicach), co czyni go
testowalnym w izolacji.

### 7.1 `image_processing`

```python
def decode_image(raw_bytes: bytes) -> PIL.Image.Image:
    """Dekoduje JPEG/PNG. Rzuca InvalidImageFormatError przy uszkodzonych/
    nieobsługiwanych danych. Konwertuje CMYK/paletę do RGB przed dalszym przetwarzaniem."""

def to_grayscale(image: PIL.Image.Image) -> PIL.Image.Image:
    """Konwersja do L (8-bit grayscale) metodą luminancji percepcyjnej
    (ITU-R 601/709, tak jak Pillow domyślnie robi w convert("L"))."""

def resample_to_grid(image: PIL.Image.Image, target_cols: int, target_rows: int) -> np.ndarray:
    """Resampling do siatki docelowej (bilinear/lanczos). Zwraca float32
    array [rows, cols] w zakresie [0.0, 1.0] (0=czarny, 1=biały)."""
```

**Kontrakt:** wynik `resample_to_grid` ma kształt `(rows, cols)` gdzie
`rows`/`cols` są determinowane przez `heightmap.compute_grid_resolution`
(§7.2) na podstawie `width_mm`/`height_mm` i stałej gęstości próbkowania
(punkty na mm — patrz §9).

### 7.2 `heightmap`

```python
def compute_grid_resolution(width_mm: float, height_mm: float, points_per_mm: float) -> tuple[int, int]:
    """Zwraca (cols, rows), zaokrąglone w górę do min. 2, ograniczone przez
    MAX_GRID_POINTS (§9) — jeśli przekroczone, points_per_mm jest
    proporcjonalnie zmniejszane (degradacja jakości, nie błąd)."""

def brightness_to_height(grid: np.ndarray, min_thickness_mm: float,
                          max_thickness_mm: float, invert: bool) -> np.ndarray:
    """Mapuje jasność [0,1] na grubość [min_thickness_mm, max_thickness_mm].
    Domyślnie (invert=False): jasność 1.0 (biały) → min_thickness (cienko,
    dużo światła przechodzi); jasność 0.0 (czarny) → max_thickness (grubo,
    mało światła). invert=True odwraca tę relację.
    Zwraca float32 array [rows, cols] — wysokość górnej powierzchni ponad
    płaszczyznę bazową z=0."""
```

**Decyzja projektowa:** płaszczyzna bazowa (spód modelu) jest zawsze płaska
w z=0. Górna powierzchnia to `height_map`. To gwarantuje, że model stoi
stabilnie na stole drukarki bez podpór pod spodem.

### 7.3 `mesh_builder`

To najbardziej krytyczny moduł pod kątem poprawności geometrycznej — patrz
szczegółowa specyfikacja topologii w §8.

```python
@dataclass
class Mesh:
    vertices: np.ndarray  # float32 [N, 3]
    triangles: np.ndarray  # int32 [M, 3], indeksy do vertices, CCW od zewnątrz

def build_plate_mesh(height_map: np.ndarray, width_mm: float, height_mm: float) -> Mesh:
    """Buduje watertight mesh płyty: górna powierzchnia (z=height_map),
    dolna powierzchnia (z=0, płaska), oraz 4 ściany boczne łączące obwód
    góry z obwodem dołu. Patrz §8 dla dokładnej triangulacji."""

def add_frame(plate: Mesh, height_map_shape: tuple[int, int], width_mm: float,
              height_mm: float, border_width_mm: float, border_height_mm: float) -> Mesh:
    """Dokleja prostokątną ramkę (jak obramowanie obrazka) wokół istniejącej
    płyty jako osobną, zespoloną bryłę watertight, następnie łączy (unia
    wierzchołków na wspólnej krawędzi płyta/ramka — bez boolean mesh ops,
    przez współdzielenie wierzchołków na styku). Zwraca pojedynczy Mesh
    (może zawierać rozłączne komponenty topologicznie, co jest
    akceptowalne dla druku 3D o ile każdy komponent jest manifold)."""
```

**Decyzja projektowa (brak boolean CSG):** V1 świadomie unika operacji
boolowskich mesh (union/difference) między płytą a ramką, ponieważ wymagałyby
biblioteki CSG (np. `trimesh` + `manifold3d`/`pymesh`) — dodatkowa zależność,
złożoność, potencjalne niestabilności numeryczne na granicach. Zamiast tego
ramka jest generowana jako geometria, która **dzieli wierzchołki** z krawędzią
płyty w miejscach styku (identyczne współrzędne x,y na obwodzie), co daje
efekt wizualny i strukturalny połączenia bez potrzeby CSG. Ograniczenie:
ramka musi mieć prostą prostokątną geometrię (nie może "otaczać" nieregularnego
kształtu) — akceptowalne dla V1, bo płyta jest zawsze prostokątna.

### 7.4 `stl_writer`

```python
def write_binary_stl(mesh: Mesh) -> bytes:
    """Serializuje Mesh do binarnego formatu STL. Dla każdego trójkąta
    oblicza normalną z iloczynu wektorowego krawędzi (v1-v0)×(v2-v0),
    zgodnie z orientacją CCW (patrz §8.2). Zapisuje 80-bajtowy header,
    4-bajtowy uint32 liczby trójkątów, następnie po 50 bajtów na trójkąt
    (12×float32 normalna+3 wierzchołki + uint16 attribute=0)."""
```

**Decyzja: binary STL, nie ASCII.** Mniejszy rozmiar pliku (istotne przy
transferze HTTP), szybszy zapis/parsowanie, powszechnie wspierany przez
slicery. ASCII STL nie jest oferowany w V1 (brak potrzeby, dodaje tylko
kod do utrzymania).

### 7.5 Decyzja: własna implementacja vs. `numpy-stl`

Rekomendacja: **własna funkcja `write_binary_stl`** (via `struct.pack`/
`numpy.tobytes`) zamiast zależności `numpy-stl`. Format binary STL jest
prosty (opisany w §7.4) i pełna kontrola nad serializacją ułatwia debugging
problemów z orientacją normalnych. `numpy-stl` jest akceptowalną alternatywą
jeśli Codex oceni, że przyspiesza to development — decyzja niewiążąca,
w przeciwieństwie do struktury Mesh (vertices/triangles) i reguł orientacji
w §8, które MUSZĄ być zachowane niezależnie od wybranej metody serializacji.

## 8. Topologia mesha — specyfikacja wiążąca

To jest najbardziej krytyczna część architektury. Błędy tutaj produkują
niedrukowalne modele (non-manifold, odwrócone normalne, dziury).

### 8.1 Definicja "watertight" / manifold dla V1

Mesh jest watertight wtedy i tylko wtedy, gdy:
1. Każda krawędź (para wierzchołków) jest współdzielona przez **dokładnie
   dwa** trójkąty (edge-manifold).
2. Każdy trójkąt ma spójną orientację (CCW patrząc od zewnątrz) — normalne
   wszystkich trójkątów wskazują na zewnątrz bryły.
3. Brak zdegenerowanych trójkątów (trzy współliniowe punkty lub powtórzony
   wierzchołek w trójkącie).
4. Mesh nie ma otworów — każda krawędź obwodowa dowolnej podpowierzchni
   (góra/dół/boki) musi się dokładnie połączyć z odpowiadającą krawędzią
   sąsiedniej podpowierzchni.

To jest test do zaimplementowania w `tests/property/test_manifold.py`
(patrz §11.3).

### 8.2 Indeksowanie wierzchołków i triangulacja siatki

Dla siatki wysokości o wymiarach `rows × cols` (indeksy `i` = 0..rows-1
wiersze wzdłuż Y, `j` = 0..cols-1 kolumny wzdłuż X):

**Indeks liniowy wierzchołka górnej powierzchni:**
```
top_index(i, j) = i * cols + j
```

**Indeks wierzchołka dolnej powierzchni** (przesunięcie o `rows*cols`):
```
bottom_index(i, j) = rows * cols + i * cols + j
```

**Współrzędne wierzchołka:**
```
x = j * (width_mm / (cols - 1))
y = i * (height_mm / (rows - 1))
z_top = height_map[i, j]
z_bottom = 0.0
```

Układ współrzędnych: X rośnie w prawo, Y rośnie "w głąb" (od dołu obrazu
ku górze — uwaga na flip osi Y między współrzędnymi obrazu (0,0 = lewy-górny,
Y w dół) a współrzędnymi mesha (Y w górę): `heightmap` musi odwrócić wiersze
obrazu przy budowie siatki, inaczej model wyjdzie lustrzanie odwrócony w
pionie względem oryginału).

**Triangulacja jednej komórki siatki (kwadrat i,i+1 × j,j+1), górna
powierzchnia, CCW patrząc z +Z (z góry):**

```
v00 = top_index(i,   j)      v01 = top_index(i,   j+1)
v10 = top_index(i+1, j)      v11 = top_index(i+1, j+1)

trójkąt A: (v00, v10, v11)   # przekątna od v00 do v11
trójkąt B: (v00, v11, v01)
```

Weryfikacja CCW: patrząc z +Z w dół (standard: X w prawo, Y w górę, Z ku
obserwatorowi), kolejność `v00→v10→v11` obiega przeciwnie do wskazówek
zegara gdy `v10` jest "niżej" (większe i) i `v11` dalej w prawo — normalna
`(v10-v00)×(v11-v00)` musi mieć dodatnią składową Z. **To jest test
jednostkowy obowiązkowy** (§11.1): dla znanej komórki 2×2 sprawdzić znak
`normal.z > 0` dla obu trójkątów górnej powierzchni.

**Dolna powierzchnia** — te same indeksy komórki, ale odwrócona kolejność
(normalna w -Z), bo patrzymy "od spodu":

```
trójkąt A: (b00, b11, b10)   # b_xx = bottom_index(...)
trójkąt B: (b00, b01, b11)
```

### 8.3 Ściany boczne (łączenie obwodu góry z obwodem dołu)

Obwód siatki to cztery krawędzie: `i=0` (przód), `i=rows-1` (tył), `j=0`
(lewo), `j=cols-1` (prawo). Dla każdej pary sąsiednich punktów na obwodzie
generujemy prostokąt (2 trójkąty) łączący odpowiadające wierzchołki top/bottom.

Przykład dla krawędzi `j=0` (lewa ściana), para punktów `i` i `i+1`:

```
top_a    = top_index(i,   0)     top_b    = top_index(i+1, 0)
bottom_a = bottom_index(i, 0)    bottom_b = bottom_index(i+1, 0)
```

Normalna lewej ściany musi wskazywać w kierunku -X (na zewnątrz). Kolejność
zapewniająca to (weryfikować testem, nie tylko wzorem — patrz §11.1):

```
trójkąt A: (top_a, bottom_a, bottom_b)
trójkąt B: (top_a, bottom_b, top_b)
```

Analogicznie dla pozostałych trzech krawędzi obwodu, z odpowiednio odwróconą
kolejnością tak, aby normalna zawsze wskazywała na zewnątrz (+X dla prawej
ściany, -Y i +Y dla przedniej/tylnej — dokładny dobór kolejności ma być
wyprowadzony i zweryfikowany testem jednostkowym per-ściana, nie zgadywany
w trakcie implementacji).

**Ogólna reguła do zastosowania przy implementacji wszystkich 4 ścian:**
normalna trójkąta = `(v1-v0) × (v2-v0)`; jeśli wynik wskazuje do wnętrza
bryły, zamienić kolejność dwóch ostatnich wierzchołków trójkąta (odwraca
orientację bez zmiany geometrii).

### 8.4 Ramka (border)

Ramka jest prostym "obramowaniem" — prostokątną obwódką o stałej wysokości
`border_height_mm` i szerokości `border_width_mm`, otaczającą płytę na
zewnątrz. Modelowana jako druga, niezależna siatka watertight (analogiczna
konstrukcja góra/dół/boki jak w §8.2–8.3, ale na prostokącie zamiast na
heightmap — górna powierzchnia ramki jest płaska na `z = border_height_mm`),
z wewnętrzną krawędzią o współrzędnych identycznych z zewnętrznym obwodem
płyty (tak by wierzchołki się pokrywały co do wartości — deduplication
wierzchołków po scaleniu jest **opcjonalna** dla poprawności STL, bo STL nie
wymaga współdzielenia wierzchołków między niezależnymi manifold-bryłami;
ważne jest tylko, żeby nie było szczeliny/luki geometrycznej między nimi).

**Uproszczenie V1:** płyta i ramka mogą pozostać dwoma osobnymi manifold
komponentami w jednym pliku STL (tzw. "multi-body STL"), stykającymi się
lub lekko zachodzącymi na siebie (overlap rzędu `epsilon` = 0.01 mm) zamiast
wymagać dokładnego sklejenia w jeden spójny manifold. Overlap gwarantuje
brak szczelin nawet przy błędach numerycznych zaokrągleń współrzędnych
float32. Większość slicerów (i sam druk 3D) poprawnie obsługuje multi-body
STL, o ile każdy komponent z osobna jest manifold i bryły się nie
przenikają w sposób tworzący non-manifold geometry (dlatego overlap musi
być "positive union" — patrz test w §11.3, sprawdzenie że objętość
połączonej bryły nie ma niespodziewanych ubytków).

### 8.5 Znane ograniczenia geometryczne V1 (do udokumentowania w kodzie/README, nie do "naprawiania" teraz)

- Ekstremalnie kontrastowe obrazy z pojedynczymi izolowanymi jasnymi
  pikselami na czarnym tle mogą tworzyć bardzo cienkie, kruche fragmenty
  (grubość bliska `min_thickness_mm`) — to zjawisko fizyczne modelu, nie
  błąd mesha; brak automatycznego wygładzania w V1.
- Brak dekymacji siatki — liczba trójkątów rośnie liniowo z rozdzielczością
  obrazu (ograniczoną przez `MAX_GRID_POINTS`, §9), co jest świadomym
  kompromisem prostoty nad optymalnością rozmiaru pliku.

## 9. Limity wydajności i zasobów (V1, bez GPU, brak kolejki)

| Stała                  | Wartość      | Uzasadnienie                                                  |
|--------------------------|--------------|------------------------------------------------------------------|
| `MAX_UPLOAD_BYTES`         | 20 MB       | ochrona pamięci procesu                                          |
| `MAX_IMAGE_DIMENSION`        | 8000 px    | ochrona przed dekompresją "image bomb"                            |
| `POINTS_PER_MM` (domyślne)      | 4          | ok. 0.25 mm rozdzielczości siatki — sensowne dla druku FDM 0.4 mm dyszy |
| `MAX_GRID_POINTS`                | 1 000 000 (np. 1000×1000) | ok. 4M trójkątów górnej+dolnej powierzchni; utrzymuje generację i serializację w akceptowalnym czasie (docelowo < 10 s na typowym sprzęcie deweloperskim, do zweryfikowania testem wydajnościowym, nie twardym SLA) |
| `REQUEST_TIMEOUT`                  | 60 s (poziom serwera/proxy, nie kod aplikacji) | górna granica dla przetwarzania synchronicznego |

Jeśli `compute_grid_resolution` (§7.2) wyliczy rozdzielczość przekraczającą
`MAX_GRID_POINTS` dla podanych `width_mm`/`height_mm` przy domyślnym
`POINTS_PER_MM`, gęstość próbkowania jest **automatycznie redukowana**
(z zachowaniem proporcji), a nie zwracany jest błąd — użytkownik dostaje
działający, nieco mniej szczegółowy model zamiast odrzuconego requestu.
Ta decyzja (degradacja jakości > twardy błąd) ma być odnotowana w
odpowiedzi jako nagłówek `X-Grid-Downsampled: true` (opcjonalnie, nice-to-have,
nie blokujące dla V1).

## 10. Frontend — kontrakt komponentów (szkic, szczegóły do Codex)

- `UploadForm`: wybór pliku (drag&drop + input), podgląd miniatury.
- `ParamsPanel`: formularz kontrolowany, walidacja klientowa lustrzana do §6
  (natychmiastowy feedback), ale **zawsze** wysyła request do backendu i ufa
  jego walidacji jako ostatecznej.
- `ErrorBanner`: renderuje `error_code`/`message` z odpowiedzi 4xx backendu
  (mapowanie `error_code` → komunikat PL, fallback na `message` z API).
- `DownloadButton`: po sukcesie inicjuje pobranie pliku `.stl` z response
  blob (nie trzyma pliku w stanie dłużej niż to konieczne).

**Poza V1 (odnotowane, nie projektowane):** podgląd 3D w przeglądarce (np.
three.js) — wymagałby dodatkowej zależności i nie jest niezbędny do
podstawowej funkcji "wygeneruj i pobierz STL". Rekomendacja dla V2 jeśli
potrzebne.

Frontend i backend komunikują się wyłącznie przez `/api/*` — w Docker
Compose frontend serwuje statyczne pliki (build Vite) przez lekki serwer
(np. `vite preview` lub nginx), backend nasłuchuje na osobnym porcie;
przeglądarka wywołuje backend bezpośrednio (CORS skonfigurowany na
konkretny origin frontendu, nie `*`, nawet w V1 — unikanie złych nawyków
bezpieczeństwa od początku).

## 11. Plan testów

### 11.1 Testy jednostkowe (`tests/unit/`)

- `image_processing`: dekodowanie poprawnego JPEG/PNG; odrzucenie
  uszkodzonego pliku (`InvalidImageFormatError`); konwersja RGBA→grayscale
  zachowuje relatywną jasność znanych pikseli; resampling do zadanej siatki
  zwraca poprawny kształt i zakres [0,1].
- `heightmap`: `compute_grid_resolution` dla znanych `width_mm`/`height_mm`
  zwraca oczekiwane `(cols, rows)`; redukcja gęstości przy przekroczeniu
  `MAX_GRID_POINTS`; `brightness_to_height` — biały→min_thickness,
  czarny→max_thickness (i odwrotnie dla `invert=True`), monotoniczność
  (większa jasność → mniejsza grubość przy invert=False).
- `mesh_builder` (**obowiązkowe, krytyczne**): dla siatki 2×2 (najmniejszy
  możliwy przypadek) zweryfikować dokładną liczbę trójkątów (2 góra + 2 dół
  + 8 boki = 12), zweryfikować znak normalnej każdego trójkąta (górna: +Z,
  dolna: -Z, boczne: odpowiednio ±X/±Y) przez jawne obliczenie iloczynu
  wektorowego w teście; zweryfikować brak duplikatów indeksów w pojedynczym
  trójkącie (zdegenerowane trójkąty).
- `stl_writer`: round-trip — zapisany binary STL sparsowany z powrotem
  (własnym prostym parserem testowym lub `numpy-stl`) odtwarza te same
  wierzchołki/trójkąty z tolerancją float32.

### 11.2 Testy integracyjne (`tests/integration/`)

- Pełny pipeline na małych obrazach syntetycznych (generowanych w teście,
  np. gradient 16×16, szachownica 8×8, jednolity kolor) → poprawny binary
  STL o oczekiwanej strukturze nagłówka i liczbie trójkątów zgodnej ze
  wzorem `4*(rows-1)*(cols-1) + 2*2*(rows-1) + 2*2*(cols-1)` (góra+dół+boki).
- Endpoint `POST /api/generate` (via `TestClient` FastAPI): happy path
  zwraca 200 z poprawnym `Content-Type`/`Content-Disposition`; każdy
  `error_code` z §5 ma dedykowany test wyzwalający dokładnie ten kod przy
  odpowiednio spreparowanym requeście (zły format, zbyt duży plik, parametr
  poza zakresem, `max_thickness <= min_thickness`, ramka z
  `border_height < max_thickness`).
- Test `border_width_mm=0` → brak ramki w wyniku (mesh identyczny jak bez
  wywołania `add_frame`).

### 11.3 Testy property-based (`tests/property/`, hypothesis)

- **Manifold check** (najważniejszy test w całym projekcie): dla losowo
  generowanych heightmap (różne rows/cols w rozsądnym zakresie, losowe
  wartości wysokości) zweryfikować że wygenerowany Mesh spełnia definicję
  z §8.1 — algorytm: zbudować słownik `edge → count` z wszystkich
  krawędzi wszystkich trójkątów (krawędź jako `frozenset({v_a, v_b})`),
  assert że każda wartość w słowniku == 2.
- **Orientacja spójna:** dla tego samego losowego mesha, dla każdego
  trójkąta obliczyć normalną i środek trójkąta, i sprawdzić że wektor od
  centroidu całej bryły do środka trójkąta ma nieujemny iloczyn skalarny
  z normalną (heurystyka "normalna wskazuje na zewnątrz" dla brył
  wypukłych/gwiaździstych względem centroidu — wystarczająca dla prostej
  geometrii prostopadłościennej V1; udokumentować to ograniczenie w
  komentarzu testu).
- **Brak zdegenerowanych trójkątów:** dla każdego trójkąta pole
  powierzchni (via cross product magnitude / 2) > epsilon.
- **Zakres współrzędnych:** wszystkie wierzchołki mieszczą się w
  oczekiwanym bounding boxie `[0, width_mm] × [0, height_mm] × [0,
  max_thickness_mm + border_height_mm]` (z tolerancją float32).

### 11.4 Testy frontendu (Vitest)

- Walidacja formularza: wprowadzenie wartości poza zakresem (§6) blokuje
  submit i pokazuje komunikat, zanim request trafi do sieci.
- Mapowanie błędów API: mock fetch zwracający każdy `error_code` z §5 →
  poprawny komunikat w `ErrorBanner`.
- Happy path: mock 200 z blobem STL → `DownloadButton` inicjuje pobranie
  (asercja na wywołanie odpowiedniego API przeglądarki, nie na rzeczywisty
  zapis pliku).

### 11.5 Kryteria akceptacji testów (definicja "gotowe")

1. Wszystkie testy jednostkowe i property-based dla `mesh_builder` muszą
   przechodzić **przed** merge jakiegokolwiek PR dotykającego ten moduł —
   to jedyny moduł z twardą bramką jakości w V1 (reszta może iterować
   szybciej).
2. Test manifold (§11.3) musi przechodzić dla min. 100 losowych przypadków
   hypothesis (rows/cols w zakresie 2–50, żeby test był szybki w CI).
3. Pokrycie testami modułów `pipeline/*`: dąż do >90% linii, ale nie jest
   to twardy gate — priorytetem jest jakość testów geometrycznych nad
   metryką pokrycia.
4. CI (jeśli/gdy Codex skonfiguruje) uruchamia `pytest` i `vitest` na
   każdym PR; brak wymogu e2e/browser testów w V1.

## 12. Ryzyka i mitigacje

| Ryzyko                                                        | Wpływ | Mitigacja w V1                                                                 |
|-----------------------------------------------------------------|-------|-----------------------------------------------------------------------------------|
| Non-manifold mesh (dziury, odwrócone normalne) → niedrukowalny plik | Wysoki | Property-based test manifold jako obowiązkowa bramka (§11.3, §11.5); precyzyjna specyfikacja indeksowania w §8 eliminuje niejednoznaczność przy implementacji |
| Duże obrazy → zbyt długi czas przetwarzania synchronicznego (brak kolejki w V1) | Średni | Twarde limity `MAX_UPLOAD_BYTES`/`MAX_IMAGE_DIMENSION`/`MAX_GRID_POINTS` (§9) odrzucają lub degradują zbyt duże requesty zamiast blokować proces na długo |
| Niespójność walidacji frontend/backend (np. frontend przepuszcza coś, co backend odrzuca) | Niski | Backend jest jedynym źródłem prawdy (§5); frontend to tylko UX-owy skrót, nie bramka bezpieczeństwa |
| Błędna orientacja osi Y (obraz vs. mesh) → model lustrzanie odwrócony w pionie | Średni | Jawnie udokumentowane w §8.2; obowiązkowy test integracyjny na asymetrycznym obrazie testowym (np. pojedynczy jasny piksel w rogu) weryfikujący, że trafia we właściwy róg mesha |
| Rozjazd ramki i płyty (szczelina, non-manifold na styku) | Średni | Strategia "positive overlap" zamiast dokładnego sklejenia (§8.4); test integracyjny sprawdzający brak ujemnej odległości między komponentami |
| Zależność `numpy-stl` niekompatybilna z przyszłą wersją NumPy | Niski | Rekomendacja własnej serializacji STL (§7.5) minimalizuje powierzchnię zależności zewnętrznych |
| Pamięć: duża siatka (bliska `MAX_GRID_POINTS`) w połączeniu z wieloma równoległymi requestami przeciąża kontener | Średni | V1 świadomie nie rozwiązuje współbieżności (brak kolejki) — odnotowane jako ograniczenie do adresowania w V2 (worker queue), Uvicorn z ograniczoną liczbą workerów w Compose jako tymczasowe ograniczenie throughput |
| Brak testów wizualnych (czy model "wygląda dobrze") | Niski | Poza zakresem automatyzacji V1; weryfikacja manualna przez Codex/dewelopera przed release, opcjonalnie snapshot renderowanego podglądu w V2 |

## 13. Docker Compose — kontrakt wdrożeniowy

```yaml
# docker-compose.yml (szkic strukturalny, Codex wypełnia Dockerfile'e)
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
    environment:
      - MAX_UPLOAD_BYTES=20971520
  frontend:
    build: ./frontend
    ports: ["3000:80"]
    depends_on:
      backend:
        condition: service_healthy
```

Brak wolumenów trwałych (brak potrzeby — bezstanowy pipeline). Brak
zmiennych sekretnych w V1 (brak autentykacji, brak kluczy API zewnętrznych).

## 14. Otwarte decyzje pozostawione Codexowi (nieblokujące, taktyczne)

Poniższe są celowo niedoprecyzowane — to detale implementacyjne, nie
decyzje architektoniczne:
- Dokładny wybór biblioteki HTTP klienta we frontendzie (natywny `fetch`
  wystarcza, ale `axios` jest akceptowalny).
- Formatowanie/linting (ruff/black dla backendu, eslint/prettier dla
  frontendu) — dowolna rozsądna konfiguracja.
- Dokładna struktura komponentów React poza kontraktem funkcjonalnym z §10.
- Nazewnictwo wewnętrznych helperów w `mesh_builder.py` poza publicznym
  kontraktem funkcji z §7.3.

## 15. Podsumowanie decyzji architektonicznych (skrót)

1. Pipeline w pełni synchroniczny, w procesie, bez kolejki — świadomy
   kompromis prostoty V1 kosztem przepustowości (§2, §12).
2. Brak zewnętrznych generatorów CAD/mesh — cała geometria budowana ręcznie
   w NumPy według jawnej specyfikacji indeksowania (§8).
3. Binary STL, generowany bez zależności `numpy-stl` jako preferowana opcja
   (§7.4–7.5).
4. Ramka i płyta jako dwa nakładające się (epsilon-overlap) komponenty
   manifold zamiast wymogu CSG boolean union (§7.3, §8.4).
5. Backend jako jedyne źródło prawdy dla walidacji; frontend duplikuje
   reguły wyłącznie dla UX (§5, §6, §12).
6. Test manifold property-based jako jedyna twarda bramka jakości w V1
   (§11.5) — reszta testów jest zalecana, nie blokująca.
