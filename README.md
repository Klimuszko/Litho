# Litho — generator litofanii V1

Samodzielna aplikacja webowa generująca płaskie, zamknięte modele litofanii STL bez GPU i bez zewnętrznego generatora geometrii.

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

Backend przetwarza obraz i STL wyłącznie w pamięci. Katalogi `data/` pozostają przygotowane do opcjonalnej diagnostyki, lecz V1 nie zapisuje w nich prywatnych plików.

## Generator obudów

Widok `Obudowa` generuje podświetlany `Box` albo `Ramkę` dla paneli
100 × 150, 130 × 180, 150 × 200 mm oraz wymiarów własnych. Podany wymiar jest
dokładnym wymiarem panelu Litho; aplikacja automatycznie dodaje ściany, kieszeń
montażową 2,0 mm, luz, obramowanie i tylną pokrywę. Wynikiem jest ZIP zawierający
osobny STL korpusu i pokrywy oraz instrukcję montażu. Panel wkłada się od otwartego
tyłu, opiera kołnierzem o wewnętrzny rant i dociska pod 4 lub 6 sprężystych
zatrzasków. Montaż nie wymaga kleju ani dodatkowych części. Oba modele są
eksportowane płaską stroną do stołu i nie wymagają podpór.

```text
POST /api/housing/generate
Content-Type: application/json
```

Oba warianty są przeznaczone dla litofanii wygenerowanej z opcją
`Kołnierz montażowy Litho Mount V1`.

## Testy backendu

```bash
docker build -t lithophane-test .
docker run --rm -v "${PWD}/backend:/work" -w /work lithophane-test sh -c "pip install -r requirements-dev.txt && python -m pytest -q"
```

Najważniejsza bramka jakości sprawdza, że każda krawędź wygenerowanego mesha należy dokładnie do dwóch trójkątów i że nie występują zdegenerowane ściany.

## Kalibracja P1S

Punkt startowy dla białego PLA: 0,8 mm / 3,2 mm / gamma 1,0. Wydrukuj tę samą fotografię z kilkoma wartościami gamma i maksymalnej grubości, zachowując ten sam filament, profil slicera oraz źródło światła. Wyniki są zależne od materiału — parametry są celowo konfigurowalne.

## Ograniczenia V1

- płaski model prostokątny;
- synchroniczne generowanie;
- opcjonalna ramka rozszerza bryłę na zewnątrz i nie zabiera obszaru fotografii;
- brak 3MF, kolejki i podglądu 3D.

Szczegółowe decyzje i kontrakty opisuje [ARCHITECTURE.md](ARCHITECTURE.md).
