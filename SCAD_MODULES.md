# Moduły parametryczne OpenSCAD w Litho

## Zasada działania

Serwer przechowuje konta, źródła, metadane i wersje modułów. Nie ma zainstalowanego
OpenSCAD i nie generuje STL/3MF. Całe obliczenie wykonuje OpenSCAD WebAssembly w
osobnym Web Workerze przeglądarki użytkownika. Wynik pozostaje lokalnym obiektem
`Blob` używanym przez podgląd Three.js i przycisk pobierania.

Pierwsze generowanie pobiera około 11 MB WASM (około 3,4 MB po kompresji HTTP).
Kolejne uruchomienia korzystają z cache przeglądarki. Anulowanie kończy worker.

## Biblioteka

Interfejs ma dwie zakładki:

- **Moje moduły** — moduły bieżącego użytkownika;
- **Wszystkie moduły** — drafty i opublikowane moduły wszystkich użytkowników.

Każdy zalogowany użytkownik może przeglądać i generować widoczne moduły. Autor
może edytować kod i dane swoich modułów, a administrator może edytować każdy.
Status można filtrować jako `draft`, `published` lub `blocked`.

## Tworzenie i edycja

Przycisk **Nowy moduł** daje dwie możliwości:

1. rozpoczęcie od kodu przykładowego i edycja w przeglądarce;
2. import pojedynczego `.scad` albo ZIP z lokalnymi bibliotekami i assets.

Przycisk **Edytuj kod** otwiera źródło pliku wejściowego. Każdy zapis tworzy nową
wersję roboczą i ponownie parsuje parametry Customizera. W module ZIP zmieniany
jest tylko plik wejściowy, a pozostałe biblioteki i assets są zachowane.

## Obsługiwana składnia Customizera

```scad
/* [Main] */
diameter = 60;       // [40:1:100]
style = "Fine";      // [Fine,Standard,Chunky]
output_mode = 0;     // [0:Complete,1:Preview,2:Ring only]
enabled = true;
```

Litho rozpoznaje liczby, tekst, boolean, listy, opisane listy liczbowe, sekcje,
wartości domyślne, zakres i krok. Obsługiwane tagi dodatkowe:
`@label`, `@description`, `@unit`, `@hidden`, `@advanced`, `@group`, `@order`.

## Wersjonowanie

Nowy moduł zaczyna jako `draft`. Zapis kodu tworzy kolejną wersję roboczą.
Publikacja ustawia bieżącą wersję publiczną, a dalsza edycja nie nadpisuje jej
do czasu następnej publikacji. Przywrócenie starej wersji tworzy nową rewizję i
nie usuwa historii.

## Uprawnienia

- autor: edycja kodu i danych, publikacja, wersje i usunięcie własnego modułu;
- inny użytkownik: odczyt, generowanie lokalne, preset i duplikowanie;
- administrator: edycja i moderacja wszystkich modułów;
- `hidden`: niewidoczny dla innych użytkowników;
- `blocked`: widoczny, ale bez możliwości generowania;
- usuwanie jest miękkie, trwałe usunięcie jest dostępne administratorowi.

Kontrola dostępu jest egzekwowana przez backend, a nie tylko przez ukrycie
przycisków w interfejsie.

## Konfiguracja

| Zmienna | Domyślnie | Znaczenie |
|---|---:|---|
| `LITHO_SCAD_MAX_SOURCE_BYTES` | 10485760 | limit źródeł/ZIP |
| `LITHO_SCAD_MAX_MODULES_PER_USER` | 100 | limit aktywnych modułów |
| `LITHO_SCAD_CATEGORIES` | lista kategorii | kategorie rozdzielone przecinkami |
| `LITHO_SCAD_SEED_EXAMPLES` | true | utworzenie przykładów przy pierwszym starcie |

Źródła są zapisywane w `/data/scad`, a metadane w bazie kont
`/data/auth.sqlite3`. Migracja bazowa znajduje się w
`backend/app/scad/migrations/001_scad_platform.sql`.
