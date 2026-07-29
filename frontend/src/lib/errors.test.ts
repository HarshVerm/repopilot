import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiRequestError } from "./api/client";
import { errorMessage } from "./errors";


describe("API error messages", () => {
  it("keeps an actionable backend permission message", () => {
    const error = new ApiRequestError({
      status: 403,
      code: "GITHUB_PERMISSION_DENIED",
      message:
        "GitHub App installation must grant Contents: Read and write.",
    });

    assert.equal(
      errorMessage(error),
      "GitHub App installation must grant Contents: Read and write.",
    );
  });
});
