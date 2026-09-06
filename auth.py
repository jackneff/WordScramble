"""Access control.

The app is intended for one family, so it carries no user accounts. Instead of
a login page of its own, it sits behind Cloudflare Access: Cloudflare
authenticates the person at its edge and puts a short-lived signed JWT on every
request it forwards. This module's whole job is to refuse anything that does not
carry a valid one.

That means there is no password, PIN or session to guess here - an attacker
would have to forge a Cloudflare signature. In production the app is reached
through a cloudflared tunnel and listens only on loopback, so requests cannot
arrive from anywhere else in the first place; this check is the second lock.

AUTH_MODE=none disables all of it, which is what local development runs. app.py
refuses to start if that is combined with anything that looks like a real
deployment.
"""
import jwt
from flask import (
    current_app, g, jsonify, render_template, request,
)

from config import AUTH_CLOUDFLARE

# Cloudflare presents the assertion both ways. The header is set on proxied
# requests; the cookie is what a browser sends back on subsequent navigations.
ACCESS_HEADER = "Cf-Access-Jwt-Assertion"
ACCESS_COOKIE = "CF_Authorization"

# How long to trust a cached copy of Cloudflare's public keys. They rotate, but
# not often, and PyJWKClient refetches automatically when it sees a key id it
# does not recognise.
JWKS_LIFESPAN = 3600

_jwks_clients = {}


class AccessError(Exception):
    """The request did not carry a usable Cloudflare Access assertion."""


def _team_domain(app):
    return "https://{}.cloudflareaccess.com".format(app.config["CF_ACCESS_TEAM"])


def _jwks_client(app):
    """One cached key client per team, shared across requests."""
    url = _team_domain(app) + "/cdn-cgi/access/certs"
    client = _jwks_clients.get(url)
    if client is None:
        client = jwt.PyJWKClient(url, cache_keys=True, lifespan=JWKS_LIFESPAN)
        _jwks_clients[url] = client
    return client


def _assertion():
    return request.headers.get(ACCESS_HEADER) or request.cookies.get(ACCESS_COOKIE)


def verify(token):
    """Return the claims of a valid assertion, or raise AccessError.

    Checking the audience is the security-critical part: without it any token
    Cloudflare issued for any other application in the same team would be
    accepted here.
    """
    if not token:
        raise AccessError("No Cloudflare Access assertion on the request.")

    app = current_app
    try:
        signing_key = _jwks_client(app).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=app.config["CF_ACCESS_AUD"],
            issuer=_team_domain(app),
        )
    except Exception as exc:
        # Signature, audience, issuer, expiry and malformed-token failures all
        # land here and are all the same answer to the caller: no.
        raise AccessError(str(exc)) from exc


def current_identity():
    """The signed-in email address, or None when authentication is off."""
    return getattr(g, "identity", None)


def _denied():
    """Say no without saying why - the reason goes to the log, not the caller."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "Authentication required"}), 403
    return render_template("denied.html"), 403


def register_guard(app):
    """Refuse every request that did not arrive through Cloudflare Access."""
    if app.config["AUTH_MODE"] != AUTH_CLOUDFLARE:
        @app.before_request
        def no_identity():
            g.identity = None
        return

    @app.before_request
    def require_access():
        try:
            claims = verify(_assertion())
        except AccessError as exc:
            app.logger.warning(
                "Access denied for %s %s: %s", request.method, request.path, exc
            )
            return _denied()

        # Cloudflare issues service-token assertions with no email claim; label
        # those by their common name so log lines still identify the caller.
        g.identity = claims.get("email") or claims.get("common_name") or "unknown"
        return None
