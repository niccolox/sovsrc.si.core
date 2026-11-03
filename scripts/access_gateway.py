#!/usr/bin/env python3
"""Create or update the Cloudflare Access gateway for the MCP endpoint.

The script creates a self-hosted Access application for hello.sovsrc.si/mcp
with Managed OAuth on, an Allow policy for the listed emails, and writes
TEAM_DOMAIN and POLICY_AUD into wrangler.toml. Run `make deploy` after it.

Usage:
    export CLOUDFLARE_API_TOKEN=...   # needs "Access: Apps and Policies Write"
    python scripts/access_gateway.py --email you@example.com [--email ...]

Options:
    --account-id   Cloudflare account id (default: the sovsrc.si account)
    --hostname     Protected URL without scheme (default: hello.sovsrc.si/mcp)
    --name         Access application name (default: sovsrc-si-core MCP)
    --dry-run      Print the planned changes and exit
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
DEFAULT_ACCOUNT = "eb7b649cd5ea63241107e86cf00d2cef"


def call(token: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as err:
        payload = json.load(err)
    if not payload.get("success"):
        sys.exit(f"{method} {path} failed: {json.dumps(payload.get('errors'), indent=2)}")
    return payload["result"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", action="append", required=True, help="Email allowed to use the MCP server")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT)
    parser.add_argument("--hostname", default="hello.sovsrc.si/mcp")
    parser.add_argument("--name", default="sovsrc-si-core MCP")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("Set CLOUDFLARE_API_TOKEN. The token needs Access: Apps and Policies Write.")

    account = args.account_id
    org = call(token, "GET", f"/accounts/{account}/access/organizations")
    team_domain = f"https://{org['auth_domain']}"
    print(f"Zero Trust organization: {org.get('name')} ({team_domain})")

    policy = {
        "name": f"Allow {args.name} users",
        "decision": "allow",
        "include": [{"email": {"email": e}} for e in args.email],
        "exclude": [],
        "require": [],
    }
    app_body = {
        "type": "self_hosted",
        "name": args.name,
        "domain": args.hostname,
        "self_hosted_domains": [args.hostname],
        "session_duration": "24h",
        "app_launcher_visible": False,
        "allowed_idps": [],
        "auto_redirect_to_identity": False,
        "policies": [policy],
        "oauth_configuration": {"enabled": True},
    }

    apps = call(token, "GET", f"/accounts/{account}/access/apps")
    existing = next((a for a in apps if a.get("name") == args.name), None)

    if args.dry_run:
        action = "update" if existing else "create"
        print(f"Would {action} Access application:")
        print(json.dumps(app_body, indent=2))
        return

    if existing:
        app = call(token, "PUT", f"/accounts/{account}/access/apps/{existing['id']}", app_body)
        print(f"Updated Access application {app['id']}")
    else:
        app = call(token, "POST", f"/accounts/{account}/access/apps", app_body)
        print(f"Created Access application {app['id']}")

    aud = app["aud"]
    print(f"AUD: {aud}")

    wrangler = Path(__file__).resolve().parent.parent / "wrangler.toml"
    text = wrangler.read_text()
    text = re.sub(r'^TEAM_DOMAIN = ".*"$', f'TEAM_DOMAIN = "{team_domain}"', text, flags=re.M)
    text = re.sub(r'^POLICY_AUD = ".*"$', f'POLICY_AUD = "{aud}"', text, flags=re.M)
    wrangler.write_text(text)
    print(f"Wrote TEAM_DOMAIN and POLICY_AUD to {wrangler}")
    print("Next: run `make deploy`, then `claude mcp add --transport http sovsrc-rewards https://hello.sovsrc.si/mcp`")


if __name__ == "__main__":
    main()
