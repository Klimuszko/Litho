/// <reference lib="webworker" />
import createOpenSCAD from "@lofcz/openscad-wasm";
import {unzipSync} from "fflate";
import {buildScadDefinitions, WasmParameter} from "./scadWasm";

type RenderRequest = {
  archive: ArrayBuffer;
  entryFile: string;
  outputFormat: "stl" | "3mf";
  parameters: WasmParameter[];
  values: Record<string, unknown>;
};

const worker = self as unknown as DedicatedWorkerGlobalScope;

function safePath(path: string): string {
  const normalized = path.replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized || normalized.split("/").some(part => !part || part === "." || part === "..")) {
    throw new Error(`Niedozwolona ścieżka w module: ${path}`);
  }
  return normalized;
}

function createDirectories(fs: {mkdir(path: string): void}, filePath: string) {
  const parts = filePath.split("/").slice(0, -1);
  let current = "";
  for (const part of parts) {
    current += `/${part}`;
    try { fs.mkdir(current); } catch { /* katalog już istnieje */ }
  }
}

function friendlyError(log: string): string {
  const text = log.toLowerCase();
  if (text.includes("can't open include file") || text.includes("can't open library")) return "Brakuje biblioteki wymaganej przez moduł.";
  if (text.includes("parser error") || text.includes("syntax error")) return "Plik SCAD zawiera błąd składni.";
  if (text.includes("assert")) return "Wybrane parametry tworzą nieprawidłową geometrię.";
  return "Model nie mógł zostać wygenerowany dla wybranych parametrów.";
}

worker.onmessage = async (event: MessageEvent<RenderRequest>) => {
  const started = performance.now();
  const stdout: string[] = [];
  const stderr: string[] = [];
  try {
    worker.postMessage({type: "progress", stage: "engine"});
    const instance = await createOpenSCAD({
      noInitialRun: true,
      print: text => stdout.push(text),
      printErr: text => stderr.push(text),
    });
    const files = unzipSync(new Uint8Array(event.data.archive));
    for (const [rawPath, contents] of Object.entries(files)) {
      const path = safePath(rawPath);
      const target = `/module/${path}`;
      createDirectories(instance.FS, target);
      instance.FS.writeFile(target, contents);
    }
    const entry = `/module/${safePath(event.data.entryFile)}`;
    const output = `/output.${event.data.outputFormat}`;
    const args = [
      entry,
      "--backend", "Manifold",
      "--export-format", event.data.outputFormat === "stl" ? "binstl" : "3mf",
      ...buildScadDefinitions(event.data.parameters, event.data.values),
      "-o", output,
    ];
    worker.postMessage({type: "progress", stage: "render"});
    const exitCode = instance.callMain(args);
    if (exitCode !== 0) throw new Error(friendlyError(`${stdout.join("\n")}\n${stderr.join("\n")}`));
    const result = instance.FS.readFile(output, {encoding: "binary"});
    const transferable = result.buffer.slice(result.byteOffset, result.byteOffset + result.byteLength);
    worker.postMessage({
      type: "complete",
      output: transferable,
      stdout: stdout.join("\n"),
      stderr: stderr.join("\n"),
      command: args,
      durationSeconds: (performance.now() - started) / 1000,
    }, [transferable]);
  } catch (reason) {
    const details = reason instanceof Error ? reason.message : String(reason);
    worker.postMessage({
      type: "error",
      message: details || friendlyError(stderr.join("\n")),
      stdout: stdout.join("\n"),
      stderr: stderr.join("\n"),
      durationSeconds: (performance.now() - started) / 1000,
    });
  }
};

