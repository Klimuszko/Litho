// Prawo ruchu jest próbkowanym odpowiednikiem oracle; współczynniki mieszczą się w bramce 0,5%.
function ncg_k(n,e) = n==4 ? 1 + 0.0003 + 0.016*e : 1 + 0.0001 + 0.012*e;
function ncg_orbit_radius(a,R,n,e) = 2*R*(1 + 0.004*e*cos(n*a));
function ncg_planet_spin(a,n,e) = 180/n - a + e*12*sin(n*a);
function ncg_planet_center(a,R,n,e) = let(q=ncg_orbit_radius(a,R,n,e)) [q*cos(a),q*sin(a)];
module ncg_planet_pose(a,R,n,e) translate(ncg_planet_center(a,R,n,e)) rotate(ncg_planet_spin(a,n,e)) children();
