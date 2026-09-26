# Moduły parametryczne OpenSCAD w Litho

## Uruchomienie

Obraz produkcyjny instaluje OpenSCAD i ustawia `OPENSCAD_BINARY=/usr/bin/openscad`.
Źródła, wersje i cache renderów są zapisywane w `/data/scad`; metadane są w tej
samej bazie SQLite co konta (`/data/auth.sqlite3`). Po wdrożeniu otwórz pozycję
**Moduły** w głównej nawigacji.

Najważniejsze ustawienia:

| Zmienna | Domyślnie | Znaczenie |
|---|---:|---|
| `LITHO_SCAD_RENDER_TIMEOUT` | 120 | limit czasu procesu w sekundach |
| `LITHO_SCAD_MEMORY_MB` | 2048 | limit pamięci procesu na Linuksie |
| `LITHO_SCAD_MAX_CONCURRENT_RENDERS` | 2 | liczba workerów |
| `LITHO_SCAD_MAX_CONCURRENT_PER_USER` | 1 | aktywne zadania jednego użytkownika |
| `LITHO_SCAD_MAX_SOURCE_BYTES` | 10485760 | limit źródeł/ZIP |
| `LITHO_SCAD_MAX_OUTPUT_BYTES` | 262144000 | limit STL/3MF |
| `LITHO_SCAD_MAX_MODULES_PER_USER` | 100 | limit aktywnych modułów |
| `LITHO_SCAD_CATEGORIES` | lista kategorii | kategorie rozdzielone przecinkami |

Stan silnika można sprawdzić przez `GET /api/scad/engine`.

## Tworzenie modułu

Wybierz **Moduły → Dodaj moduł** i prześlij pojedynczy plik `.scad` albo ZIP.
ZIP zachowuje katalogi i może wyglądać tak:

```text
module/
├── main.scad
├── module.json
├── preview.png
├── assets/
└── libraries/
```

`module.json` jest opcjonalny. Pole `entry` wskazuje plik startowy; domyślnie
jest to `main.scad`. Przy pojedynczym `.scad` Litho automatycznie zapisuje go jako
`main.scad`. Brakujące `include`/`use`, ścieżki absolutne, `..` i dynamiczne
ścieżki `import()`/`surface()` są odrzucane przed utworzeniem wersji.

Przykłady gotowe do importu: `examples/scad/minimal` oraz
`examples/scad/planetary-fidget`.

## Obsługiwana składnia Customizera

```scad
/* [Main] */
diameter = 60;       // [40:1:100]
thickness = 1.5;     // [0.5:0.1:3]
style = "Fine";      // [Fine,Standard,Chunky]
enabled = true;
caption = "Example";
```

Litho rozpoznaje `integer`, `float`, `boolean`, `string`, `enum`, sekcje,
wartość domyślną, zakres i krok. Wyrażenia, funkcje i wartości wyliczane nie są
traktowane jako parametry — kod wykonuje OpenSCAD, a nie parser Litho.

```scad
finger_hole = 22; // [16:1:30] @unit:mm @label:"Finger hole" @description:"Opening" @order:4
debug = false;    // @hidden
helix = 25;       // [10:1:45] @advanced @group:"Advanced geometry"
```

Obsługiwane tagi: `@label`, `@description`, `@unit`, `@hidden`, `@advanced`,
`@group`, `@order`. Parametry ukryte są widoczne autorowi w Developer mode.

## Rendering i metadata

Parametry są walidowane według modelu parsera i przekazywane jako osobne argumenty
`-D`; źródło nie jest modyfikowane. Stringi są serializowane jako literały JSON.
Render ma status `queued`, `running`, `completed`, `failed`, `cancelled` albo
`timed_out` i można go rzeczywiście anulować.

```scad
mode = "model"; // [model,metadata] @hidden
echo("INFO:ring_teeth=49");
echo("WARNING:Finger hole reduced");
```

API przyjmuje `mode: "model" | "metadata"`. Techniczne `stdout`, `stderr`,
argumenty, czas, hash źródła i informacja o cache są dostępne w Developer mode.
Klucz cache obejmuje moduł, wersję, hash źródeł, parametry, wersję OpenSCAD, tryb
i format.

## Publikowanie i wersjonowanie

Import tworzy prywatny `draft` i pierwszą wersję roboczą. Zapisanie nowej wersji
roboczej nie zmienia generatora publicznego. Dopiero **Opublikuj wersję** ustawia
`published_version_id`. Inni użytkownicy zawsze otwierają wersję opublikowaną;
właściciel i administrator widzą wersję roboczą.

Przywrócenie starej wersji tworzy nową rewizję. Porównanie zwraca diff źródła:

```text
GET /api/scad/modules/{id}/versions/compare?left={id}&right={id}
```

Duplikowanie tworzy prywatny draft nowego właściciela oraz zachowuje
`forked_from_module_id` i `forked_from_version_id`.

## Uprawnienia

Istniejąca rola Litho `operator` odpowiada użytkownikowi modułów; `admin` zachowuje
pełne uprawnienia administracyjne. Reguły egzekwuje centralna polityka backendowa.

- właściciel tworzy wersje, publikuje, wycofuje, udostępnia i usuwa swój moduł;
- inni używają i duplikują publiczny moduł, ale nie mogą go edytować;
- presety są prywatne dla użytkownika i modułu;
- admin może hide/block/restore, zmieniać Official, usuwać i przeglądać audyt;
- `hidden` usuwa z katalogu, `blocked` blokuje wykonanie;
- usuwanie jest miękkie; trwałe usunięcie kasuje źródła, wersje i cache.

Widoczności: `private`, `public`, `unlisted`, `system`. Tylko admin ustawia
`system`. `unlisted` działa przez link. Zakładka „Udostępnione” pokazuje moduły
przypisane konkretnemu loginowi.

## Bezpieczeństwo

Każdy render działa w oddzielnym katalogu tymczasowym jako osobny proces bez
`shell=True`. Na Linuksie ustawiane są limity CPU, pamięci, rozmiaru pliku i liczby
procesów; timeout i anulowanie kończą grupę procesu. Kontener ma
`no-new-privileges` i limit PID. Importy wychodzące poza katalog są odrzucane, a
katalog roboczy jest sprzątany.

OpenSCAD nie zapewnia kompletnego sandboxa systemowego. Obecna izolacja zakłada,
że kontener Litho jest granicą bezpieczeństwa. Dla anonimowego publicznego hostingu
zalecany jest osobny, bezsieciowy kontener worker per render z read-only rootfs.

## Diagnostyka

1. Sprawdź `GET /api/scad/engine`.
2. Otwórz Developer mode.
3. Dla `MISSING_INCLUDE` prześlij cały folder jako ZIP.
4. Dla `RENDER_TIMEOUT` zmniejsz jakość lub kontrolowanie zwiększ limit.
5. `ASSERT_FAILED` zwykle oznacza niedozwoloną kombinację parametrów.

Migracja: `backend/app/scad/migrations/001_scad_platform.sql`.
