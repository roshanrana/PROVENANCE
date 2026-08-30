package plugin

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	fwkplugin "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/plugin"
)

// PluginType is the value used in EPP YAML `type:` fields.
const PluginType = "tenant-salt"

// DefaultIdentityHeader is what values-hardened.yaml configures the proxy to set
// after authenticating, and to strip from anything the client sent (ADR-006).
const DefaultIdentityHeader = "x-llmd-tenant"

// Config is the plugin's `parameters:` block (LLD §3).
type Config struct {
	// IdentityHeader carries the proxy-vouched tenant id.
	IdentityHeader string `json:"identityHeader"`

	// SaltSecretEnv names the environment variable holding the HMAC secret,
	// mounted from a Kubernetes Secret. The secret is never in the YAML, and
	// never logged — a derived salt in a log is a forgeable credential.
	SaltSecretEnv string `json:"saltSecretEnv"`

	// PropagateToEngine rewrites the outbound request body's cache_salt so
	// vLLM's own prefix cache partitions identically (ADR-007).
	//
	// Defaults true. With it false the EPP routing index is closed while the
	// engine's real KV cache stays shared — the weaker half of the mitigation
	// presented as the whole, which is worse than no mitigation because it
	// would be published as one.
	PropagateToEngine *bool `json:"propagateToEngine,omitempty"`

	// FailClosed rejects requests with absent or malformed identity rather than
	// routing them with an empty salt. Defaults true.
	FailClosed *bool `json:"failClosed,omitempty"`
}

func (c *Config) propagate() bool {
	return c.PropagateToEngine == nil || *c.PropagateToEngine
}

func (c *Config) failClosed() bool {
	return c.FailClosed == nil || *c.FailClosed
}

// TenantSalt binds the prefix cache salt to authenticated tenant identity.
//
// Three contractual obligations (LLD §4.3), and omitting any one of them yields a
// mitigation that appears to work and does not:
//
//	1. derive the salt by HMAC — never read it from the client
//	2. seed the EPP prefix hash chain with it
//	3. rewrite the outbound cache_salt so the engine partitions identically
type TenantSalt struct {
	typedName fwkplugin.TypedName
	cfg       Config
	secret    []byte
}

// Factory constructs the plugin from its YAML `parameters:` block.
func Factory(name string, parameters *json.Decoder, _ fwkplugin.Handle) (fwkplugin.Plugin, error) {
	cfg := Config{IdentityHeader: DefaultIdentityHeader}
	if parameters != nil {
		if err := parameters.Decode(&cfg); err != nil {
			return nil, fmt.Errorf("%s: could not parse parameters: %w", PluginType, err)
		}
	}
	if strings.TrimSpace(cfg.IdentityHeader) == "" {
		cfg.IdentityHeader = DefaultIdentityHeader
	}
	if strings.TrimSpace(cfg.SaltSecretEnv) == "" {
		return nil, fmt.Errorf("%s: saltSecretEnv is required", PluginType)
	}

	secret := []byte(os.Getenv(cfg.SaltSecretEnv))
	// Validated at construction, not per request. An EPP that starts with a weak
	// secret and only discovers it under load has already served traffic whose
	// isolation was never real.
	if len(secret) < MinSecretBytes {
		return nil, fmt.Errorf("%s: %s must hold at least %d bytes (got %d)",
			PluginType, cfg.SaltSecretEnv, MinSecretBytes, len(secret))
	}

	return &TenantSalt{
		typedName: fwkplugin.TypedName{Type: PluginType, Name: name},
		cfg:       cfg,
		secret:    secret,
	}, nil
}

func (p *TenantSalt) TypedName() fwkplugin.TypedName { return p.typedName }

// SaltFor resolves the salt for one request's headers.
//
// Returns ("", nil) only when fail-open is explicitly configured — which is
// available for the DEFAULT (leaking) deployment, because that is the
// configuration under attack and it must behave as upstream does.
func (p *TenantSalt) SaltFor(_ context.Context, headers map[string]string) (string, error) {
	tenant, err := TenantFromHeaders(headers, p.cfg.IdentityHeader)
	if err != nil {
		if p.cfg.failClosed() {
			return "", fmt.Errorf("%s: %w (header %q)", PluginType, err, p.cfg.IdentityHeader)
		}
		return "", nil
	}
	return DeriveSalt(p.secret, tenant)
}

// RewriteBody sets cache_salt on the outbound request body to the derived value.
//
// It OVERRIDES rather than merges or defers: a client-supplied cache_salt is
// exactly the forgery vector this plugin closes. Preferring the client's value
// when present — the natural-looking implementation — would leave the attack
// fully open while every test that only checks the honest path still passed.
func (p *TenantSalt) RewriteBody(body map[string]any, salt string) bool {
	if !p.cfg.propagate() || salt == "" {
		return false
	}
	body["cache_salt"] = salt
	return true
}

// Propagates reports whether obligation 3 is active. Exposed so the deploy
// smoke test can assert the hardened profile actually has it on.
func (p *TenantSalt) Propagates() bool { return p.cfg.propagate() }

// FailsClosed reports obligation-1 enforcement, for the same reason.
func (p *TenantSalt) FailsClosed() bool { return p.cfg.failClosed() }

func init() {
	// Registration happens here rather than in a fork of upstream: `Register`
	// writes to an exported package-level registry, so a blank import of this
	// package from our own main.go is enough (ADR-002, STATE.md F-02).
	//
	// Alpha stability is honest — this plugin has not been through upstream
	// review, and running it requires --allow-experimental-plugins.
	fwkplugin.Register(PluginType, fwkplugin.StabilityAlpha, Factory)
}
