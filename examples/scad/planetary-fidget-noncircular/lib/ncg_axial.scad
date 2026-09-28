include <ncg_teeth.scad>

module ncg_slice(kind,z0,h,R,n,e,teeth,m,N,outer_r,backlash,phase,shrink=0) {
    translate([0,0,z0]) linear_extrude(height=h+0.01)
        offset(delta=-shrink) ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,phase);
}

module ncg_transition(kind,z0,h,R,n,e,teeth,m,N,outer_r,backlash,p0,p1) {
    translate([0,0,z0]) linear_extrude(height=h+0.01) intersection() {
        ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,p0);
        ncg_profile(kind,R,n,e,teeth,m,N,outer_r,backlash,p1);
    }
}

module ncg_axial_body(kind,R,n,e,teeth,m,N,outer_r,backlash,H,delta,g_ax,recess,channel_h,ramp_h) {
    band=(H-channel_h-ramp_h)/2;
    step=(band-2*g_ax)/3;
    // dolny pas: od zewnątrz do kanału 2δ,δ,0; pierwsze 0,4 mm są zwężone.
    ncg_slice(kind,0,min(0.2,step),R,n,e,teeth,m,N,outer_r,backlash,2*delta,0.4);
    ncg_slice(kind,0.2,step-0.2,R,n,e,teeth,m,N,outer_r,backlash,2*delta,0.2);
    ncg_transition(kind,step,g_ax,R,n,e,teeth,m,N,outer_r,backlash,2*delta,delta);
    ncg_slice(kind,step+g_ax,step,R,n,e,teeth,m,N,outer_r,backlash,delta);
    ncg_transition(kind,2*step+g_ax,g_ax,R,n,e,teeth,m,N,outer_r,backlash,delta,0);
    ncg_slice(kind,2*step+2*g_ax,step,R,n,e,teeth,m,N,outer_r,backlash,0);
    // cofnięty kanał bez kontaktu.
    ncg_slice(kind,band,channel_h,R,n,e,teeth,m,N,outer_r,backlash,0,recess);
    // rampa 45° pod pasem górnym, warstwy 0,2 mm.
    for(j=[0:max(0,ceil(ramp_h/0.2)-1)]) let(h=min(0.2,ramp_h-j*0.2),d=max(0,recess*(1-(j+1)/max(1,ceil(ramp_h/0.2)))))
        ncg_slice(kind,band+channel_h+j*0.2,h,R,n,e,teeth,m,N,outer_r,backlash,0,d);
    top=band+channel_h+ramp_h;
    ncg_slice(kind,top,step,R,n,e,teeth,m,N,outer_r,backlash,0);
    ncg_transition(kind,top+step,g_ax,R,n,e,teeth,m,N,outer_r,backlash,0,delta);
    ncg_slice(kind,top+step+g_ax,step,R,n,e,teeth,m,N,outer_r,backlash,delta);
    ncg_transition(kind,top+2*step+g_ax,g_ax,R,n,e,teeth,m,N,outer_r,backlash,delta,2*delta);
    ncg_slice(kind,top+2*step+2*g_ax,step,R,n,e,teeth,m,N,outer_r,backlash,2*delta);
}
