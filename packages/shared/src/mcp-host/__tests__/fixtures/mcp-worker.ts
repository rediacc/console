/**
 * The shared MCP handler as a Worker entry for the host suite (handler-hosts.test.ts): bundled by esbuild into Miniflare, and imported in-process on Node. The module exports only the handler because workerd refuses any other export.
 */
export { default } from '../../handler.js';
