/*
  Litho — otwarty planetarny fidget print-in-place

  Model jest drukowany jako jeden element, bez montażu i podpór.
  Obie strony pozostają całkowicie otwarte — bez koszyka, mostka i płyt.
  Widoczne elementy ruchome to pierścień zewnętrzny, koło centralne i planety.
  Podwójnie skośne zęby ewolwentowe utrzymują przekładnię w osi.

  Zalecany pierwszy wydruk:
  PLA: luz standardowy, warstwa 0,20 mm, 3 obrysy, bez podpór.
  PETG: luz luźny, jeśli drukarka skleja mechanizmy print-in-place.

  Model należy drukować płasko, dokładnie w wygenerowanej orientacji.
*/

/* [Główne] */
// Wybierz kompletny mechanizm, podgląd albo pojedynczy element.
output_mode = 0; // [0:Kompletny print-in-place,1:Kolorowy podgląd mechanizmu,2:Tylko pierścień,3:Tylko koło centralne,4:Jedna planeta] @label:"Generowany element"

// Gotowa maksymalna średnica zewnętrzna modelu.
outer_diameter = 60; // [45:1:110] @unit:mm @label:"Średnica zewnętrzna"

// Liczba planet. Generator automatycznie dobiera prawidłową liczbę zębów.
planet_count = 6; // [3:1:12] @label:"Liczba planet"

// Drobne zęby dają więcej detali, grube są łatwiejsze do wydrukowania.
tooth_style = 1; // [0:Drobne,1:Standardowe,2:Grube] @label:"Rodzaj zębów"

// Całkowita wysokość fidgetu.
gear_thickness = 8.0; // [6:0.2:14] @unit:mm @label:"Grubość modelu"

/* [Dopasowanie wydruku] */
// Luz roboczy pomiędzy wszystkimi ruchomymi elementami.
fit_profile = 1; // [0:Ciasny,1:Standardowy,2:Luźny] @label:"Luz elementów"

/* [Obudowa i otwory] */
// Średnica otworu na palec w kole centralnym.
finger_hole_diameter = 22; // [16:1:28] @unit:mm @label:"Średnica otworu na palec"

// Włącza okrągłe otwory odciążające w planetach.
planet_holes = true; // @label:"Otwory w planetach"

// Wielkość otworów jako procent dostępnej średnicy u podstawy zębów.
planet_hole_percent = 52; // [30:1:68] @unit:% @label:"Wielkość otworów w planetach"

// Kształt zewnętrznej obudowy. Trzy pierwsze warianty to klasyczne wzory Litho.
grip_style = 0; // [0:Delikatne zagłębienia,1:Głębokie zagłębienia,2:Grupowe okrągłe,3:Zaokrąglone segmenty,4:Kanciaste segmenty,5:Segmenty z oknami,6:Zewnętrzne ząbki,7:Korona trójkątna,8:Sześciokąt techniczny] @label:"Kształt obudowy"

// Liczba zagłębień, wypustek albo faset dla wzorów regularnych.
grip_count = 18; // [8:1:40] @label:"Liczba zagłębień lub ząbków"

// Głębokość wzoru. Wartość jest automatycznie ograniczana dla ochrony ścianki.
grip_depth = 1.2; // [0.2:0.1:2.0] @unit:mm @label:"Głębokość wzoru"

// Szerokość pojedynczego zagłębienia albo wypustki.
grip_width = 3.2; // [1.2:0.2:7] @unit:mm @label:"Szerokość wzoru"

// Obrót całego wzoru względem położenia planet.
grip_phase = 0; // [-15:1:15] @unit:° @label:"Obrót wzoru"

/* [Obudowy segmentowe] */
// Liczba dużych segmentów dla obudów inspirowanych przedstawionymi modelami.
segment_count = 10; // [6:1:16] @label:"Liczba segmentów"

// Wielkość otworów w wariancie „Segmenty z oknami”.
segment_window_percent = 58; // [35:1:72] @unit:% @label:"Wielkość okien"

// Zaokrąglenie narożników okien i sześciokątnej obudowy.
housing_rounding = 0.8; // [0.2:0.1:1.8] @unit:mm @label:"Zaokrąglenie obudowy"

/* [Nacięcia grupowe] */
// Liczba grup rozłożonych równomiernie na obwodzie.
grip_group_count = 6; // [3:1:16] @label:"Liczba grup"

