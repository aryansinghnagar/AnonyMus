/* Vitest global test setup */
import { afterEach, vi } from "vitest";

// Clear all mocks between tests
afterEach(() => {
  vi.clearAllMocks();
});
