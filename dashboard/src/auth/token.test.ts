import { afterEach, describe, expect, it } from "vitest";
import { getToken, setToken } from "./token";

describe("token", () => {
  afterEach(() => {
    setToken(null);
  });

  it("has no token by default", () => {
    expect(getToken()).toBeNull();
  });

  it("persists a real token across reads", () => {
    setToken("a-real-bearer-token");
    expect(getToken()).toBe("a-real-bearer-token");
  });

  it("clears the token when set to null", () => {
    setToken("a-real-bearer-token");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});
