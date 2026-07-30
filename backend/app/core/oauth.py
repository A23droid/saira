"""
Authlib OAuth client registry.

Two providers are registered:

- google: standard OpenID Connect, discovered via Google's well-known
  metadata document. Gives us an `id_token` we can decode for `sub`,
  `email`, and `name`.
- orcid: ORCID's "Public API — Authenticate with ORCID" flow. This is a
  plain OAuth2 (not full OIDC) flow; the token endpoint response itself
  contains the `orcid` iD and the user's `name` directly, so no separate
  userinfo call is required for basic sign-in.

Both clients are looked up lazily via `oauth.create_client(name)` in the
endpoints, which keeps this module free of any request-time logic.
"""

from authlib.integrations.starlette_client import OAuth

from app.core.config import settings

oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="orcid",
    client_id=settings.ORCID_CLIENT_ID,
    client_secret=settings.ORCID_CLIENT_SECRET,
    access_token_url=f"{settings.orcid_base_url}/oauth/token",
    authorize_url=f"{settings.orcid_base_url}/oauth/authorize",
    api_base_url=settings.orcid_api_base_url,
    client_kwargs={"scope": "/authenticate"},
)
