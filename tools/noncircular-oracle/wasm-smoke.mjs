import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import createOpenSCAD from "../../frontend/node_modules/@lofcz/openscad-wasm/openscad.js";

const require = createRequire(import.meta.url);
const wasmBytes = readFileSync(require.resolve("../../frontend/node_modules/@lofcz/openscad-wasm/openscad.wasm"));
const root = resolve(import.meta.dirname, "../../examples/scad/planetary-fidget-noncircular");
const instance = await createOpenSCAD({
  noInitialRun: true,
  instantiateWasm(imports, done) { WebAssembly.instantiate(wasmBytes, imports).then(r => done(r.instance)); return {}; },
  print: line => process.stdout.write(`${line}\n`),
  printErr: line => process.stderr.write(`${line}\n`),
});
instance.FS.mkdir("/module"); instance.FS.mkdir("/module/lib");
for (const file of ["main.scad", "lib/ncg_curves.scad", "lib/ncg_kinematics.scad", "lib/ncg_teeth.scad", "lib/ncg_axial.scad", "lib/ncg_validate.scad"])
  instance.FS.writeFile(`/module/${file}`, readFileSync(resolve(root, file)));
const shape = process.argv[2] ?? "0";
const outputMode = process.argv[3] ?? "4";
const fit = process.argv[4] ?? "1";
const code = instance.callMain(["/module/main.scad", "--backend", "Manifold", "--export-format", "binstl", `-Dshape=${shape}`, `-Doutput_mode=${outputMode}`, `-Dfit_profile=${fit}`, "-o", "/out.stl"]);
if (code !== 0) process.exit(code);
const bytes = instance.FS.readFile("/out.stl");
if (bytes.length <= 84) throw new Error("Pusty STL");
function stlComponents(data) {
  const view=new DataView(data.buffer,data.byteOffset,data.byteLength), triangles=view.getUint32(80,true), parent=Array.from({length:triangles},(_,i)=>i), owner=new Map();
  const find=x=>parent[x]===x?x:(parent[x]=find(parent[x]));
  const join=(a,b)=>{a=find(a);b=find(b);if(a!==b)parent[b]=a;};
  for(let t=0;t<triangles;t++) for(let v=0;v<3;v++) { const o=84+t*50+12+v*12; const key=`${view.getFloat32(o,true).toFixed(4)},${view.getFloat32(o+4,true).toFixed(4)},${view.getFloat32(o+8,true).toFixed(4)}`; if(owner.has(key))join(t,owner.get(key));else owner.set(key,t); }
  return new Set(parent.map((_,i)=>find(i))).size;
}
const components=stlComponents(bytes);
if(outputMode==="0" && components!==2+Number(shape=== "0" ? 4 : 3)) throw new Error(`Liczba brył ${components}, oczekiwano ${2+Number(shape==="0"?4:3)}`);
console.log(`WASM_OK shape=${shape} output=${outputMode} fit=${fit} bytes=${bytes.length} components=${components}`);
