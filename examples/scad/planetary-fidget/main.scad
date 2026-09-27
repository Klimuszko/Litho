/*
 * Oficjalny moduł referencyjny Litho.
 * Platforma obsługuje go dokładnie tak samo jak każdy inny moduł SCAD.
 * Aplikacja nie zawiera żadnej logiki napisanej specjalnie dla tego fidgetu.
 */

/* [Główne] */
// Gotowa średnica zewnętrzna modelu. Każdy wzór obudowy mieści się w tym wymiarze.
outer_diameter = 60; // [40:1:100] @unit:mm @label:"Średnica zewnętrzna" @order:1
// Liczba kół planetarnych rozmieszczonych wokół koła centralnego.
planet_count = 8; // [3:1:12] @label:"Liczba planet" @order:2
// Drobne zęby dają więcej detali, a grube są łatwiejsze do wydrukowania.
tooth_style = 0; // [0:Drobne,1:Standardowe,2:Grube] @label:"Rodzaj zębów" @order:3
// Całkowita wysokość fidgetu.
gear_thickness = 8.0; // [5:0.5:15] @unit:mm @label:"Grubość modelu" @order:4

/* [Dopasowanie wydruku] */
// Wybierz luz odpowiedni dla dokładności drukarki i materiału.
print_fit = 1; // [0:Ciasne,1:Standardowe,2:Luźne] @label:"Luz elementów"

/* [Obudowa i otwory] */
// Maksymalna średnica zewnętrzna jest zachowana dla każdego wzoru.
outer_grip_style = 1; // [0:Gładka,1:Delikatne zagłębienia,2:Głębokie zagłębienia,3:Zaokrąglone wypustki,4:Płaskie fasety,5:Nacięcia V,6:Grupowe okrągłe,7:Grupowe V,8:Nacięcia naprzemienne] @label:"Kształt obudowy"
// Liczba zagłębień, wypustek albo faset dla wzorów regularnych.
grip_count = 18; // [6:1:40] @label:"Liczba elementów wzoru"
// Jak głęboko wzór wchodzi w obudowę. Generator chroni minimalną grubość ścianki.
grip_depth = 1.2; // [0.2:0.1:2.4] @unit:mm @label:"Głębokość wzoru"
// Szerokość pojedynczego zagłębienia albo wypustki.
grip_width = 3.2; // [1.2:0.2:7] @unit:mm @label:"Szerokość wzoru"
// Obrót całego wzoru pozwala ustawić zagłębienia względem planet.
grip_phase = 0; // [-15:1:15] @unit:° @label:"Obrót wzoru"
// Średnica otworu na palec w kole centralnym.
finger_hole = 18; // [12:1:26] @unit:mm @label:"Średnica otworu na palec"
// Włącza otwory odciążające w kołach planetarnych.
planet_holes = true; // @label:"Otwory w planetach"
planet_hole_size = 4.0; // [2:0.5:8] @unit:mm @label:"Średnica otworów w planetach"

/* [Nacięcia grupowe] */
// Ustawienia używane przez oba warianty grupowe.
grip_group_count = 6; // [3:1:16] @label:"Liczba grup"
grip_group_size = 3; // [1:1:6] @label:"Nacięcia w grupie"
grip_group_spread = 4.0; // [1:0.5:10] @unit:° @label:"Odstęp w grupie"

/* [Zaawansowane] */
pressure_angle = 20; // [14:1:30] @unit:° @advanced @label:"Kąt przyporu"
helix_angle = 0; // [0:1:30] @unit:° @advanced @label:"Kąt skręcenia zębów"
quality = 80; // [32:8:160] @advanced @label:"Jakość krzywizn"
mode = "model"; // [model,metadata] @hidden

