include <ncg_profiles.scad>

// Profile data are generated from the independent JS oracle.  Index order is
// [shape][fit][arc phase 0/delta/2delta][planet/sun/ring].
module ncg_profile(kind,R,n,e,z,m,N,outer_r,backlash,phase=0) {
    phase_index = phase < 0.25 ? 0 : phase < 0.75 ? 1 : 2;
    item = ncg_profiles[shape][fit_profile][phase_index][kind==0 ? 1 : kind==1 ? 0 : 2];
    if(kind==2) difference() {
        polygon(points=item[0],paths=[item[1][0]],convexity=20);
        polygon(points=item[0],paths=[item[1][1]],convexity=20);
    } else polygon(points=item[0],paths=item[1],convexity=20);
}
