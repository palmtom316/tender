import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(__dirname, "../..");
const read = (path: string) => readFileSync(resolve(root, path), "utf8");

describe("design-system CSS contracts", () => {
  it("defines shared component tokens used across pages", () => {
    const tokens = read("src/styles/tokens.css");
    expect(tokens).toContain("--control-height-sm");
    expect(tokens).toContain("--control-height-md");
    expect(tokens).toContain("--control-height-lg");
    expect(tokens).toContain("--table-row-height");
    expect(tokens).toContain("--toolbar-gap");
    expect(tokens).toContain("--state-icon-size");
  });

  it("shares table styling between data and asset tables", () => {
    const tables = read("src/styles/tables.css");
    expect(tables).toContain(":where(.data-table, .asset-table)");
    expect(tables).toContain(":where(.data-table, .asset-table) th");
    expect(tables).toContain(":where(.data-table, .asset-table) td");
  });

  it("provides unified chip and local tab classes", () => {
    const tabs = read("src/styles/tabs.css") + read("src/styles/utilities.css");
    expect(tabs).toContain(".segmented-tabs");
    expect(tabs).toContain(".segmented-tab");
    expect(tabs).toContain(".filter-chip");
  });
});