// Liczba nacięć znajdujących się w każdej grupie.
grip_group_size = 3; // [1:1:6] @label:"Nacięcia w grupie"

// Kątowy odstęp pomiędzy nacięciami w jednej grupie.
grip_group_spread = 4.0; // [1:0.5:10] @unit:° @label:"Odstęp w grupie"

/* [Zaawansowane] */
// Kąt podwójnie skośnych zębów. Zakres 24–30° dobrze sprawdza się w FDM.
helix_angle = 26; // [20:1:32] @unit:° @advanced @label:"Kąt skręcenia zębów"

// Szerokość pełnego materiału na zewnątrz zębów pierścienia.
ring_rim = 3.8; // [3.0:0.2:8.5] @unit:mm @advanced @label:"Minimalna szerokość obręczy"

/* [Ukryte] */
PI_ = 3.14159265358979323846;
pressure_angle = 25;
round_fn = 72;
involute_steps = 10;

// Ustawienia luzów dla druku FDM.
mesh_backlash = fit_profile == 0 ? 0.22 : fit_profile == 1 ? 0.32 : 0.44;
extra_tip_clearance = fit_profile == 0 ? 0.08 : fit_profile == 1 ? 0.14 : 0.22;
planet_spacing_clearance = fit_profile == 0 ? 0.25 : fit_profile == 1 ? 0.40 : 0.58;

// Docelowy moduł służy wyłącznie solverowi.
target_module = tooth_style == 0 ? 0.72 : tooth_style == 1 ? 0.95 : 1.20;
min_sun_wall = 1.20;
min_grip_wall = 1.8;

// Rozbudowane obudowy potrzebują szerszej obręczy. Solver uwzględnia ją
// przed doborem zębów, dzięki czemu ozdoby nigdy nie przecinają przekładni.
function required_ring_rim(style) =
    style == 3 ? 4.8 :
    style == 4 ? 5.4 :
    style == 5 ? 7.2 :
    style == 6 ? 4.6 :
    style == 7 ? 5.0 :
    style == 8 ? 8.0 : 3.8;
effective_ring_rim = max(ring_rim, required_ring_rim(grip_style));

// ---------- automatyczny dobór przekładni ----------
function rad_to_deg(x) = x * 180 / PI_;
function solved_module(d, zr) = (d - 2*effective_ring_rim - 2*extra_tip_clearance) / (zr + 2.5);
function phase_valid(zs, zr, n) = ((zs + zr) % n) == 0;
function spacing_margin(zs, zp, m, n) =
    m*(zs + zp)*sin(180/n) - (m*(zp + 2) + planet_spacing_clearance);
function candidate_score(zs, zp, zr, m) =
    abs(m - target_module)*120
    + abs(zp - 11)*1.35
    + abs(zs - 20)*0.30
    + (m < 0.62 ? 1800 : 0)
    + (m > 1.95 ? 1800 : 0);
function best_candidate_index(v, i=1, b=0) =
    i >= len(v) ? b : best_candidate_index(v, i + 1, (v[i][0] < v[b][0]) ? i : b);

gear_candidates = [
    for (zs = [14:64])
        for (zp = [6:28])
            let(
                zr = zs + 2*zp,
                m = solved_module(outer_diameter, zr),
                margin = spacing_margin(zs, zp, m, planet_count),
                score = candidate_score(zs, zp, zr, m)
            )
            if (phase_valid(zs, zr, planet_count)
                && m >= 0.50 && m <= 2.00
                && margin >= 0
                && (m*zs/2 - (1.25*m + extra_tip_clearance)) >= finger_hole_diameter/2 + min_sun_wall)
                [score, zs, zp, zr, m, margin]
];

solver_ok = len(gear_candidates) > 0;
best_candidate = solver_ok
    ? gear_candidates[best_candidate_index(gear_candidates)]
    : [0, 18, 12, 42, 1.0, 0];

sun_teeth = best_candidate[1];
planet_teeth = best_candidate[2];
ring_teeth = best_candidate[3];
module_mm = best_candidate[4];

sun_pitch_r = module_mm * sun_teeth / 2;
planet_pitch_r = module_mm * planet_teeth / 2;
ring_pitch_r = module_mm * ring_teeth / 2;
planet_center_r = sun_pitch_r + planet_pitch_r;