function tooth_module(style) = style == 0 ? 0.78 : style == 2 ? 1.18 : 0.96;
function clearance(fit) = fit == 0 ? 0.18 : fit == 2 ? 0.42 : 0.28;
function is_valid_sun(ring, sun, planets) = ((ring - sun) % 2 == 0) && ((ring + sun) % planets == 0);
function find_sun(ring, planets, sun = 9) = sun >= ring - 8 ? 9 : (is_valid_sun(ring, sun, planets) ? sun : find_sun(ring, planets, sun + 1));

module_size = tooth_module(tooth_style);
// Obręcz rezerwuje miejsce na wybrany wzór oraz co najmniej 1 mm pełnej ścianki.
wall = max(3.8, module_size * 2.4 + grip_depth + 1.0);
ring_teeth_guess = floor((outer_diameter - wall * 2) / module_size);
sun_teeth = find_sun(ring_teeth_guess, planet_count);
ring_teeth = ring_teeth_guess - ((ring_teeth_guess - sun_teeth) % 2);
planet_teeth = floor((ring_teeth - sun_teeth) / 2);
actual_module = (outer_diameter - wall * 2) / ring_teeth;
fit_gap = clearance(print_fit);
sun_pitch_r = sun_teeth * actual_module / 2;
planet_pitch_r = planet_teeth * actual_module / 2;
planet_orbit = sun_pitch_r + planet_pitch_r + fit_gap;
ring_root_r = ring_teeth * actual_module / 2 + actual_module * 0.72;
outer_radius = outer_diameter / 2;
minimum_rim_radius = ring_root_r + max(1.0, actual_module);
available_grip_depth = max(0, outer_radius - minimum_rim_radius);
safe_grip_depth = min(grip_depth, available_grip_depth);

echo(str("INFO:zęby_pierścienia=", ring_teeth));
echo(str("INFO:zęby_koła_centralnego=", sun_teeth));
echo(str("INFO:zęby_planety=", planet_teeth));
echo(str("INFO:moduł_zęba=", actual_module, " mm"));
echo(str("INFO:wzór_obudowy=", outer_grip_style));
echo(str("INFO:głębokość_wzoru=", safe_grip_depth, " mm"));
if (finger_hole > sun_pitch_r * 1.45) echo(str("WARNING:Otwór na palec został zmniejszony, aby zmieścił się w kole centralnym"));
if (grip_depth > available_grip_depth) echo(str("WARNING:Głębokość wzoru została zmniejszona, aby zachować bezpieczną grubość obudowy"));

module tooth_profile(teeth, pitch_r, internal = false) {
    tooth_h = actual_module * (internal ? 1.35 : 1.15);
    tooth_w = max(actual_module * 0.72, 2 * PI * pitch_r / teeth * 0.44);
    union() {
        circle(r = internal ? pitch_r - tooth_h * 0.2 : pitch_r - actual_module * 0.52, $fn = quality);
        for (i = [0 : teeth - 1])
            rotate(i * 360 / teeth)
                translate([pitch_r - (internal ? tooth_h * 0.38 : 0), 0])
                    square([tooth_h, tooth_w], center = true);
    }
}

module extruded_gear(teeth, pitch_r, hole = 0) {
    difference() {
        linear_extrude(height = gear_thickness, twist = helix_angle, slices = max(4, ceil(gear_thickness / 0.8)))
            tooth_profile(teeth, pitch_r);
        if (hole > 0) translate([0, 0, -1]) cylinder(d = hole, h = gear_thickness + 2, $fn = quality);
    }
}

// Okrągłe zagłębienie zaczynające się na obrysie i wchodzące do środka.
module round_recess_2d(angle, depth = safe_grip_depth, width = grip_width) {
    cutter_r = max(0.1, width / 2);
    rotate(angle)
        translate([outer_radius + cutter_r - depth, 0])
            circle(r = cutter_r, $fn = 28);
}

// Klinowe nacięcie w kształcie litery V.
module v_recess_2d(angle, depth = safe_grip_depth, width = grip_width) {
    rotate(angle)
        translate([outer_radius - depth, 0])
            polygon(points = [
                [0, -width / 2],
                [depth + 0.5, 0],
                [0, width / 2]
            ]);
}

