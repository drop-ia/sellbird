"""Lets a Cloudflare Access identity stand in for the dashboard token (Dokploy).

Caddy asks this server about every request (forward_auth) before passing it
to the dashboard. The request has to carry a Cloudflare Access JWT
(Cf-Access-Jwt-Assertion) signed by the team's keys, for this application's
audience, not expired and, when SELLBIRD_ACCESS_EMAILS is set, for one of
those addresses. Then the answer carries the dashboard token, which Caddy puts
in the Authorization header, so nobody has to paste it. Anything else gets a
403 and Caddy stops there. If the keys can't be fetched the answer is also a
403: it never fails open.

Environment:
  SELLBIRD_ACCESS_TEAM_DOMAIN  e.g. yourteam.cloudflareaccess.com
  SELLBIRD_ACCESS_AUD          the application's AUD tag (Zero Trust > Access > the app)
  SELLBIRD_ACCESS_EMAILS       optional comma-separated allow list
  SELLBIRD_DASHBOARD_TOKEN_FILE  default /data/data/dashboard-token
  SELLBIRD_ACCESS_AUTH_PORT    default 5556 (always on 127.0.0.1)
"""

import http.server
import logging
import os
import re
import sys

import jwt

logger = logging.getLogger("sellbird.access_auth")

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
ASSERTION_HEADER = "Cf-Access-Jwt-Assertion"
TOKEN_HEADER = "X-Sellbird-Authorization"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"access_auth: {name} is not set; the dashboard stays closed.")
    return value


class AccessVerifier:
    def __init__(self, team_domain: str, audience: str, allowed_emails: set[str],
                 jwks_client=None):
        self.issuer = f"https://{team_domain}"
        self.audience = audience
        self.allowed_emails = allowed_emails
        self.jwks = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/cdn-cgi/access/certs", cache_keys=True, lifespan=3600, timeout=5)

    def email_for(self, assertion: str) -> str:
        """The verified email, or raises."""
        key = self.jwks.get_signing_key_from_jwt(assertion).key
        claims = jwt.decode(
            assertion, key, algorithms=["RS256"], audience=self.audience,
            issuer=self.issuer, leeway=30,
            options={"require": ["exp", "iat", "aud", "iss"]})
        email = str(claims.get("email") or "").strip().lower()
        if not email:
            raise PermissionError("no email in the identity")
        if self.allowed_emails and email not in self.allowed_emails:
            raise PermissionError("email not allowed")
        return email


def read_token(path: str) -> str:
    token = open(path, encoding="utf-8").read().strip()
    if not TOKEN_RE.match(token):
        raise ValueError("dashboard token file has no valid token")
    return token


def make_handler(verifier: AccessVerifier, token_file: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self):
            assertion = self.headers.get(ASSERTION_HEADER, "")
            try:
                if not assertion:
                    raise PermissionError("no Access identity")
                verifier.email_for(assertion)
                token = read_token(token_file)
            except Exception as e:  # any doubt is a refusal
                logger.warning("refused: %s", type(e).__name__)
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
            self.send_response(200)
            self.send_header(TOKEN_HEADER, "Bearer " + token)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _answer

        def log_message(self, fmt, *args):  # no request lines, no headers
            pass

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    verifier = AccessVerifier(
        _required("SELLBIRD_ACCESS_TEAM_DOMAIN"),
        _required("SELLBIRD_ACCESS_AUD"),
        {e.strip().lower() for e in os.environ.get("SELLBIRD_ACCESS_EMAILS", "").split(",") if e.strip()},
    )
    token_file = os.environ.get("SELLBIRD_DASHBOARD_TOKEN_FILE", "/data/data/dashboard-token")
    port = int(os.environ.get("SELLBIRD_ACCESS_AUTH_PORT", "5556"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(verifier, token_file))
    logger.info("checking Cloudflare Access identities on 127.0.0.1:%d", port)
    server.serve_forever()


if __name__ == "__main__":
    main()