sun_outer_r = sun_pitch_r + module_mm;
planet_outer_r = planet_pitch_r + module_mm;
sun_root_r = max(0.20*module_mm, sun_pitch_r - (1.25*module_mm + extra_tip_clearance));
planet_root_r = max(0.20*module_mm, planet_pitch_r - (1.25*module_mm + extra_tip_clearance));
ring_tip_r = ring_pitch_r - module_mm;
ring_root_r = ring_pitch_r + 1.25*module_mm + extra_tip_clearance;
ring_outer_r = ring_root_r + effective_ring_rim;
actual_outer_d = 2*ring_outer_r;

planet_chord = 2 * planet_center_r * sin(180 / planet_count);
phase_ok = phase_valid(sun_teeth, ring_teeth, planet_count);
spacing_ok = planet_chord >= (2*planet_outer_r + planet_spacing_clearance);
hole_ok = finger_hole_diameter/2 <= sun_root_r - min_sun_wall;
planet_hole_diameter = planet_holes ? max(0, 2*planet_root_r*(planet_hole_percent/100)) : 0;
planet_hole_ok = !planet_holes || planet_hole_diameter/2 <= planet_root_r - 0.80;
geometry_ok = ring_tip_r > planet_outer_r*0.25 && module_mm > 0 && gear_thickness >= 6;
valid_model = solver_ok && phase_ok && spacing_ok && hole_ok && planet_hole_ok && geometry_ok;

available_grip_depth = max(0, ring_outer_r - (ring_root_r + min_grip_wall));
safe_grip_depth = min(grip_depth, available_grip_depth);
housing_core_r = ring_root_r + min_grip_wall;
decorative_span = ring_outer_r - housing_core_r;

$fn = round_fn;

// ---------- funkcje matematyczne ----------
function involute_intersect_angle(rb, r) = r <= rb ? 0 : rad_to_deg(sqrt((r/rb)*(r/rb) - 1));
function involute_xy(rb, a_deg) =
    let(t = a_deg * PI_ / 180)
    [
        rb * (cos(a_deg) + t * sin(a_deg)),
        rb * (sin(a_deg) - t * cos(a_deg))
    ];
function rotpt(a, p) = [cos(a)*p[0] + sin(a)*p[1], cos(a)*p[1] - sin(a)*p[0]];
function mirror_y(p) = [p[0], -p[1]];
function ext_half_tooth_angle(z, rp, backlash_share) = 90/z - rad_to_deg(backlash_share/(2*rp));
function gap_half_tooth_angle(z, rp, backlash_share) = 90/z + rad_to_deg(backlash_share/(2*rp));
function planet_phase(theta, sun_rot) =
    theta + 180 - 180/planet_teeth + (sun_teeth/planet_teeth)*(theta - sun_rot);
function sun_assembly_phase() = (planet_teeth % 2 == 0) ? 180/sun_teeth : 0;
function helix_twist_deg(rp, h, beta) = rad_to_deg((h*tan(beta))/rp);

// ---------- ewolwentowe profile zębów ----------
module involute_tooth_segments(rp, rb, rf, ra, half_angle, steps=involute_steps) {
    min_r = max(rb, rf);
    start_a = involute_intersect_angle(rb, min_r);
    stop_a = involute_intersect_angle(rb, ra);
    pitch_pt = involute_xy(rb, involute_intersect_angle(rb, rp));
    pitch_a = atan2(pitch_pt[1], pitch_pt[0]);
    center_a = pitch_a + half_angle;

    for (s = [1:steps]) {
        a1 = start_a + (stop_a - start_a)*(s - 1)/steps;
        a2 = start_a + (stop_a - start_a)*s/steps;
        p1 = rotpt(center_a, involute_xy(rb, a1));
        p2 = rotpt(center_a, involute_xy(rb, a2));
        q1 = mirror_y(p1);
        q2 = mirror_y(p2);
        polygon(points = [[0,0], p1, p2, q2, q1]);
    }
}

module external_gear_2d(z, m, pa, backlash_share, extra_clear) {
    rp = m*z/2;
    rb = rp*cos(pa);
    ra = rp + m;
    rf = max(0.20*m, rp - (1.25*m + extra_clear));
    half_a = ext_half_tooth_angle(z, rp, backlash_share);

    union() {
        circle(r = rf*1.001, $fn = max(round_fn, z*4));
        for (i = [0:z - 1])
            rotate(i*360/z)
                involute_tooth_segments(rp, rb, rf, ra, half_a);
    }
}

