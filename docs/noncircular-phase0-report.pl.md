# Faza 0 — raport numeryczny (GO)

Data: 2026-09-28. Baza: `034a33a`; implementacja od `47f9ee2`. Rewizja planu: 2.

## Decyzja

**GO dla implementacji programowej.** Oracle tworzy jawny standardowy
12-zębowy dłutak ewolwentowy 25°, generuje planetę przez zamiatanie dłutaka,
a koło centralne i pierścień jako obwiednie tej samej planety w ruchach
wynikających z kinematyki. Operacje union/difference/intersection wykonuje
deterministycznie biblioteka `polygon-clipping` 0.15.7 z siatką współrzędnych
`1e-5 mm`.

Surowa kinematyka jest w `tools/noncircular-oracle/results.json`, a pełne wyniki
wielokątowe w `geometry-results.json`. Polecenie odtwarzające:
`npm test` oraz `node geometry-report.mjs geometry-results.json` w katalogu oracle.

## Siatka bramki

- kwadrat: `e₁ = 0,03 / 0,04 / 0,05`;
- trójkąt: `e₁ = 0,04 / 0,06 / 0,08`;
- próbki ruchu co najwyżej co 1°; wszystkie planety w fazach wynikających z §4.8;
- trzy profile dopasowania i stopnie `0 / δ / 2δ` dla każdego przypadku.

Wszystkie przypadki mają domknięcie z residuum < `4e-16 rad`, `|k−1| < 0,22%`,
oddychanie orbity < 0,31%, regularne pojedyncze granice i dodatnią grubość.
Dłutak jest wolny od podcięcia; grubość głowy wynosi około `0,44m`, a stopa
około `0,97` grubości podziałowej (minimum planu: odpowiednio `max(0,25m,
0,4 mm)` oraz `0,8`).

Maksymalne pola przenikania S–P i P–R mieszczą się poniżej `1e-5 mm²`
(tolerancja kwantyzacji), planet–planeta wynosi zero, a minimalny odstęp planet
we wszystkich przypadkach przekracza wymagane `0,58 mm`. Przecięcia profili
warstw przejściowych są niepuste i mniejsze od profilu nominalnego, a rdzeń
kanału jest ściśle cofnięty.

## Model osiowy rewizji 2

Dla profili Ciasny / Standardowy / Luźny obliczone `δ` spełnia jednocześnie
blokadę `δ ≥ bₙ/cos(25°)+0,15`, półkę `δ cos(25°) ≤ 0,7 mm` i limit głowy
`δ ≤ 0,35πm`. Dwa pasy mają po trzy stopnie w przeciwnych kierunkach,
przejścia są przecięciami sąsiednich profili, kanał ma cofnięty rdzeń, a rampa
45° występuje wyłącznie pod pasem górnym.

## Ograniczenie wyniku

GO dotyczy geometrii obliczeniowej i pozwala przejść do SCAD. Nie potwierdza
sprawności fizycznej. Testy F1–F11 pozostają niewykonane i są jawnie opisane w
`docs/noncircular-physical-tests-protocol.pl.md`; bez wydruków nie wolno
deklarować retencji, łatwego rozruchu, trwałości ani jakości rampy.
