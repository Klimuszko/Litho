function ncg_r(a, R, n, e1, e2=0) = R*(1 + e1*cos(n*a) + e2*cos(2*n*a));
function ncg_point(a, R, n, e1, e2=0, radial=0) = let(r=ncg_r(a,R,n,e1,e2)+radial) [r*cos(a),r*sin(a)];
function ncg_points(R,n,e1,e2=0,radial=0,samples=180,phase=0) =
    [for(i=[0:samples-1]) ncg_point(phase+360*i/samples,R,n,e1,e2,radial)];
function ncg_sum(v,i=0,a=0) = i>=len(v) ? a : ncg_sum(v,i+1,a+v[i]);
function ncg_perimeter(R,n,e1,e2=0,samples=720) =
    ncg_sum([for(i=[0:samples-1]) norm(ncg_point(360*(i+1)/samples,R,n,e1,e2)-ncg_point(360*i/samples,R,n,e1,e2))]);
module ncg_blank(R,n,e1,e2=0,radial=0,samples=180,phase=0) polygon(ncg_points(R,n,e1,e2,radial,samples,phase));