module internal_gap_cutter_2d(z, m, pa, backlash_share, extra_clear) {
    rp = m*z/2;
    rb = rp*cos(pa);
    rtip = rp - m;
    rroot = rp + (1.25*m + extra_clear);
    half_gap = gap_half_tooth_angle(z, rp, backlash_share);

    union() {
        circle(r = rtip, $fn = max(round_fn, z*4));
        for (i = [0:z - 1])
            rotate(i*360/z)
                involute_tooth_segments(rp, rb, rtip, rroot, half_gap);
    }
}

// ---------- podwójnie skośne wyciągnięcie ----------
module herringbone_extrude_2d(rp, hand=1) {
    half_h = gear_thickness/2;
    tw = helix_twist_deg(rp, half_h, helix_angle) * hand;

    linear_extrude(
        height = half_h,
        twist = tw,
        slices = max(8, ceil(half_h/0.35)),
        convexity = 12
    )
        children();

    translate([0, 0, half_h])
        rotate([0, 0, tw])
            linear_extrude(
                height = half_h,
                twist = -tw,
                slices = max(8, ceil(half_h/0.35)),
                convexity = 12
            )
                children();
}

module herringbone_external_gear(z, hand=1, hole_d=0) {
    rp = module_mm*z/2;
    difference() {
        herringbone_extrude_2d(rp, hand)
            external_gear_2d(
                z,
                module_mm,
                pressure_angle,
                mesh_backlash/2,
                extra_tip_clearance
            );
        if (hole_d > 0)
            translate([0, 0, -0.1])
                cylinder(d = hole_d, h = gear_thickness + 0.2, $fn = round_fn);
    }
}

// ---------- projektant obudowy zewnętrznej ----------
module round_recess_2d(angle, depth=safe_grip_depth, width=grip_width) {
    cutter_r = max(0.1, width/2);
    rotate(angle)
        translate([ring_outer_r + cutter_r - depth, 0])
            circle(r = cutter_r, $fn = 28);
}

module regular_round_recesses(depth_multiplier=1) {
    for (i = [0:grip_count - 1])
        round_recess_2d(
            grip_phase + i*360/grip_count,
            safe_grip_depth*depth_multiplier
        );
}

module grouped_round_recesses() {
    for (group = [0:grip_group_count - 1])
        for (member = [0:grip_group_size - 1])
            round_recess_2d(
                grip_phase
                + group*360/grip_group_count
                + (member - (grip_group_size - 1)/2)*grip_group_spread
            );
}

module rounded_rectangle_2d(size_x, size_y, radius) {
    safe_radius = max(0.01, min(radius, min(size_x, size_y)/2 - 0.01));
    offset(r = safe_radius)
        square(
            [max(0.02, size_x - 2*safe_radius), max(0.02, size_y - 2*safe_radius)],
            center = true
        );
}

module rounded_segments_2d() {
    lobe_r = min(
        decorative_span*0.92,
        2*PI_*ring_outer_r/segment_count*0.34
    );
    union() {
        circle(r = housing_core_r, $fn = max(round_fn, ring_teeth*4));
        for (i = [0:segment_count - 1])
            rotate(grip_phase + i*360/segment_count)
                translate([ring_outer_r - lobe_r, 0])
                    circle(r = lobe_r, $fn = 28);
    }
}

module angular_segment_2d(angle) {
    inner_angle = 180/segment_count*0.55;
    outer_angle = 180/segment_count*0.78;
    rotate(angle)
        polygon(points = [
            [housing_core_r*cos(inner_angle), -housing_core_r*sin(inner_angle)],
            [ring_outer_r*cos(outer_angle), -ring_outer_r*sin(outer_angle)],
            [ring_outer_r*cos(outer_angle), ring_outer_r*sin(outer_angle)],
            [housing_core_r*cos(inner_angle), housing_core_r*sin(inner_angle)]
        ]);
}

module angular_segments_2d() {
    union() {
        circle(r = housing_core_r, $fn = max(round_fn, ring_teeth*4));
        for (i = [0:segment_count - 1])
            angular_segment_2d(grip_phase + i*360/segment_count);
    }
}

