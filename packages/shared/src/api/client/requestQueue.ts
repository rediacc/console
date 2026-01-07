/**
 * Request queue for serializing API requests.
 * Ensures token rotation is properly handled by processing requests sequentially.
 */
export class RequestQueue {
  private queue: Promise<void> = Promise.resolve();

  /**
   * Queue a request to be executed after all pending requests complete.
   * Errors from previous requests don't affect subsequent requests.
   */
  async enqueue<T>(request: () => Promise<T>): Promise<T> {
    const nextRequest = this.queue
      .catch(() => undefined) // Ignore previous errors
      .then(() => request());

    // Update queue to track this request (ignore its result for queue purposes)
    this.queue = nextRequest.then(
      () => undefined,
      () => undefined
    );

    return nextRequest;
  }
}
