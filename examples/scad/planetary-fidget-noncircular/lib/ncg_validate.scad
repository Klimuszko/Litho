module ncg_validate(m,H,k,delta,backlash,pressure,band,channel_gap) {
    assert(m>=0.6 && m<=1.6,"Moduł zęba poza zakresem 0,6–1,6 mm");
    assert(abs(k-1)<=0.005,"Zmniejsz kanciastość: korekta pierścienia przekracza 0,5%");
    assert(H>=7.2,"Zwiększ grubość modelu albo wybierz drobniejsze zęby");
    assert(delta>=backlash/cos(pressure)+0.15,"Retencja osiowa jest niewystarczająca");
    assert(delta*cos(pressure)<=0.7,"Półka stopnia przekracza 0,7 mm");
    assert(band>=2.2,"Pas zębów jest za niski");
    assert(channel_gap>=0.8,"Kanał centralny jest zbyt ciasny");
    children();
}
