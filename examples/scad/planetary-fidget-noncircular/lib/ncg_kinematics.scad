// The complete sampled kinematics are consumed by generate-scad-data.mjs.
// These values are oracle outputs for the two exposed, validated presets;
// no fitted motion formula is evaluated by OpenSCAD.
function ncg_k(n,e) = n==4 ? 1.0017736854536707 : 1.0008509383280697;
function ncg_mount_phase(n) = n==4 ? 135 : 120;
