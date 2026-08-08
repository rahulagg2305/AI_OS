import { useState } from "react";
import { getToken, setToken } from "./token";

export function TokenBar() {
  const [value, setValue] = useState(() => getToken() ?? "");
  const [saved, setSaved] = useState(() => getToken() !== null);

  return (
    <form
      aria-label="Authentication"
      onSubmit={(event) => {
        event.preventDefault();
        setToken(value.trim() || null);
        setSaved(value.trim().length > 0);
      }}
    >
      <label htmlFor="bearer-token">Bearer token</label>
      <input
        id="bearer-token"
        type="password"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          setSaved(false);
        }}
        placeholder="Paste a bearer token"
      />
      <button type="submit">Save</button>
      <span role="status">{saved ? "Signed in" : "Not signed in"}</span>
    </form>
  );
}
