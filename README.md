# Litho — generator litofanii i obudów 3D

Samodzielna aplikacja webowa oparta na React i FastAPI. Generuje litofanie STL,
dopasowane obudowy oraz udostępnia bibliotekę parametrycznych modułów OpenSCAD.

## Publikacja obrazu w GitHub Container Registry

Workflow `.github/workflows/container-images.yml` buduje jeden obraz aplikacji
dla `linux/amd64` (Synology z procesorem Intel/AMD), a następnie publikuje go jako:

```text
ghcr.io/klimuszko/litho:latest
```

Pakiety GHCR muszą być publiczne albo serwer Docker musi być wcześniej zalogowany
przez `docker login ghcr.io`.

## Uruchomienie na serwerze

Skopiuj `docker-compose.yml` i `.env.example` na serwer, zmień nazwę pliku na
`.env`, a następnie ustaw nazwę obrazu, domenę, DNS oraz nazwę istniejącej sieci.
Jeden kontener otrzymuje statyczny adres `10.10.50.19` w zewnętrznej sieci
`VLAN50_Docker`. FastAPI serwuje zarówno API, jak i zbudowany frontend React.
Sieć zewnętrzna musi już istnieć i mieć subnet obejmujący `10.10.50.19`.
Jeżeli nie jest zarządzana przez Twój obecny stack, przykładowe utworzenie wygląda
tak (dopasuj CIDR i sterownik do swojej infrastruktury):

```bash
docker network create -d macvlan --subnet=10.10.50.0/24 --gateway=10.10.50.1 -o parent=YOUR_VLAN_INTERFACE VLAN50_Docker
```

W repozytorium GitHub ustaw właściwą gałąź produkcyjną jako domyślną. Tylko
obrazy z tej gałęzi otrzymują tag `latest`; pozostałe są dostępne po tagu SHA.

```bash
docker compose pull
docker compose up -d
```

Ruch HTTP/HTTPS obsługuje Traefik według `LITHOPHANE_DOMAIN`. Port hosta nie
jest publikowany bezpośrednio.

Zatrzymanie: `docker compose down`.

## Pipeline

`JPEG/PNG → korekcja i crop → luminancja → mapa grubości → zamknięty mesh → walidacja → binary STL`

Jasne piksele dają minimalną grubość, a ciemne maksymalną:

```text
t = min + (1 - luminance)^gamma * (max - min)
```

Generator przetwarza obraz i geometrię w pamięci. Trwałe projekty klientów są
zapisywane wyłącznie w prywatnym wolumenie aplikacji.

## Generator obudów

Widok `Obudowa` generuje `Box` albo `Ramkę` dla paneli 100 × 150,
130 × 180, 150 × 200 mm oraz wymiarów własnych mieszczących się na stole
256 × 256 mm. Wynikiem jest ZIP z korpusem, tylną pokrywą, klinami oraz
`README-PL.txt` zawierającym aktualne ustawienia produkcyjne.

Najważniejsze parametry:

- minimalna głębokość obudowy: 40 mm,
- szerokość obramowania ramki: 17 mm,
- zewnętrzna kompensacja pleców: 0,20 mm na każdą krawędź
  (0,40 mm w całym wymiarze),
- luz rantu pleców: 0,20 mm na stronę,
- lokalny wcisk zaczepów pleców: 0,05 mm,
- zewnętrzna część pleców: 3 mm,
- wewnętrzny biały odbłyśnik: 1 mm.

`back.stl` zawiera dwie wyrównane, zamknięte bryły przeznaczone do druku
jedno- albo dwukolorowego. Dla warstwy 0,20 mm pierwszych 15 warstw jest
czarnych, a biały materiał zaczyna się od warstwy 16.

```text
POST /api/housing/generate
Content-Type: application/json
```

Oba warianty są przeznaczone dla litofanii wygenerowanej z opcją
`Kołnierz montażowy Litho Mount V2`.

## Generator puzzli

Widok `Puzzle` przygotowuje dwa niezależne pliki: wielokolorowy model puzzli
`3MF` oraz paczkę `ZIP` z ramką i składaną podpórką. Domyślna konfiguracja to
100 elementów, format 150 × 200 mm i 4 kolory wybrane automatycznie wyłącznie
z listy posiadanych filamentów. Dostępne siatki mają 36, 64, 100, 144 lub
225 elementów, a generator pilnuje minimalnego rozmiaru pojedynczego puzzla
oraz pola roboczego 250 × 250 mm.

