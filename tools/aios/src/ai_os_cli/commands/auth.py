"""``aios auth`` — ``login``/``logout``/``whoami`` (``cli_design.md``
§4). No real ``/auth/login`` endpoint exists to exchange credentials
for a token (the Kernel only ever verifies a token someone else
already issued — a pre-shared HS256 secret or a real OIDC provider) —
``login`` stores a token the caller already has; ``whoami`` decodes
that token's own claims locally, genuinely correct without a server
round trip, since a JWT's claims are readable without verifying its
signature.
"""

from __future__ import annotations

import jwt
import typer

from ai_os_cli.config import load_config, save_token
from ai_os_cli.errors import EXIT_AUTHORIZATION_DENIED, CliError
from ai_os_cli.output import render

app = typer.Typer(help="Manage the locally stored bearer token.")


@app.command()
def login(
    ctx: typer.Context,
    token: str | None = typer.Option(None, "--token", help="A bearer token you already have."),
) -> None:
    """Stores a real bearer token for every later command to use."""
    real_token = token if token is not None else typer.prompt("Token", hide_input=True)
    save_token(real_token)
    render({"status": "logged in"}, output_format=ctx.obj["output_format"])


@app.command()
def logout(ctx: typer.Context) -> None:
    """Clears the locally stored token — no server call, since there
    is no server-side session to end (a bearer token is stateless)."""
    save_token(None)
    render({"status": "logged out"}, output_format=ctx.obj["output_format"])


@app.command()
def whoami(ctx: typer.Context) -> None:
    """Decodes the stored token's own real claims — ``sub``, ``roles``,
    ``exp`` — locally, without verifying its signature (this CLI holds
    no signing key) and without any server round trip (no ``/whoami``
    endpoint exists)."""
    config = load_config()
    if config.token is None:
        raise CliError("not logged in — run 'aios auth login'", exit_code=EXIT_AUTHORIZATION_DENIED)

    claims = jwt.decode(config.token, options={"verify_signature": False})
    render(claims, output_format=ctx.obj["output_format"])
