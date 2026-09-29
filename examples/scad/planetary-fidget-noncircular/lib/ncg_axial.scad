include <ncg_teeth.scad>

module ncg_slice(kind,z0,h,R,n,e,teeth,m,N,outer_r,backlash,phase,shrink=0) {
    translate([0,0,z0]) linear_extrude(height=h+0.01) {
        if(shrink>0) offset(delta=-shrink) ncg_profile_coarse(kind,R,n,e,teeth,m,N,outer_r,backlash,phase);
        else ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,phase);
    }
}

module ncg_transition(kind,z0,h,R,n,e,teeth,m,N,outer_r,backlash,p0,p1) {
    translate([0,0,z0]) linear_extrude(height=h+0.01) intersection() {
        ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,p0);
        ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,p1);
    }
}

module ncg_channel_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,phase,recess) {
    phase_index = phase < 0.25 ? 0 : phase < 0.75 ? 1 : 2;
    item = ncg_profiles[shape][fit_profile][phase_index][kind==0 ? 4 : kind==1 ? 3 : 5];
    if(kind==2) difference() {
        polygon(points=item[0],paths=[item[1][0]],convexity=20);
        polygon(points=item[0],paths=[item[1][1]],convexity=20);
    } else polygon(points=item[0],paths=item[1],convexity=20);
}

module ncg_channel_slice(kind,z0,h,R,n,e,teeth,m,N,outer_r,backlash,phase,recess) {
    translate([0,0,z0]) linear_extrude(height=h+0.01)
        ncg_channel_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,phase,recess);
}

module ncg_ramp(kind,z0,h,R,n,e,teeth,m,N,outer_r,backlash,phase,recess) {
    layers=round(h/0.2);
    for(j=[0:layers-1]) translate([0,0,z0+j*0.2]) linear_extrude(height=0.21)
        intersection() {
            ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,phase);
            offset(delta=(j+1)*0.2)
                ncg_channel_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,phase,recess);
        }
}

module ncg_axial_body(kind,R,n,e,teeth,m,N,outer_r,backlash,H,delta,g_ax,recess,channel_h,ramp_h) {
    band=(H-channel_h-ramp_h)/2;
    step0=floor((band-2*g_ax)/3/0.2)*0.2;
    step1=step0;
    step2=band-2*g_ax-step0-step1;
    // dolny pas: od zewnątrz do kanału 2δ,δ,0; pierwsze 0,4 mm są zwężone.
    ncg_slice(kind,0,min(0.2,step0),R,n,e,teeth,m,N,outer_r,backlash,2*delta,0.4);
    ncg_slice(kind,0.2,min(0.2,step0-0.2),R,n,e,teeth,m,N,outer_r,backlash,2*delta,0.2);
    ncg_slice(kind,0.4,step0-0.4,R,n,e,teeth,m,N,outer_r,backlash,2*delta);
    ncg_transition(kind,step0,g_ax,R,n,e,teeth,m,N,outer_r,backlash,2*delta,delta);
    ncg_slice(kind,step0+g_ax,step1,R,n,e,teeth,m,N,outer_r,backlash,delta);
    ncg_transition(kind,step0+step1+g_ax,g_ax,R,n,e,teeth,m,N,outer_r,backlash,delta,0);
    ncg_slice(kind,step0+step1+2*g_ax,step2,R,n,e,teeth,m,N,outer_r,backlash,0);
    // cofnięty kanał bez kontaktu.
    ncg_channel_slice(kind,band,channel_h,R,n,e,teeth,m,N,outer_r,backlash,0,recess);
    // Prawdziwa rampa łączy gładki rdzeń stopy z pasem zębatym.
    ncg_ramp(kind,band+channel_h,ramp_h,R,n,e,teeth,m,N,outer_r,backlash,0,recess);
    top=band+channel_h+ramp_h;
    ncg_slice(kind,top,step2,R,n,e,teeth,m,N,outer_r,backlash,0);
    ncg_transition(kind,top+step2,g_ax,R,n,e,teeth,m,N,outer_r,backlash,0,delta);
    ncg_slice(kind,top+step2+g_ax,step1,R,n,e,teeth,m,N,outer_r,backlash,delta);
    ncg_transition(kind,top+step2+step1+g_ax,g_ax,R,n,e,teeth,m,N,outer_r,backlash,delta,2*delta);
    ncg_slice(kind,top+step2+step1+2*g_ax,step0,R,n,e,teeth,m,N,outer_r,backlash,2*delta);
}