module segment_window_2d(angle) {
    radial_wall = 0.65;
    radial_size = max(0.4, decorative_span - 2*radial_wall);
    center_r = housing_core_r + radial_wall + radial_size/2;
    available_tangent = 2*center_r*tan(180/segment_count*0.52);
    tangent_size = max(0.8, available_tangent*segment_window_percent/100);
    rotate(angle)
        translate([center_r, 0])
            rounded_rectangle_2d(radial_size, tangent_size, housing_rounding);
}

module windowed_segments_2d() {
    difference() {
        angular_segments_2d();
        for (i = [0:segment_count - 1])
            segment_window_2d(grip_phase + i*360/segment_count);
    }
}

module radial_tooth_2d(angle) {
    root_r = max(housing_core_r, ring_outer_r - min(1.8, decorative_span));
    root_angle = 180/grip_count*0.62;
    tip_angle = 180/grip_count*0.28;
    rotate(angle)
        polygon(points = [
            [root_r*cos(root_angle), -root_r*sin(root_angle)],
            [ring_outer_r*cos(tip_angle), -ring_outer_r*sin(tip_angle)],
            [ring_outer_r*cos(tip_angle), ring_outer_r*sin(tip_angle)],
            [root_r*cos(root_angle), root_r*sin(root_angle)]
        ]);
}

module external_teeth_2d() {
    root_r = max(housing_core_r, ring_outer_r - min(1.8, decorative_span));
    union() {
        circle(r = root_r, $fn = max(round_fn, ring_teeth*4));
        for (i = [0:grip_count - 1])
            radial_tooth_2d(grip_phase + i*360/grip_count);
    }
}

module triangular_crown_2d() {
    base_r = max(housing_core_r, ring_outer_r - min(2.4, decorative_span));
    half_angle = 180/segment_count*0.58;
    union() {
        circle(r = base_r, $fn = max(round_fn, ring_teeth*4));
        for (i = [0:segment_count - 1])
            rotate(grip_phase + i*360/segment_count)
                polygon(points = [
                    [base_r*cos(half_angle), -base_r*sin(half_angle)],
                    [ring_outer_r, 0],
                    [base_r*cos(half_angle), base_r*sin(half_angle)]
                ]);
    }
}

module rounded_hexagon_2d() {
    corner = min(housing_rounding, 1.8);
    offset(r = corner)
        circle(r = ring_outer_r - corner, $fn = 6);
}

module technical_hexagon_2d() {
    corner = min(housing_rounding, 1.8);
    flat_r = (ring_outer_r - corner)*cos(30) + corner;
    radial_wall = 0.55;
    radial_size = max(0.45, flat_r - housing_core_r - 2*radial_wall);
    center_r = housing_core_r + radial_wall + radial_size/2;
    slot_tangent = max(0.7, center_r*0.075);
    slot_gap = slot_tangent*1.45;
    difference() {
        rounded_hexagon_2d();
        for (side = [0:5])
            for (slot = [-1:1])
                rotate(grip_phase + 30 + side*60)
                    translate([center_r, slot*slot_gap])
                        rounded_rectangle_2d(
                            radial_size,
                            slot_tangent,
                            min(housing_rounding, 0.45)
                        );
    }
}

module outer_grip_profile_2d() {
    if (grip_style == 0 || grip_style == 1 || grip_style == 2) {
        difference() {
            circle(r = ring_outer_r, $fn = max(round_fn, ring_teeth*4));
            if (grip_style == 0)
                regular_round_recesses(0.65);
            else if (grip_style == 1)
                regular_round_recesses(1);
            else
                grouped_round_recesses();
        }
    } else if (grip_style == 3)
        rounded_segments_2d();
    else if (grip_style == 4)
        angular_segments_2d();
    else if (grip_style == 5)
        windowed_segments_2d();
    else if (grip_style == 6)
        external_teeth_2d();
    else if (grip_style == 7)
        triangular_crown_2d();
    else
        technical_hexagon_2d();
}

module herringbone_ring() {
    rp = ring_pitch_r;
    half_h = gear_thickness/2;
    tw = helix_twist_deg(rp, half_h, helix_angle) * -1;

