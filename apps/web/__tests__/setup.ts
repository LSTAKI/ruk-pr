import "@testing-library/jest-dom";
import React from "react";
import { vi } from "vitest";

vi.mock("recharts", async () => {
  const original = await vi.importActual<any>("recharts");
  return {
    ...original,
    ResponsiveContainer: ({ children }: any) =>
      React.createElement("div", { style: { width: 800, height: 400 } }, children),
  };
});
