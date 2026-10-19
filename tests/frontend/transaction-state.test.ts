import { describe, expect, it } from "vitest";
import { classifyTransactionState } from "@/lib/transaction-state";

describe("Bradbury transaction evidence", () => {
  it("treats the explorer's canceled evaluation as a proven failure", () => {
    expect(classifyTransactionState({ status: "CANCELED" })).toMatchObject({
      status: "CANCELED",
      failed: true,
      confirmed: false,
    });
  });

  it("does not call a merely pending transaction successful", () => {
    expect(classifyTransactionState({ status: "REVEALING" })).toMatchObject({ failed: false, confirmed: false });
  });

  it("requires successful execution evidence before confirmation", () => {
    expect(classifyTransactionState({ status: "FINALIZED", executionResult: "FINISHED_WITH_RETURN", result: "SUCCESS" })).toMatchObject({ failed: false, confirmed: true });
    expect(classifyTransactionState({ status: "FINALIZED", executionResult: "FINISHED_WITH_ERROR", result: "FAILURE" })).toMatchObject({ failed: true, confirmed: false });
  });
});
