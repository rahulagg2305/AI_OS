import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TokenBar } from "./TokenBar";
import { getToken, setToken } from "./token";

describe("TokenBar", () => {
  afterEach(() => {
    setToken(null);
  });

  it("shows not signed in with no stored token", () => {
    render(<TokenBar />);
    expect(screen.getByRole("status")).toHaveTextContent("Not signed in");
  });

  it("genuinely persists a real token on submit", () => {
    render(<TokenBar />);

    fireEvent.change(screen.getByLabelText("Bearer token"), {
      target: { value: "a-real-bearer-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByRole("status")).toHaveTextContent("Signed in");
    expect(getToken()).toBe("a-real-bearer-token");
  });
});
