// Package plugin implements the "tenant-salt" llm-d EPP plugin.
//
// The finding this exists to fix (STATE.md F-01): llm-d seeds its prefix
// block-hash chain with the target model plus an OPTIONAL, CLIENT-SUPPLIED
// cache_salt, and nothing else. The isolation primitive already exists — the gap
// is that it is unenforced. Three ways that fails in a multi-tenant deployment:
//
//	omission   an attacker simply sends no salt, and shares the default namespace
//	forgery    an attacker sends a salt it learned or guessed belonging to a victim
//	negligence an honest tenant forgets to set one and is silently unprotected
//
// So this plugin does not invent salting. It DERIVES the salt from an
// authenticated tenant identity the proxy vouches for, and overrides whatever the
// client sent. See ADR-006 and ADR-007.
package plugin

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
)

// ErrNoIdentity is returned when the trusted identity header is absent or empty.
//
// With failClosed set (the default) this rejects the request. Routing with an
// empty salt instead would put the caller back in the shared default namespace —
// the exact failure the plugin exists to prevent — while appearing to work.
var ErrNoIdentity = errors.New("tenant-salt: no authenticated tenant identity on the request")

// ErrNoSecret is returned when the HMAC secret is missing or too short.
var ErrNoSecret = errors.New("tenant-salt: salt secret is missing or too short")

// MinSecretBytes is the shortest secret accepted.
//
// The derived salt is only as unguessable as this key. A short or guessable
// secret makes every tenant's salt derivable by anyone who can guess it, which
// restores the forgery attack in a form that is harder to notice.
const MinSecretBytes = 32

// SaltLength is the hex length of a derived salt: 128 bits, enough that guessing
// is hopeless while keeping the value short enough to sit in a request body.
const SaltLength = 32

// DeriveSalt returns the cache salt for a tenant.
//
// Deterministic — the same tenant must land in the same cache namespace on every
// request, or prefix caching within a tenant would never hit and the mitigation
// would look far more expensive than it is. HMAC rather than a plain hash so the
// salt cannot be computed by anyone who merely knows the tenant id.
func DeriveSalt(secret []byte, tenantID string) (string, error) {
	if len(secret) < MinSecretBytes {
		return "", fmt.Errorf("%w: got %d bytes, need at least %d",
			ErrNoSecret, len(secret), MinSecretBytes)
	}
	tenant := strings.TrimSpace(tenantID)
	if tenant == "" {
		return "", ErrNoIdentity
	}

	mac := hmac.New(sha256.New, secret)
	// Domain-separate the input so a tenant id can never be crafted to collide
	// with some other use of the same secret.
	mac.Write([]byte("provenance/tenant-salt/v1\x00"))
	mac.Write([]byte(tenant))
	return hex.EncodeToString(mac.Sum(nil))[:SaltLength], nil
}

// TenantFromHeaders extracts the identity the proxy vouched for.
//
// This is trustworthy ONLY because the proxy strips any client-supplied copy of
// the header before forwarding (ADR-006). That stripping is part of the
// deliverable, configured in values-hardened.yaml — without it the header is
// attacker-controlled and the whole mitigation is forgeable at the edge.
//
// Header lookup is case-insensitive: HTTP header names are, and a plugin that
// matched only the exact casing would fail open on a proxy that normalised them.
func TenantFromHeaders(headers map[string]string, headerName string) (string, error) {
	want := strings.ToLower(strings.TrimSpace(headerName))
	if want == "" {
		return "", fmt.Errorf("tenant-salt: identityHeader is not configured")
	}
	for key, value := range headers {
		if strings.ToLower(key) == want {
			tenant := strings.TrimSpace(value)
			if tenant == "" {
				return "", ErrNoIdentity
			}
			return tenant, nil
		}
	}
	return "", ErrNoIdentity
}
