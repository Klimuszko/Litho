# Dostęp do Litho

Cały interfejs producenta i wszystkie endpointy API poza `GET /api/health` oraz `POST /api/auth/login` są domyślnie chronione. Dokumentacja OpenAPI jest wyłączona w obrazie produkcyjnym.

## Pierwsze konto administratora

Przed pierwszym wdrożeniem ustaw w `.env` lub edytorze stacka:

```env
LITHO_BOOTSTRAP_ADMIN_USERNAME=admin
LITHO_BOOTSTRAP_ADMIN_PASSWORD=unikalne-haslo-o-dlugosci-minimum-12-znakow
LITHO_BOOTSTRAP_ADMIN_DISPLAY_NAME=Administrator
```

Konto bootstrap jest tworzone tylko wtedy, gdy `/data/auth.sqlite3` nie zawiera żadnego użytkownika. Po pierwszym poprawnym zalogowaniu można usunąć `LITHO_BOOTSTRAP_ADMIN_PASSWORD` ze zmiennych stacka — konto pozostanie w bazie na wolumenie.

Nie usuwaj pliku `/data/auth.sqlite3`, ponieważ zawiera konta i aktywne sesje. Katalog `/data` musi być bind-mountem wskazanym przez `LITHOPHANE_DATA_PATH`.

## Role

- `admin` — generator, obudowy oraz tworzenie, wyłączanie i resetowanie haseł kont;
- `operator` — generator i obudowy bez zarządzania użytkownikami;
- `service` — wewnętrzna tożsamość klucza WordPressa, ograniczona do API projektów klientów i zamówień.

System nie pozwala wyłączyć lub zdegradować ostatniego aktywnego administratora. Wyłączenie konta albo zmiana hasła unieważnia wszystkie jego sesje.

## Bezpieczeństwo

- hasła są przechowywane jako pamięciożerne hashe `scrypt` z unikalną solą;
- losowa sesja ma 256 bitów i wygasa po 12 godzinach;
- identyfikator sesji jest wyłącznie w ciasteczku `HttpOnly; Secure; SameSite=Strict; Path=/`;
- operacje zmieniające stan wymagają osobnego tokenu CSRF;
- po dziesięciu błędnych próbach adres klienta jest czasowo blokowany, bez umożliwienia osobie trzeciej trwałego zablokowania konkretnego konta;
- zmiana hasła i wyłączenie konta natychmiast usuwają jego sesje.

HTTPS musi pozostać włączony w Traefiku. Nie wyłączaj `LITHO_SECURE_COOKIES` w środowisku produkcyjnym.

## WordPress

Klucz `LITHO_ADMIN_API_KEY` jest przeznaczony wyłącznie do komunikacji serwer WordPress → Litho. Nie wolno umieszczać go w JavaScript ani HTML. Klucz działa tylko dla `/api/customer/*` i `/api/admin/projects*`; nie może zarządzać kontami Litho ani korzystać z produkcyjnego generatora poza projektami zamówień.

## Skalowanie

Kontener pracuje jako pojedynczy proces Uvicorn. Ograniczanie prób jest przechowywane w pamięci procesu. Przed uruchomieniem wielu workerów lub replik należy przenieść limiter do wspólnego magazynu, np. Redis.
