/** Offline import of generated models. Large binaries stay outside Git history. */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync, unlinkSync } from "node:fs";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_MODEL_BYTES = 25 * 1024 * 1024;
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");

/** Validate the GLB container and return the authored animation names. */
export function inspectGlb(bytes) {
  if (bytes.length < 20 || bytes.length > MAX_MODEL_BYTES || bytes.toString("ascii", 0, 4) !== "glTF" ||
      bytes.readUInt32LE(4) !== 2) throw new Error("Invalid GLB header or size");
  if (bytes.readUInt32LE(8) !== bytes.length) throw new Error("Invalid GLB length");
  let document;
  let offset = 12;
  let binaryLength = 0;
  while (offset < bytes.length) {
    if (offset + 8 > bytes.length) throw new Error("Invalid GLB chunk header");
    const length = bytes.readUInt32LE(offset);
    const kind = bytes.readUInt32LE(offset + 4);
    const end = offset + 8 + length;
    if (length % 4 !== 0 || end > bytes.length) throw new Error("Invalid GLB chunk length");
    if (offset === 12 && kind !== 0x4e4f534a) throw new Error("GLB first chunk must be JSON");
    if (kind === 0x4e4f534a) {
      if (document !== undefined) throw new Error("Duplicate GLB JSON chunk");
      document = JSON.parse(bytes.toString("utf8", offset + 8, end));
    } else if (kind === 0x004e4942) binaryLength += length;
    offset = end;
  }
  if (document?.asset?.version !== "2.0" || !document.meshes?.length || !document.scenes?.length) {
    throw new Error("GLB has no supported scene or mesh");
  }
  for (const item of [...(document.buffers ?? []), ...(document.images ?? [])]) {
    if (item.uri !== undefined && !item.uri.startsWith("data:")) {
      throw new Error("GLB references an external resource");
    }
  }
  const embeddedBytes = (document.buffers ?? []).filter((item) => item.uri === undefined)
    .reduce((total, item) => total + item.byteLength, 0);
  if (embeddedBytes > binaryLength) throw new Error("GLB binary chunk is truncated");
  return { clips: (document.animations ?? []).map((clip) => clip.name) };
}

/** Verify every source first; keep an existing different destination file intact. */
export function syncModels(models, source, destination) {
  if (!Array.isArray(models) || models.length === 0) throw new Error("Empty model manifest");
  const names = new Set();
  const checked = models.map((model) => {
    if (!/^[a-z0-9_]+\.glb$/.test(model.file) || names.has(model.file)) {
      throw new Error("Invalid or duplicate model file");
    }
    names.add(model.file);
    const bytes = readFileSync(join(source, model.file));
    if (hash(bytes) !== model.sha256) throw new Error(`Model hash mismatch: ${model.file}`);
    if (bytes.length !== model.bytes) throw new Error(`Model size mismatch: ${model.file}`);
    const metadata = inspectGlb(bytes);
    if (JSON.stringify(metadata.clips) !== JSON.stringify(model.clips)) {
      throw new Error(`Model clips mismatch: ${model.file}`);
    }
    const target = join(destination, model.file);
    const present = existsSync(target);
    if (present && hash(readFileSync(target)) !== model.sha256) {
      throw new Error(`Keep existing model intact: ${model.file}`);
    }
    return { bytes, target, present };
  });
  mkdirSync(destination, { recursive: true });
  for (const { bytes, target, present } of checked) {
    if (present) continue;
    const temporary = `${target}.import`;
    writeFileSync(temporary, bytes, { flag: "wx" });
    try { renameSync(temporary, target); }
    finally { if (existsSync(temporary)) unlinkSync(temporary); }
  }
  return checked.length;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== "--source") {
    console.error("Usage: npm run models:sync -- --source DIRECTORY");
    process.exitCode = 2;
  } else {
    try {
      const web = fileURLToPath(new URL("../", import.meta.url));
      const manifest = JSON.parse(readFileSync(join(web, "models.json"), "utf8"));
      const count = syncModels(manifest.models, resolve(args[1]), join(web, "public", "models"));
      console.info(`Verified ${count} models in web/public/models`);
    } catch (error) {
      console.error(error.message);
      process.exitCode = 1;
    }
  }
}
