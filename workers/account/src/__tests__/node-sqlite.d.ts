// The slice of Node's built-in `node:sqlite` the credit-ledger test drives; this project's tsconfig loads workers types only, not @types/node.
declare module 'node:sqlite' {
  export class DatabaseSync {
    constructor(path: string);
    prepare(sql: string): { all(...bindings: unknown[]): Record<string, unknown>[] };
  }
}
