# Litho for WooCommerce

Wtyczka dodaje do wskazanych produktów WooCommerce uproszczony konfigurator litofanii. Klient wybiera zdjęcie, kadr, rozmiar, orientację, kolor obudowy i barwę LED. Typ obudowy oraz sposób zasilania są przypisane do produktu przez obsługę sklepu i nie są prezentowane jako opcje klienta.

## Instalacja

1. Spakuj katalog `litho-woocommerce` jako `litho-woocommerce.zip`.
2. W WordPressie otwórz **Wtyczki → Dodaj nową → Wyślij wtyczkę na serwer**.
3. Aktywuj **Litho for WooCommerce**.
4. Otwórz **WooCommerce → Litho** i ustaw:
   - adres API, np. `https://litho.smartintegracje.pl`,
   - ten sam sekret co `LITHO_ADMIN_API_KEY` w kontenerze Litho,
   - dostępne kolory obudowy,
   - barwy LED (`warm`, `neutral`, `cool`).

Ustawienia adresu API i sekretu są dostępne wyłącznie dla administratora WordPressa (`manage_options`). Obsługa sklepu nadal może korzystać z projektów i pobierać pliki z poziomu zamówień.
5. Edytuj każdy odpowiedni produkt WooCommerce. W sekcji danych produktu:
   - zaznacz **Konfigurator Litho**,
   - przypisz `Ramka` albo `Box`,
   - przypisz `Przewodowe` albo `Bateryjne`.

Najprostsza oferta składa się z czterech produktów: ramka przewodowa, ramka bateryjna, box przewodowy i box bateryjny.

W środowisku produkcyjnym najlepiej przechowywać sekret poza bazą WordPressa. Dodaj go do `wp-config.php`; pole klucza w ustawieniach wtyczki może wtedy pozostać puste:

```php
define('LITHO_ADMIN_API_KEY', 'ten-sam-dlugi-sekret-co-w-kontenerze-litho');
```

## Bezpieczeństwo

- `LITHO_ADMIN_API_KEY` jest używany wyłącznie po stronie PHP i może być przechowywany w `wp-config.php` zamiast w bazie danych.
- Token projektu otrzymany z Litho jest szyfrowany w sesji proxy i nigdy nie trafia do JavaScriptu klienta.
- Żądania gościa wymagają zarówno nonce, jak i losowego tokenu powiązanego z jego sesją WooCommerce.
- Strony produktów z aktywnym konfiguratorem wysyłają nagłówki `no-cache`, ponieważ zawierają token sesji klienta.
- Dodanie projektu do koszyka wymaga podpisu HMAC i ponownego potwierdzenia projektu przez API.
- WordPress akceptuje wyłącznie JPG/PNG do 20 MB.
- Typ obudowy i zasilanie są ponownie odczytywane z produktu po stronie serwera.
- Po utworzeniu zamówienia WordPress przypisuje jego ID do projektu w Litho.
- Pobranie zdjęcia albo STL przez administratora wymaga uprawnienia, nonce oraz zgodności projektu z konkretnym zamówieniem.

## Dane zamówienia

Pozycja zamówienia przechowuje identyfikator projektu oraz migawkę konfiguracji. Administrator widzi rozmiar, orientację, kolor obudowy i barwę LED, a także przyciski pobrania zdjęcia źródłowego i STL. Typ obudowy i zasilanie wynikają z zakupionego produktu.

## Ograniczenia V1

- Obsługiwane są standardowe formularze dodawania do koszyka WooCommerce dla produktów prostych.
- Jeden zatwierdzony projekt ma zawsze ilość `1`; kolejne zdjęcie należy skonfigurować i dodać jako osobną pozycję. Dzięki temu jedno zamówienie może zawierać kilka różnych litofanii tego samego produktu.
- Wtyczka generuje STL litofanii. Obudowa jest przygotowywana przez obsługę w produkcyjnym generatorze Litho.
- Porzucone projekty należy okresowo usuwać z panelu/API Litho; automatyczna polityka retencji będzie osobnym etapem.
