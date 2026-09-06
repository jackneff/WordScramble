"""Cloudflare Access enforcement, and the startup checks that make it stick.

Tokens are minted here with a locally generated RSA key, and auth.py's key
lookup is pointed at that key, so nothing in this file touches the network.
"""
import datetime
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import auth
from app import create_app
from config import TestConfig

TEAM = "example-family"
AUD = "this-apps-audience-tag"
ISSUER = "https://{}.cloudflareaccess.com".format(TEAM)
REAL_SECRET = "not-the-dev-default"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture
def cf_app(tmp_path, keypair, monkeypatch):
    """An app in cloudflare mode whose key lookup returns our test key."""
    private, public = keypair

    class Cloudflare(TestConfig):
        DB_PATH = str(tmp_path / "cf.db")
        SECRET_KEY = REAL_SECRET
        AUTH_MODE = "cloudflare"
        CF_ACCESS_TEAM = TEAM
        CF_ACCESS_AUD = AUD

    class StubKey:
        key = public

    class StubClient:
        def get_signing_key_from_jwt(self, token):
            # A token signed by a key Cloudflare does not publish must fail the
            # same way a forged one would.
            if jwt.get_unverified_header(token).get("kid") == "unknown":
                raise jwt.PyJWKClientError("no matching key")
            return StubKey()

    monkeypatch.setattr(auth, "_jwks_client", lambda app: StubClient())
    return create_app(Cloudflare)


@pytest.fixture
def cf_client(cf_app):
    return cf_app.test_client()


def make_token(keypair, aud=AUD, issuer=ISSUER, expires_in=600, kid="test-key",
               email="parent@example.com"):
    private, _ = keypair
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "aud": aud,
            "iss": issuer,
            "email": email,
            "iat": now - datetime.timedelta(seconds=5),
            "exp": now + datetime.timedelta(seconds=expires_in),
        },
        private,
        algorithm="RS256",
        headers={"kid": kid},
    )


def get(client, keypair, path="/", **token_kwargs):
    return client.get(
        path, headers={auth.ACCESS_HEADER: make_token(keypair, **token_kwargs)}
    )


# --- the gate ---------------------------------------------------------------

def test_a_request_with_no_assertion_is_refused(cf_client):
    res = cf_client.get("/")

    assert res.status_code == 403
    assert "Not signed in" in res.get_data(as_text=True)


def test_the_api_refuses_with_json_not_html(cf_client):
    res = cf_client.get("/api/round/1")

    assert res.status_code == 403
    assert res.get_json()["error"] == "Authentication required"


def test_a_valid_assertion_gets_in(cf_client, keypair):
    assert get(cf_client, keypair).status_code == 200


def test_the_cookie_works_as_well_as_the_header(cf_client, keypair):
    cf_client.set_cookie(auth.ACCESS_COOKIE, make_token(keypair))

    assert cf_client.get("/").status_code == 200


def test_the_email_claim_becomes_the_identity(cf_app, cf_client, keypair):
    seen = {}

    @cf_app.before_request
    def capture():
        seen["identity"] = auth.current_identity()

    get(cf_client, keypair, email="grown-up@example.com")

    assert seen["identity"] == "grown-up@example.com"


# --- tokens that must not work ----------------------------------------------

def test_an_expired_token_is_refused(cf_client, keypair):
    assert get(cf_client, keypair, expires_in=-30).status_code == 403


def test_a_token_for_another_app_is_refused(cf_client, keypair):
    """The audience check: same team, same signing key, different application.

    Without it, any other app behind the same Cloudflare team would mint
    tokens that unlock this one.
    """
    assert get(cf_client, keypair, aud="some-other-apps-tag").status_code == 403


def test_a_token_from_another_team_is_refused(cf_client, keypair):
    assert get(
        cf_client, keypair, issuer="https://attacker.cloudflareaccess.com"
    ).status_code == 403


def test_a_token_signed_by_an_unknown_key_is_refused(cf_client, keypair):
    assert get(cf_client, keypair, kid="unknown").status_code == 403


def test_a_garbage_assertion_is_refused_not_crashed(cf_client):
    res = cf_client.get("/", headers={auth.ACCESS_HEADER: "not-a-jwt-at-all"})

    assert res.status_code == 403


def test_a_token_signed_with_none_algorithm_is_refused(cf_client):
    """The classic JWT downgrade: a token with a stripped signature."""
    forged = jwt.encode(
        {"aud": AUD, "iss": ISSUER, "email": "attacker@example.com",
         "exp": int(time.time()) + 600},
        key="",
        algorithm="none",
    )

    assert cf_client.get("/", headers={auth.ACCESS_HEADER: forged}).status_code == 403


# --- startup checks ---------------------------------------------------------

def _config(tmp_path, **overrides):
    attrs = {"DB_PATH": str(tmp_path / "boot.db")}
    attrs.update(overrides)
    return type("Boot", (TestConfig,), attrs)


def test_cloudflare_mode_needs_its_settings(tmp_path):
    config = _config(
        tmp_path, SECRET_KEY=REAL_SECRET, AUTH_MODE="cloudflare",
        CF_ACCESS_TEAM="example", CF_ACCESS_AUD=None,
    )

    with pytest.raises(RuntimeError, match="CF_ACCESS_AUD"):
        create_app(config)


def test_a_secure_cookie_without_authentication_refuses_to_start(tmp_path):
    """The dangerous combination: deployed over HTTPS with the gate switched off."""
    config = _config(tmp_path, SECRET_KEY=REAL_SECRET, SESSION_COOKIE_SECURE=True)

    with pytest.raises(RuntimeError, match="no authentication"):
        create_app(config)


def test_the_dev_secret_key_refuses_to_start_in_production(tmp_path):
    config = _config(
        tmp_path, SECRET_KEY="dev-only-not-for-production",
        SESSION_COOKIE_SECURE=True,
    )

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(config)


def test_the_dev_secret_key_is_fine_locally(tmp_path):
    config = _config(tmp_path, SECRET_KEY="dev-only-not-for-production")

    assert create_app(config) is not None
