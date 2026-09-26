/*
 * Litho reference module. The platform treats this like every other SCAD module;
 * no planetary-specific code exists in the application.
 */

/* [Main] */
outer_diameter = 60; // [40:1:100] @unit:mm @label:"Outer diameter" @order:1
planet_count = 8; // [3:1:12] @label:"Planet count" @order:2
tooth_style = "Fine"; // [Fine,Standard,Chunky] @label:"Tooth style" @order:3
gear_thickness = 8; // [5:0.5:15] @unit:mm @label:"Gear thickness" @order:4

/* [Print fit] */
print_fit = "Standard"; // [Tight,Standard,Loose] @label:"Print fit"

/* [Grip & holes] */
outer_grip_style = "Scalloped"; // [Smooth,Scalloped,Knurled] @label:"Outer grip"
grip_count = 16; // [8:1:32] @label:"Grip count"
finger_hole = 18; // [12:1:26] @unit:mm @label:"Finger hole diameter"
planet_holes = true; // @label:"Planet holes"
planet_hole_size = 4; // [2:0.5:8] @unit:mm @label:"Planet hole size"

/* [Advanced] */
pressure_angle = 20; // [14:1:30] @unit:deg @advanced @label:"Pressure angle"
helix_angle = 0; // [0:1:30] @unit:deg @advanced @label:"Helix angle"
quality = 80; // [32:8:160] @advanced @label:"Curve quality"
mode = "model"; // [model,metadata] @hidden

function tooth_module(style) = style == "Fine" ? 0.78 : style == "Chunky" ? 1.18 : 0.96;
function clearance(fit) = fit == "Tight" ? 0.18 : fit == "Loose" ? 0.42 : 0.28;
function is_valid_sun(ring, sun, planets) = ((ring - sun) % 2 == 0) && ((ring + sun) % planets == 0);
function find_sun(ring, planets, sun = 9) = sun >= ring - 8 ? 9 : (is_valid_sun(ring, sun, planets) ? sun : find_sun(ring, planets, sun + 1));

module_size = tooth_module(tooth_style);
wall = max(2.2, module_size * 2.4);
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

echo(str("INFO:ring_teeth=", ring_teeth));
echo(str("INFO:sun_teeth=", sun_teeth));
echo(str("INFO:planet_teeth=", planet_teeth));
echo(str("INFO:module=", actual_module));
if (finger_hole > sun_pitch_r * 1.45) echo(str("WARNING:Finger hole reduced to fit the sun gear"));

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

module outer_grips() {
    if (outer_grip_style != "Smooth")
        for (i = [0 : grip_count - 1]) rotate(i * 360 / grip_count)
            translate([outer_diameter / 2 - 0.5, 0, gear_thickness / 2])
                cylinder(r = outer_grip_style == "Knurled" ? 0.75 : 1.2, h = gear_thickness, center = true, $fn = 12);
}

module ring_gear() {
    difference() {
        union() {
            cylinder(d = outer_diameter, h = gear_thickness, $fn = quality * 2);
            outer_grips();
        }
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
