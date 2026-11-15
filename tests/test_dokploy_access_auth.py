"""deploy/dokploy/access_auth.py: a Cloudflare Access identity unlocks the dashboard."""

import importlib.util
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("access_auth", ROOT / "deploy" / "dokploy" / "access_auth.py")
access_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(access_auth)

TEAM = "team.cloudflareaccess.com"
AUD = "a" * 64
TOKEN = "T" * 43


class _Key:
    def __init__(self, key):
        self.key = key


class StubJWKS:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, assertion):
        return _Key(self.public_key)


@pytest.fixture(scope="module")
def keys():
    good = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return good, other


def assertion(key, **overrides):
    now = int(time.time())
    claims = {"aud": [AUD], "iss": f"https://{TEAM}", "email": "bruno@dropia.uy",
              "iat": now, "exp": now + 600}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def server(keys, tmp_path):
    good, _ = keys
    token_file = tmp_path / "dashboard-token"
    token_file.write_text(TOKEN + "\n")
    verifier = access_auth.AccessVerifier(TEAM, AUD, {"bruno@dropia.uy"},
                                          jwks_client=StubJWKS(good.public_key()))
    httpd = access_auth.http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), access_auth.make_handler(verifier, str(token_file)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", token_file
    httpd.shutdown()


def ask(url, assertion_value=None):
    headers = {access_auth.ASSERTION_HEADER: assertion_value} if assertion_value else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "/verify", headers=headers)) as r:
            return r.status, r.headers.get(access_auth.TOKEN_HEADER)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get(access_auth.TOKEN_HEADER)


def test_a_valid_access_identity_gets_the_dashboard_token(server, keys):
    url, _ = server

    status, header = ask(url, assertion(keys[0]))

    assert (status, header) == (200, "Bearer " + TOKEN)


def test_a_request_without_an_access_identity_is_refused(server):
    url, _ = server

    status, header = ask(url)

    assert (status, header) == (403, None)


def test_an_identity_signed_by_another_key_is_refused(server, keys):
    url, _ = server

    status, header = ask(url, assertion(keys[1]))

    assert (status, header) == (403, None)


def test_an_identity_for_another_application_is_refused(server, keys):
    url, _ = server

    status, header = ask(url, assertion(keys[0], aud=["b" * 64]))

    assert (status, header) == (403, None)


def test_an_identity_from_another_team_is_refused(server, keys):
    url, _ = server

    status, header = ask(url, assertion(keys[0], iss="https://other.cloudflareaccess.com"))

    assert (status, header) == (403, None)


def test_an_expired_identity_is_refused(server, keys):
    url, _ = server
    past = int(time.time()) - 3600

    status, header = ask(url, assertion(keys[0], iat=past - 600, exp=past))

    assert (status, header) == (403, None)


def test_an_identity_without_expiry_is_refused(server, keys):
    url, _ = server

    status, header = ask(url, assertion(keys[0], exp=None))

    assert (status, header) == (403, None)


def test_an_email_outside_the_allow_list_is_refused(server, keys):
    url, _ = server

    status, header = ask(url, assertion(keys[0], email="someone@example.com"))

    assert (status, header) == (403, None)


def test_an_unsigned_identity_is_refused(server):
    url, _ = server
    unsigned = jwt.encode({"aud": [AUD], "iss": f"https://{TEAM}", "email": "bruno@dropia.uy",
                           "iat": int(time.time()), "exp": int(time.time()) + 600},
                          None, algorithm="none")

    status, header = ask(url, unsigned)

    assert (status, header) == (403, None)


def test_a_bad_token_file_is_refused_instead_of_passed_on(server, keys):
    url, token_file = server
    token_file.write_text("not a token")

    status, header = ask(url, assertion(keys[0]))

    assert (status, header) == (403, None)
