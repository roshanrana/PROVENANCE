package plugin

import (
	"errors"
	"strings"
	"testing"
)

var testSecret = []byte("this-is-a-thirty-two-byte-secret!!")

func TestDeriveSaltIsDeterministic(t *testing.T) {
	// The same tenant must land in the same namespace on every request, or
	// prefix caching within a tenant never hits and the mitigation looks far
	// more expensive than it is.
	a, err := DeriveSalt(testSecret, "tenant-a")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	b, _ := DeriveSalt(testSecret, "tenant-a")
	if a != b {
		t.Fatalf("salt is not deterministic: %q != %q", a, b)
	}
}

func TestDifferentTenantsGetDifferentSalts(t *testing.T) {
	a, _ := DeriveSalt(testSecret, "tenant-a")
	b, _ := DeriveSalt(testSecret, "tenant-b")
	if a == b {
		t.Fatal("two tenants share a salt — they would share a cache namespace")
	}
}

func TestSaltDependsOnTheSecret(t *testing.T) {
	// Otherwise anyone who knows the tenant id could compute the salt, which
	// restores the forgery attack in a harder-to-notice form.
	other := []byte("a-completely-different-32b-secret!")
	a, _ := DeriveSalt(testSecret, "tenant-a")
	b, _ := DeriveSalt(other, "tenant-a")
	if a == b {
		t.Fatal("salt does not depend on the secret")
	}
}

func TestSaltLength(t *testing.T) {
	s, _ := DeriveSalt(testSecret, "tenant-a")
	if len(s) != SaltLength {
		t.Fatalf("expected %d hex chars, got %d", SaltLength, len(s))
	}
}

func TestShortSecretIsRefused(t *testing.T) {
	_, err := DeriveSalt([]byte("too-short"), "tenant-a")
	if !errors.Is(err, ErrNoSecret) {
		t.Fatalf("expected ErrNoSecret, got %v", err)
	}
}

func TestEmptyTenantIsRefused(t *testing.T) {
	for _, id := range []string{"", "   ", "\t"} {
		if _, err := DeriveSalt(testSecret, id); !errors.Is(err, ErrNoIdentity) {
			t.Fatalf("empty tenant %q should be refused, got %v", id, err)
		}
	}
}

func TestTenantIsTrimmed(t *testing.T) {
	// " tenant-a" and "tenant-a" are the same tenant; treating them as two
	// would silently split one tenant's cache in half.
	a, _ := DeriveSalt(testSecret, "tenant-a")
	b, _ := DeriveSalt(testSecret, "  tenant-a  ")
	if a != b {
		t.Fatal("whitespace changed the derived salt")
	}
}

func TestDomainSeparation(t *testing.T) {
	// A tenant id must not be craftable to collide with another use of the
	// same secret. The prefix makes the input space disjoint.
	a, _ := DeriveSalt(testSecret, "a")
	b, _ := DeriveSalt(testSecret, "provenance/tenant-salt/v1\x00a")
	if a == b {
		t.Fatal("domain separation is ineffective")
	}
}

func TestTenantFromHeadersIsCaseInsensitive(t *testing.T) {
	// HTTP header names are case-insensitive, and proxies normalise them
	// differently. Matching only exact casing would fail open.
	for _, key := range []string{"x-llmd-tenant", "X-LLMD-Tenant", "X-Llmd-Tenant"} {
		got, err := TenantFromHeaders(map[string]string{key: "tenant-a"}, "x-llmd-tenant")
		if err != nil || got != "tenant-a" {
			t.Fatalf("header %q: got %q, err %v", key, got, err)
		}
	}
}

func TestMissingHeaderIsRefused(t *testing.T) {
	// Fail closed. Routing with an empty salt would put the caller back in the
	// shared default namespace — the exact failure this plugin prevents.
	_, err := TenantFromHeaders(map[string]string{"other": "x"}, "x-llmd-tenant")
	if !errors.Is(err, ErrNoIdentity) {
		t.Fatalf("expected ErrNoIdentity, got %v", err)
	}
}

func TestEmptyHeaderValueIsRefused(t *testing.T) {
	_, err := TenantFromHeaders(map[string]string{"x-llmd-tenant": "  "}, "x-llmd-tenant")
	if !errors.Is(err, ErrNoIdentity) {
		t.Fatalf("expected ErrNoIdentity, got %v", err)
	}
}

func TestUnconfiguredHeaderNameIsAnError(t *testing.T) {
	_, err := TenantFromHeaders(map[string]string{"x": "y"}, "")
	if err == nil || !strings.Contains(err.Error(), "identityHeader") {
		t.Fatalf("expected a configuration error, got %v", err)
	}
}

func TestSaltIsHex(t *testing.T) {
	s, _ := DeriveSalt(testSecret, "tenant-a")
	for _, r := range s {
		if !strings.ContainsRune("0123456789abcdef", r) {
			t.Fatalf("non-hex character %q in salt %q", r, s)
		}
	}
}
