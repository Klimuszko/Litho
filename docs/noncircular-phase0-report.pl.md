# Faza 0 — raport numeryczny (NO-GO)

Data: 2026-09-28. Baza: `034a33a`. Rewizja planu: 2.

## Decyzja

**NO-GO.** Wstępny oracle potwierdza okresową podziałkę, kinematykę centroid,
domknięcie po korekcie `k`, małe oddychanie orbity oraz wykonalność przekroju
osiowego rewizji 2. Nie ma jeszcze dowodu regularności obwiedni wygenerowanych
dłutakiem ani ciągłej symulacji kolizji pełnych profili zębów. Zgodnie z bramką
§10 nie wolno przejść do SCAD ani zastępować tych dowodów atrapą geometryczną.

Surowe wyniki znajdują się w `tools/noncircular-oracle/results.json`.

## Wyniki potwierdzone

| Kształt | e₁ | k | naturalne nᵣ | oddychanie orbity |
|---|---:|---:|---:|---:|
| kwadrat | 0,03 | 1,000811 | 12,0390 | 0,0445% |
| kwadrat | 0,04 | 1,001132 | 12,0545 | 0,0785% |
| kwadrat | 0,05 | 1,000342 | 12,0164 | 0,1214% |
| trójkąt | 0,04 | 1,000425 | 9,0153 | 0,0791% |
| trójkąt | 0,06 | 1,000676 | 9,0244 | 0,1755% |
| trójkąt | 0,08 | 1,001066 | 9,0385 | 0,3061% |

Wszystkie korekty spełniają `|k−1| ≤ 0,5%`, a oddychanie pozostaje poniżej 1%.
Domknięcie po korekcie ma residuum numeryczne poniżej `4e-16 rad`.

Dla `m=1`, `H=8,4 mm`: `H_min=7,2 mm`, pasy mają po `2,8 mm`, kanał
`0,6 mm`, rampa `2,2 mm`, a efektywny udział kontaktu po fazce wynosi 61,9%.
Wyliczone przesunięcia stopni: 0,3927 / 0,5031 / 0,6355 mm dla profili
Ciasny / Standardowy / Luźny. Półki wynoszą 0,356 / 0,456 / 0,576 mm i są
poniżej limitu 0,7 mm; margines blokady wynosi 0,15 mm.

## Niespełnione warunki GO

- brak jawnego modelu wirtualnego dłutaka i obwiedni S/P/R;
- brak testów podcięcia, grubości głowy i stopy dla powstałych zębów;
- brak testu odległości pełnych wielokątów planet co najwyżej co 1° cyklu;
- brak testu pustego przecięcia pełnych profili S–P i P–R poza strefą kontaktu;
- brak testów warstw przejściowych na rzeczywistych obwiedniach stopni.

To są kryteria 4–7e z §9.1, a nie opcjonalne ulepszenia. Zielone testy obecnego
oracle dotyczą wyłącznie zakresu, który faktycznie implementują.

## Następny krok

Rozbudować oracle o wielokąt dłutaka ewolwentowego, zamiatanie narzędzia,
ekstrakcję regularnej granicy obwiedni i testy kolizji na całym cyklu. Dopiero
gdy trzy widoczne wartości `e₁` dla obu kształtów przejdą tę siatkę, bramka może
zmienić się na GO.
