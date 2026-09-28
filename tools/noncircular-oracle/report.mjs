import { evaluateCase } from "./oracle.mjs";
import { writeFileSync } from "node:fs";
const configs = [
  ...[0.03, 0.04, 0.05].map(e1 => ({ shape: "kwadrat", lobes: 4, e1 })),
  ...[0.04, 0.06, 0.08].map(e1 => ({ shape: "trójkąt", lobes: 3, e1 })),
];
const json = JSON.stringify(configs.map(c => ({ ...c, ...evaluateCase({ ...c, samples: 4096 }) })), null, 2) + "\n";
if (process.argv[2]) writeFileSync(process.argv[2], json, "utf8"); else process.stdout.write(json);