module regular_round_recesses(depth_multiplier = 1) {
    for (i = [0 : grip_count - 1])
        round_recess_2d(
            grip_phase + i * 360 / grip_count,
            safe_grip_depth * depth_multiplier
        );
}

module regular_v_recesses() {
    for (i = [0 : grip_count - 1])
        v_recess_2d(grip_phase + i * 360 / grip_count);
}

module grouped_round_recesses() {
    for (group = [0 : grip_group_count - 1])
        for (member = [0 : grip_group_size - 1])
            round_recess_2d(
                grip_phase
                + group * 360 / grip_group_count
                + (member - (grip_group_size - 1) / 2) * grip_group_spread
            );
}

module grouped_v_recesses() {
    for (group = [0 : grip_group_count - 1])
        for (member = [0 : grip_group_size - 1])
            v_recess_2d(
                grip_phase
                + group * 360 / grip_group_count
                + (member - (grip_group_size - 1) / 2) * grip_group_spread
            );
}

module rounded_lobes_2d() {
    lobe_r = max(0.6, grip_width / 2);
    core_r = max(minimum_rim_radius, outer_radius - min(safe_grip_depth, lobe_r * 0.8));
    union() {
        circle(r = core_r, $fn = quality * 2);
        for (i = [0 : grip_count - 1])
            rotate(grip_phase + i * 360 / grip_count)
                translate([outer_radius - lobe_r, 0])
                    circle(r = lobe_r, $fn = 28);
    }
}

module outer_grip_profile_2d() {
    if (outer_grip_style == 0) {
        circle(r = outer_radius, $fn = quality * 2);
    } else if (outer_grip_style == 3) {
        rounded_lobes_2d();
    } else if (outer_grip_style == 4) {
        // Wielokąt wpisany w zadaną średnicę tworzy ergonomiczne płaskie powierzchnie.
        rotate(grip_phase)
            circle(r = outer_radius, $fn = max(6, grip_count));
    } else {
        difference() {
            circle(r = outer_radius, $fn = quality * 2);
            if (outer_grip_style == 1)
                regular_round_recesses(0.65);
            else if (outer_grip_style == 2)
                regular_round_recesses(1);
            else if (outer_grip_style == 5)
                regular_v_recesses();
            else if (outer_grip_style == 6)
                grouped_round_recesses();
            else if (outer_grip_style == 7)
                grouped_v_recesses();
            else if (outer_grip_style == 8)
                for (i = [0 : grip_count - 1])
                    if (i % 2 == 0)
                        round_recess_2d(grip_phase + i * 360 / grip_count);
                    else
                        v_recess_2d(
                            grip_phase + i * 360 / grip_count,
                            safe_grip_depth * 0.72,
                            grip_width * 0.8
                        );
        }
    }
}

module ring_gear() {
    difference() {
        linear_extrude(height = gear_thickness)
            outer_grip_profile_2d();
        translate([0, 0, -0.5])
            linear_extrude(height = gear_thickness + 1, twist = -helix_angle, slices = max(4, ceil(gear_thickness / 0.8)))
                offset(delta = fit_gap)
                    tooth_profile(ring_teeth, ring_root_r, true);
    }
}

module complete_fidget() {
    ring_gear();
    extruded_gear(sun_teeth, sun_pitch_r, min(finger_hole, sun_pitch_r * 1.45));
    for (i = [0 : planet_count - 1])
        rotate(i * 360 / planet_count)
            translate([planet_orbit, 0, 0])
                rotate(i * -360 * (sun_teeth / max(1, planet_teeth)) / planet_count)
                    extruded_gear(planet_teeth, planet_pitch_r, planet_holes ? min(planet_hole_size, planet_pitch_r) : 0);
}

if (mode == "model") complete_fidget();
