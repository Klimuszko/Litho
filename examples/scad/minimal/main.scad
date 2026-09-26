/* [Main] */

width = 50; // [10:1:100] @unit:mm @label:"Width"
height = 20; // [5:1:50] @unit:mm @label:"Height"
rounded = true; // @label:"Rounded corners"

if (rounded) {
    minkowski() {
        cube([width - 4, height - 4, 2]);
        cylinder(r = 2, h = 1, $fn = 32);
    }
} else {
    cube([width, height, 3]);
}
