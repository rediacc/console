/**
 * Validation error for invalid user input or data.
 * Used by both CLI and Web for consistent validation error handling.
 */
export class ValidationError extends Error {
  public readonly name = 'ValidationError';

  /**
   * Create a new ValidationError
   * @param message - Error message describing the validation failure
   * @param field - Optional field name that failed validation
   */
  constructor(
    message: string,
    public readonly field?: string
  ) {
    super(message);
  }
}
