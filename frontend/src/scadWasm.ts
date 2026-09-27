export type WasmParameter = {
  name: string;
  type: "integer" | "float" | "boolean" | "string" | "enum";
};

export function serializeScadValue(value: unknown, type: WasmParameter["type"]): string {
  if (type === "boolean") {
    if (typeof value !== "boolean") throw new Error("Oczekiwano wartości true/false");
    return value ? "true" : "false";
  }
  if (type === "integer") {
    if (typeof value !== "number" || !Number.isInteger(value)) throw new Error("Oczekiwano liczby całkowitej");
    return String(value);
  }
  if (type === "float") {
    if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("Oczekiwano liczby");
    return String(value);
  }
  if (type === "string" || type === "enum") {
    if (typeof value !== "string") throw new Error("Oczekiwano tekstu");
    return JSON.stringify(value);
  }
  throw new Error(`Nieobsługiwany typ parametru: ${type}`);
}

export function buildScadDefinitions(parameters: WasmParameter[], values: Record<string, unknown>, mode = "model"): string[] {
  const definitions = parameters
    .map(parameter => `-D${parameter.name}=${serializeScadValue(values[parameter.name], parameter.type)}`);
  if (!parameters.some(parameter => parameter.name === "mode")) definitions.push(`-Dmode=${JSON.stringify(mode)}`);
  return definitions;
}

