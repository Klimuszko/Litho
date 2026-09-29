# Fidget planetarny nieokrągły

Moduł zawiera wariant kwadratowy z czterema planetami i 12-płatowym pierścieniem
oraz trójkątny z trzema planetami i pierścieniem 9-płatowym. Obrót celowo
pulsuje, ponieważ chwilowe przełożenie prawdziwych kół nieokrągłych zmienia się
w cyklu.

Wersja 0.2 korzysta z sześciu zwalidowanych zestawów profili: dwóch kształtów
i trzech profili dopasowania. Profile zostały wcześniej wyliczone z pełnej
kinematyki i zapisane w module, dlatego przeglądarka nie musi numerycznie tworzyć
obwiedni przy każdym użyciu. Sam model STL/3MF nadal powstaje wyłącznie na
komputerze użytkownika w OpenSCAD WebAssembly; serwer nie wykonuje renderingu.
Średnica zewnętrzna wynosi w tej wersji 90 mm, a liczba planet jest częścią
zwalidowanej geometrii: cztery dla kwadratu i trzy dla trójkąta.

Zęby są podzielone na dolny i górny pas z trzema lustrzanymi stopniami. Pomiędzy
nimi znajduje się cofnięty kanał bez kontaktu, rampa pod pasem górnym, warstwy
przejściowe z luzem osiowym i fazka pierwszej warstwy. Użytkownik reguluje luz
wyłącznie profilem dopasowania; stałe kanału i retencji są ukryte.

Zalecany punkt startowy: PLA, warstwa 0,2 mm, trzy obrysy, bez podpór, profil
„Standardowy”. Sprawność fizyczna nie została potwierdzona: przed publikacją
należy wykonać F1–F11 z `docs/noncircular-physical-tests-protocol.pl.md`.
