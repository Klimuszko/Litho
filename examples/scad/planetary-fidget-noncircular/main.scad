include <lib/ncg_curves.scad>
include <lib/ncg_kinematics.scad>
include <lib/ncg_teeth.scad>
include <lib/ncg_axial.scad>
include <lib/ncg_validate.scad>

/* [Główne] */
output_mode = 0; // [0:Kompletny print-in-place,1:Kolorowy podgląd,2:Tylko pierścień,3:Tylko koło centralne,4:Jedna planeta] @label:Widok
shape = 0; // [0:Kwadratowy,1:Trójkątny] @label:Kształt
outer_diameter = 90; // [70:1:130] @label:Średnica zewnętrzna @unit:mm
squareness = 55; // [0:1:100] @label:Kanciastość @unit:%
tooth_style = 1; // [0:Drobne,1:Standardowe,2:Grube] @label:Rozmiar zębów
gear_thickness = 8.4; // [7:0.2:14] @label:Grubość @unit:mm

/* [Dopasowanie] */
fit_profile = 1; // [0:Ciasny,1:Standardowy,2:Luźny] @label:Profil dopasowania

/* [Otwory] */
finger_hole_diameter = 16; // [10:1:24] @label:Otwór na palec @unit:mm
planet_holes = true; // @label:Otwory w planetach
planet_hole_percent = 50; // [30:1:65] @label:Wielkość otworów planet @unit:%

/* [Obudowa] */
rim_style = 0; // [0:Równoległa do fali,1:Gładka okrągła] @label:Obręcz

/* [Zaawansowane] */
side_flatness = 0; // [0:1:100] @advanced @label:Spłaszczenie boków
pressure_angle = 25; // [20:1:25] @advanced @label:Kąt przyporu @unit:°

/* [Ukryte] */
curve_samples = 360;
envelope_samples = 8;
k_max = 0.005;
debug_section_z = -1;

n = shape==0 ? 4 : 3;
ring_lobes = 3*n;
N = n;
e_max = shape==0 ? 0.075 : 0.09;
e = e_max*squareness/100;
target_m = [0.8,1,1.25][tooth_style];
R = (outer_diameter/2-5)/(3*(1+e));
perimeter = ncg_perimeter(R,n,e,0,360);
teeth_per_lobe = max(3,round(perimeter/(n*PI*target_m)));
teeth = n*teeth_per_lobe;
m = perimeter/(PI*teeth);
backlash = [0.22,0.32,0.44][fit_profile];
tip_clearance = [0.08,0.14,0.22][fit_profile];
axial_gap = [0.2,0.2,0.3][fit_profile];
channel_gap = [0.8,1.0,1.2][fit_profile];
delta = backlash/cos(pressure_angle)+0.15;
recess = 0.5;
channel_h = 0.6;
ramp_h = ceil(max(0,2.25*m+tip_clearance+recess-0.8)/0.2)*0.2;
band_h = (gear_thickness-channel_h-ramp_h)/2;
outer_r = outer_diameter/2;
k = ncg_k(n,e);
safe_hole = min(finger_hole_diameter,2*(R*(1-e)-1.25*m-recess-1.4));

if(safe_hole<finger_hole_diameter) echo("WARNING: Otwór na palec został zmniejszony, aby zachować ściankę");
echo(str("INFO:kształt=",shape==0?"kwadrat":"trójkąt"));
echo(str("INFO:liczba_planet=",N));
echo(str("INFO:zęby_koła_centralnego=",teeth));
echo(str("INFO:zęby_planety=",teeth));
echo(str("INFO:zęby_pierścienia=",3*teeth));
echo(str("INFO:moduł_zęba=",m));
echo(str("INFO:korekta_pierścienia_k=",k));
echo(str("INFO:min_odstęp_planet=",2*R*(sqrt(2)-1-e)));
echo(str("INFO:pas_zębów=",band_h));
echo(str("INFO:kanał=",channel_h+ramp_h));
echo(str("INFO:cofnięcie_rdzenia=",recess));
echo(str("INFO:przesunięcie_stopnia_δ=",delta));
echo(str("INFO:luz_osiowy=",axial_gap));
echo(str("INFO:udział_kontaktu=",100*(2*band_h-0.4)/gear_thickness));
echo("WARNING: Sprawność fizyczna wymaga wykonania protokołu F1–F11");

module sun() difference() {
    ncg_axial_body(0,R,n,e,teeth,m,N,outer_r,backlash,gear_thickness,delta,axial_gap,recess,channel_h,ramp_h);
    translate([0,0,-0.1]) cylinder(d=max(1,safe_hole),h=gear_thickness+0.2,$fn=72);
}
module planet() difference() {
    ncg_axial_body(1,R,n,e,teeth,m,N,outer_r,backlash,gear_thickness,delta,axial_gap,recess,channel_h,ramp_h);
    if(planet_holes) translate([0,0,-0.1]) linear_extrude(height=gear_thickness+0.2)
        scale(planet_hole_percent/100) ncg_blank(R,n,e,0,-1.4,120,180/n);
}
module ring() ncg_axial_body(2,R,n,e,teeth,m,N,outer_r,backlash,gear_thickness,delta,axial_gap,recess,channel_h,ramp_h);
module planets() for(i=[0:N-1]) rotate(360*i/N) translate([2*R,0]) rotate(180/n) planet();
module assembly() {
    if(output_mode==1) { color("gold") sun(); color("steelblue") planets(); color("silver") ring(); }
    else { sun(); planets(); ring(); }
}

ncg_validate(m,gear_thickness,k,delta,backlash,pressure_angle,band_h,channel_gap)
if(debug_section_z>=0) projection(cut=true) translate([0,0,-debug_section_z]) assembly();
else if(output_mode==2) ring();
else if(output_mode==3) sun();
else if(output_mode==4) planet();
else assembly();
