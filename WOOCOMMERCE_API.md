# Integracja Litho z WooCommerce — API projektów V1

API projektów oddziela uproszczony kreator klienta od produkcyjnego generatora Litho. WordPress przechowuje przy pozycji zamówienia tylko `project_id` oraz migawkę wybranych wariantów. Zdjęcie i STL pozostają w prywatnym katalogu aplikacji Litho.

Całe API projektów jest zamknięte za uwierzytelnieniem. Do czasu wdrożenia krótkotrwałych tokenów kreatora wywołania klienta muszą przechodzić przez serwer WordPressa, który dodaje `X-Litho-Admin-Key`. Klucza nie wolno wysyłać do przeglądarki. `project_token` nadal ogranicza dostęp do jednego konkretnego projektu.

## Konfiguracja projektu

`POST /api/customer/projects`

```json
{
  "size": "150x200",
  "orientation": "portrait",
  "housing_type": "frame",
  "housing_color": "black-matte",
  "light_temperature": "warm",
  "crop": {"x": 0, "y": 0, "width": 1, "height": 1},
  "rotation_degrees": 0,
  "brightness": 1,
  "contrast": 1.25,
  "gamma": 1
}
```

Dozwolone formaty to `100x150`, `130x180` i `150x200`; orientacja może być `landscape` albo `portrait`. Typ obudowy to `frame` lub `box`. Sposób zasilania nie jest częścią konfiguracji projektu klienta.

Odpowiedź zawiera niezmienny `project_id` oraz `project_token`. Token jest zwracany tylko przy utworzeniu projektu i należy go trzymać po stronie sesji kreatora, a nie w publicznych metadanych WooCommerce.

## Cykl życia

1. `POST /api/customer/projects` — utworzenie projektu.
2. `PUT /api/customer/projects/{project_id}` — aktualizacja konfiguracji.
3. `POST /api/customer/projects/{project_id}/image` — upload JPEG/PNG jako multipart (`image`).
4. `POST /api/customer/projects/{project_id}/generate` — uruchomienie generowania w tle (HTTP 202).
5. `GET /api/customer/projects/{project_id}` — status i metadane.
6. `GET /api/customer/projects/{project_id}/artifacts/lithophane_stl` — pobranie STL.

Wywołania 2–6 wymagają nagłówka:

```text
X-Project-Token: <project_token>
```

Statusy projektu: `awaiting_image`, `ready`, `generating`, `completed`, `failed`.

Po odpowiedzi 202 kreator odpytuje endpoint statusu, aż otrzyma `completed` albo `failed`. Dzięki temu żądanie WordPressa nie musi pozostawać otwarte przez cały czas budowania dużego STL.

Produkcja klienta jest celowo zablokowana na sprawdzonych parametrach: dysza 0,4 mm, geometria maksymalna, grubość 1,0–4,0 mm oraz kołnierz Litho Mount V1. Klient nie może ich przypadkowo zmienić.

## Dostęp administratora

WordPress lub panel produkcyjny korzysta z nagłówka:

```text
X-Litho-Admin-Key: <LITHO_ADMIN_API_KEY>
```

Endpointy:

- `GET /api/admin/projects` — projekty od najnowszych,
- `GET /api/admin/projects/{project_id}` — szczegóły,
- `GET /api/admin/projects/{project_id}/source` — zdjęcie źródłowe,
- `GET /api/admin/projects/{project_id}/artifacts/lithophane_stl` — gotowy STL.
- `PUT /api/admin/projects/{project_id}/order` — przypisanie `{"order_id":"..."}` po utworzeniu zamówienia,
- `DELETE /api/admin/projects/{project_id}` — trwałe usunięcie zdjęcia, metadanych i artefaktów.

Jeśli `LITHO_ADMIN_API_KEY` nie jest ustawiony, endpointy administracyjne odpowiadają kodem 503. Pliki nie są publikowane przez serwer statyczny.

Przypisanie tego samego projektu ponownie do tego samego `order_id` jest idempotentne. Próba przypisania projektu do innego zamówienia zwraca HTTP 409 i nie nadpisuje pierwotnego powiązania.

## WooCommerce

Typ obudowy (`frame` albo `box`) jest przypisany przez obsługę do produktu WooCommerce. Sposób zasilania nie jest osobnym polem konfiguratora ani ustawieniem integracji — wynika z nazwy, opisu, atrybutu lub wariantu produktu WooCommerce i nie jest wysyłany do API projektu.

Do pozycji koszyka i zamówienia należy skopiować:

```text
project_id
size
orientation
housing_type
housing_color
light_temperature
```

`project_id` jest właściwym powiązaniem z plikami produkcyjnymi. Migawka wariantów pozwala odtworzyć zamówienie nawet po późniejszej zmianie nazw kolorów albo oferty.

## Obudowy i oświetlenie

V1 zapisuje typ obudowy, ale generuje wyłącznie STL litofanii. Informacje handlowe o sposobie zasilania pozostają po stronie produktu WooCommerce i nie sterują generowaniem.

Referencyjna wtyczka znajduje się w `wordpress/litho-woocommerce`. Wszystkie wywołania przechodzą przez proxy WordPressa; klucz administratora i `project_token` nie są ujawniane w JavaScript.
