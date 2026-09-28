import { writeFileSync } from "node:fs";
import { axialDesign, FITS } from "./oracle.mjs";
import { boundaryMetrics, generateMechanism, validateAxialProfiles, validateCycle } from "./geometry.mjs";

const cases = [...[.03,.04,.05].map(e1=>({shape:"kwadrat",lobes:4,e1})), ...[.04,.06,.08].map(e1=>({shape:"trójkąt",lobes:3,e1}))];
const rows = cases.map(c => {
  const mech = generateMechanism({...c,radius:12,module:1,posesPerPitch:4});
  const cycle = validateCycle(mech);
  return {...c, teeth:mech.planet.teeth,module:mech.planet.module,k:mech.kin.k,
    shaper:{teeth:mech.planet.shaper.teeth,undercutFree:mech.planet.shaper.undercutFree,tipThickness:mech.planet.shaper.tipThickness,rootThickness:mech.planet.shaper.rootThickness},
    boundary:{planet:boundaryMetrics(mech.planet.polygon,mech.planet.module),sun:boundaryMetrics(mech.sun,mech.planet.module),ring:boundaryMetrics(mech.ring,mech.planet.module)},cycle,
    axial:FITS.map(f=>{const a=axialDesign(mech.planet.module,f,8.4),p=validateAxialProfiles(mech,a.delta);return {fit:f.name,delta:a.delta,valid:a.valid&&p.valid,transitionAreas:p.transitionAreas,channelArea:p.channelArea};})};
});
const out=JSON.stringify(rows,null,2)+"\n";
if(process.argv[2]) writeFileSync(process.argv[2],out,"utf8"); else process.stdout.write(out);
