// Minimal declarations for the Node built-ins the tests use, so the project needs no @types/node.
declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
}
declare module "node:assert/strict" {
  const assert: {
    equal(actual: unknown, expected: unknown, message?: string): void;
    deepEqual(actual: unknown, expected: unknown, message?: string): void;
    ok(value: unknown, message?: string): void;
    throws(fn: () => unknown, expected?: RegExp | ((error: unknown) => boolean)): void;
    rejects(fn: () => Promise<unknown>, expected?: RegExp): Promise<void>;
  };
  export default assert;
}
declare module "node:fs" {
  export function readFileSync(path: string | URL, encoding: "utf-8"): string;
  export function readdirSync(path: string | URL): string[];
  export function statSync(path: string | URL): { isDirectory(): boolean };
}
declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}
