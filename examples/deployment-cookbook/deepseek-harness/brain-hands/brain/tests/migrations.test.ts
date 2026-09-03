import { describe, expect, it } from "vitest";

import { migrationChecksum } from "../src/mysql/migrations.js";

describe("migration checksums", () => {
  it("are stable and detect changed image artifacts", () => {
    const original = migrationChecksum("SELECT 1;\n");
    expect(original).toBe(migrationChecksum("SELECT 1;\n"));
    expect(original).not.toBe(migrationChecksum("SELECT 2;\n"));
  });
});
