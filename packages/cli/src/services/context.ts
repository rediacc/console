/**
 * Barrel re-export for context services.
 *
 * context-base.ts defines ContextServiceBase (core context logic).
 * context-resources.ts defines ContextService (resource CRUD) and the singleton.
 *
 * Keeping them in separate files avoids a circular-dependency TDZ error:
 * context-resources.ts extends ContextServiceBase, so it must be able to
 * import the base class without triggering its own evaluation first.
 */
export { ContextServiceBase } from './context-base.js';
export { contextService } from './context-resources.js';
