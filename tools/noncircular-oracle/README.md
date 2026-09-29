# Numeryczny oracle kół nieokrągłych

Uruchomienie w tym katalogu: `npm install`, `npm test` oraz
`node geometry-report.mjs geometry-results.json`.

Oracle wylicza i weryfikuje profile źródłowe. Skrypt
`generate-scad-data.mjs` zapisuje zatwierdzone, dyskretne warianty w
`lib/ncg_profiles.scad`. Testy sprawdzają je ponownie na niezależnej siatce 64
pozycji na podziałkę i kontrolują błąd radializacji. W czasie używania modułu
oracle nie jest uruchamiany: `wasm-smoke.mjs` korzysta dokładnie z pakietu
OpenSCAD WebAssembly używanego przez browserowy worker, bez renderowania
serwerowego.
