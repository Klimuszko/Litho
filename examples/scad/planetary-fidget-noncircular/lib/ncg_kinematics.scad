// The complete sampled kinematics are consumed by generate-scad-data.mjs.
// These values are oracle outputs for the two exposed, validated presets;
// no fitted motion formula is evaluated by OpenSCAD.
function ncg_k(n) = n==4 ? 1.0002210926689508 : 1.0008511928158603;
function ncg_mount_center(n) = n==4 ? [25.6102188446,0.0249009700] : [25.4088960687,0.0231061758];
function ncg_mount_phase(n) = n==4 ? -224.8837882353 : -239.8903666160;
