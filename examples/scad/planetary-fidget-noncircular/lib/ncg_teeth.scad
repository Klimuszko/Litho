include <ncg_curves.scad>
include <ncg_kinematics.scad>

function ncg_inv(phi)=tan(phi)-phi*PI/180;
function ncg_flank_r(rb,phi)=rb/cos(phi);
function ncg_flank_a(z,alpha,phi,side)=side*(90/z + ncg_inv(alpha)*180/PI - ncg_inv(phi)*180/PI);

// Jawny zewnętrzny dłutak ewolwentowy: addendum=m, dedendum=1,25m.
module ncg_involute_shaper(m,alpha=25,zc=12,flank_samples=5) {
    rp=zc*m/2; rb=rp*cos(alpha); ra=rp+m; rf=rp-1.25*m; phi_a=acos(rb/ra);
    union() {
        circle(r=rf,$fn=zc*6);
        for(t=[0:zc-1]) rotate(360*t/zc) polygon(concat(
            [[rf*cos(-90/zc),rf*sin(-90/zc)]],
            [for(i=[0:flank_samples]) let(phi=phi_a*i/flank_samples,r=ncg_flank_r(rb,phi),a=ncg_flank_a(zc,alpha,phi,-1)) [r*cos(a),r*sin(a)]],
            [for(i=[flank_samples:-1:0]) let(phi=phi_a*i/flank_samples,r=ncg_flank_r(rb,phi),a=ncg_flank_a(zc,alpha,phi,1)) [r*cos(a),r*sin(a)]],
            [[rf*cos(90/zc),rf*sin(90/zc)]]));
    }
}

// Planeta jest blankiem pomniejszonym o sumę pozycji dłutaka toczącego się po centroidzie.
module ncg_planet_profile(R,n,e,z,m,phase=0,samples=0) {
    poses=12; rp_c=6*m; perimeter=ncg_perimeter(R,n,e,0,360);
    difference() {
        ncg_blank(R,n,e,0,1.05*m,max(180,z*8),phase/n);
        union() for(i=[0:poses-1]) let(a=360*i/poses,p=ncg_point(a,R,n,e),u=p/norm(p),c=p+u*rp_c,roll=-360*(perimeter*i/poses)/(2*PI*rp_c))
            translate(c) rotate(a+90+roll+phase/z) ncg_involute_shaper(m,25,12,4);
    }
}

// S i R są obwiedniami tej samej planety-narzędzia w dwóch ruchach względnych.
module ncg_sun_profile(R,n,e,z,m,backlash=0.32,phase=0) difference() {
    ncg_blank(R,n,e,0,1.1*m,max(180,z*8),180/n);
    union() for(i=[0:n-1]) let(a=360*i/n,c=ncg_planet_center(a,R,n,e),b=ncg_planet_spin(a,n,e))
        translate(c) rotate(b) offset(delta=backlash/2) ncg_planet_profile(R,n,e,z,m,phase);
}

module ncg_ring_profile(R,n,e,z,m,N,outer_r,backlash=0.32,phase=0) difference() {
    circle(r=outer_r,$fn=240);
    union() for(i=[0:n-1]) let(a=360*i/n,chi=ncg_k(n,e)*a*(1+2/n),c=ncg_planet_center(a,R,n,e),b=ncg_planet_spin(a,n,e))
        rotate(-chi) translate(c) rotate(b) offset(delta=backlash/2) ncg_planet_profile(R,n,e,z,m,phase);
}

module ncg_profile(kind,R,n,e,z,m,N,outer_r,backlash,phase=0) {
    if(kind==0) ncg_sun_profile(R,n,e,z,m,backlash,phase);
    else if(kind==1) ncg_planet_profile(R,n,e,z,m,phase);
    else ncg_ring_profile(R,n,e,z,m,N,outer_r,backlash,phase);
}