    difference() {
        linear_extrude(height = gear_thickness, convexity = 12)
            outer_grip_profile_2d();

        translate([0, 0, -0.05])
            linear_extrude(
                height = half_h + 0.10,
                twist = tw,
                slices = max(8, ceil(half_h/0.35)),
                convexity = 14
            )
                internal_gap_cutter_2d(
                    ring_teeth,
                    module_mm,
                    pressure_angle,
                    mesh_backlash/2,
                    extra_tip_clearance
                );

        translate([0, 0, half_h - 0.05])
            rotate([0, 0, tw])
                linear_extrude(
                    height = half_h + 0.10,
                    twist = -tw,
                    slices = max(8, ceil(half_h/0.35)),
                    convexity = 14
                )
                    internal_gap_cutter_2d(
                        ring_teeth,
                        module_mm,
                        pressure_angle,
                        mesh_backlash/2,
                        extra_tip_clearance
                    );
    }
}

module sun_gear() {
    herringbone_external_gear(sun_teeth, +1, finger_hole_diameter);
}

module planet_gear() {
    herringbone_external_gear(planet_teeth, -1, planet_hole_diameter);
}

module ring_gear() {
    herringbone_ring();
}

// ---------- kompletny mechanizm print-in-place ----------
module moving_gears() {
    sun_rot = sun_assembly_phase();

    rotate([0, 0, sun_rot])
        sun_gear();

    for (i = [0:planet_count - 1]) {
        th = i*360/planet_count;
        pr = planet_phase(th, sun_rot);
        translate([planet_center_r*cos(th), planet_center_r*sin(th), 0])
            rotate([0, 0, pr])
                planet_gear();
    }

    ring_gear();
}

module print_in_place_complete() {
    moving_gears();
}

module mechanism_preview() {
    color([0.83, 0.83, 0.86])
        ring_gear();

    sun_rot = sun_assembly_phase();
    color([0.95, 0.58, 0.15])
        rotate([0, 0, sun_rot])
            sun_gear();

    for (i = [0:planet_count - 1]) {
        th = i*360/planet_count;
        pr = planet_phase(th, sun_rot);
        color([0.18, 0.55, 0.90])
            translate([planet_center_r*cos(th), planet_center_r*sin(th), 0])
                rotate([0, 0, pr])
                    planet_gear();
    }
}

// ---------- informacje i walidacja ----------
module validation_report() {
    echo(str("INFO:zęby_pierścienia=", ring_teeth));
    echo(str("INFO:zęby_koła_centralnego=", sun_teeth));
    echo(str("INFO:zęby_planety=", planet_teeth));
    echo(str("INFO:liczba_planet=", planet_count));
    echo(str("INFO:moduł_zęba=", module_mm, " mm"));
    echo(str("INFO:rzeczywista_średnica=", actual_outer_d, " mm"));
    echo(str("INFO:luz_zazębienia=", mesh_backlash, " mm"));
    echo(str("INFO:wariant_obudowy=", grip_style));
    echo(str("INFO:szerokość_obudowy=", effective_ring_rim, " mm"));
    echo(str("INFO:głębokość_wzoru=", safe_grip_depth, " mm"));
    if (grip_depth > available_grip_depth)
        echo("WARNING:Głębokość wzoru została zmniejszona, aby zachować bezpieczną grubość obręczy");
}

validation_report();

assert(
    solver_ok,
    "Nie znaleziono prawidłowego zestawu kół. Zwiększ średnicę zewnętrzną albo zmniejsz liczbę planet."
);
assert(phase_ok, "Błąd solvera: nieprawidłowe fazowanie przekładni.");
assert(spacing_ok, "Błąd solvera: planety nachodzą na siebie.");
assert(
    hole_ok,
    "Wybrany otwór na palec nie mieści się przy tej średnicy. Zwiększ średnicę zewnętrzną."
);
assert(
    planet_hole_ok,
    "Otwory w planetach są zbyt duże. Zmniejsz ich wielkość."
);
assert(geometry_ok, "Nieprawidłowa geometria. Zwiększ grubość albo średnicę modelu.");
assert(
    ext_half_tooth_angle(sun_teeth, sun_pitch_r, mesh_backlash/2) > 0,
    "Wybrany luz jest zbyt duży dla koła centralnego."
);
assert(
    ext_half_tooth_angle(planet_teeth, planet_pitch_r, mesh_backlash/2) > 0,
    "Wybrany luz jest zbyt duży dla planet."
);

// ---------- wybór generowanego elementu ----------
if (output_mode == 0)
    print_in_place_complete();
else if (output_mode == 1)
    mechanism_preview();
else if (output_mode == 2)
    ring_gear();
else if (output_mode == 3)
    sun_gear();
else if (output_mode == 4)
    planet_gear();
