# ADR-006: Authentication Strategy — OAuth2-First with Passkey Pre-design

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Satlas operates in two modes (ADR-004): a Public API (no auth required) and a Web Service with user features (bookmarks, saved preferences). Authentication is not needed at launch but must be designed into the schema from day one.

Three authentication mechanisms were evaluated:

1. **Email/password**: Traditional approach with password hashing
2. **OAuth2 (social login)**: Delegate authentication to a third-party provider (GitHub, Google)
3. **Passkeys (WebAuthn/FIDO2)**: Device-bound cryptographic credentials using biometric authentication

## Decision

**OAuth2-first at launch. Passkey schema pre-designed, activated in a future phase. Email/password not adopted.**

### OAuth2 at Launch

- Providers: GitHub (primary — matches developer/researcher audience), Google
- No password storage, no password reset flow
- Implementation complexity is low; mature libraries available

### Passkey Pre-design

The `passkey_credentials` table is included in the initial schema but the feature is not activated at launch. Pre-designing avoids a costly migration when passkeys are added later.

### Email/Password Not Adopted

Password management introduces credential storage, hashing, reset flows, and breach risk. The target audience (researchers, defense professionals) is well-served by OAuth2 and passkeys. The added complexity is not justified.

## Schema

```sql
CREATE TABLE users (
  id            SERIAL PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  display_name  TEXT,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE oauth_accounts (
  id                SERIAL PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider          TEXT NOT NULL,        -- 'github', 'google'
  provider_user_id  TEXT NOT NULL,
  created_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE (provider, provider_user_id)
);

CREATE TABLE passkey_credentials (
  id              SERIAL PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credential_id   TEXT UNIQUE NOT NULL,
  public_key      TEXT NOT NULL,
  sign_count      INTEGER DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

One user can link multiple OAuth providers. The `passkey_credentials` table is dormant at launch.

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| Email/password | Universally familiar | Password storage risk, reset flow complexity |
| **OAuth2 only at launch (chosen)** | Simple, no credential storage | Requires social account |
| OAuth2 + Passkey from launch | Most flexible | Higher initial complexity |
| Passkey only | Most secure, passwordless | Browser support still maturing, unfamiliar to some users |

## Consequences

- No password hashes stored — reduces security attack surface
- Users must have a GitHub or Google account to access user features at launch
- `passkey_credentials` table exists from day one — activating passkeys requires no schema migration
- JWT is used for session management once auth is active (per ADR-004)
- Passkey activation tracked in [GitHub Issue #5]