Domyślne przygotowanie obrazu jest automatyczne: generator wyrównuje zakres
jasności, wzmacnia istotne detale i najpierw rozpoznaje główne role kolorów
w fotografii, a dopiero potem przypisuje im rzeczywiście dostępne filamenty.
Dzięki temu mały, ale ważny obszar (np. niebieska bluza albo twarz) nie znika
tylko dlatego, że inny kolor minimalnie lepiej pasował do większości pikseli.
Można też ręcznie wybrać pełny kolor, ciepłą sepię albo skalę czarno-białą.
Sepia i skala szarości używają uporządkowanych tonów od ciemnego do jasnego,
co zwykle daje najlepszą czytelność portretu przy 3–5 filamentach.
W ustawieniu automatycznym projekt czterokolorowy korzysta z czytelnej skali
sepii; przy większej palecie kolorowe fotografie zachowują swoje główne barwy.
Tryb `Kolor` pozwala wymusić barwny wynik także przy czterech filamentach.

Plik 3MF zachowuje każdy puzzel jako osobny obiekt i przypisuje częściom
wybrane filamenty. Dostępne są dwa sposoby druku koloru:

- `Warstwowo` — kolor dominujący jest pełnym podkładem, a kolejne kolory
  zajmują osobne wysokości Z. Tryb nie wymaga AMS i ogranicza zmiany filamentu
  do jednej zmiany na poziom.
- `Jedna wysokość` — kolor dominujący nadal wzmacnia cały puzzel, natomiast
  wszystkie kolory obrazu tworzą wspólną, płaską powierzchnię. Ten wariant
  wymaga AMS lub innego systemu wielomateriałowego.

Ramka ma jednocześnie otwory do zawieszenia i zawias podpórki pod popularną
śrubę M3 × 30, dlatego nie trzeba wybierać sposobu ekspozycji przed drukiem.

## Ustawienia powierzchni Fuzzy Skin

Fuzzy Skin dodaje drobną, nieregularną fakturę, która ogranicza widoczność
linii warstw na zewnętrznych powierzchniach obudowy.

```text
Odległość punktów: 0,15 mm
Grubość:           0,10 mm
```

Teksturę należy stosować tylko na widocznych powierzchniach zewnętrznych
korpusu i pokrywy. Nie należy jej nakładać na panel litofanii ani na powierzchnie
pasowane: rant pleców, zatrzaski, kliny, kieszeń panelu i mocowania elektroniki.
Te same informacje są automatycznie dodawane do `README-PL.txt` w każdej nowej
paczce STL.

## Testy backendu

```bash
docker build -t lithophane-test .
docker run --rm -v "${PWD}/backend:/work" -w /work lithophane-test sh -c "pip install -r requirements-dev.txt && python -m pytest -q"
```

Najważniejsza bramka jakości sprawdza, że każda krawędź wygenerowanego mesha należy dokładnie do dwóch trójkątów i że nie występują zdegenerowane ściany.

## Kalibracja P1S

Punkt startowy dla białego PLA: 0,6 mm / 4,0 mm / gamma 1,0. Wydrukuj tę samą fotografię z kilkoma wartościami gamma i maksymalnej grubości, zachowując ten sam filament, profil slicera oraz źródło światła. Wyniki są zależne od materiału — parametry są celowo konfigurowalne.

## Projekty klientów i WooCommerce

Backend udostępnia trwałe projekty klientów z prywatnym tokenem, generowaniem STL w tle oraz osobnym dostępem administracyjnym. Projekty i zdjęcia są zapisywane w prywatnym wolumenie `/data/projects`; nie trafiają do katalogu statycznego aplikacji. Kontrakt integracyjny, cykl życia projektu i wymagane zmienne środowiskowe opisuje [WOOCOMMERCE_API.md](WOOCOMMERCE_API.md).

Dostęp do generatora jest chroniony lokalnymi kontami administratorów i operatorów. Pierwsze konto, role, sesje oraz wdrożenie opisuje [AUTHENTICATION.md](AUTHENTICATION.md).

## Parametryczne moduły OpenSCAD

Litho zawiera wieloużytkownikową bibliotekę generatorów SCAD z dynamicznym UI,
podglądem 3D, eksportem STL/3MF, presetami, wersjami draft/published, rolami,
moderacją, audytem, kolejką, anulowaniem i cache. Instrukcja importowania modułów,
składnia Customizera i model bezpieczeństwa są opisane w
[SCAD_MODULES.md](SCAD_MODULES.md). Przykładowy moduł minimalny oraz planetary
fidget znajdują się w `examples/scad/`.

Szczegółowe decyzje i kontrakty opisuje [ARCHITECTURE.md](ARCHITECTURE.md).
