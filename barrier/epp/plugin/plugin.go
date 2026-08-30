package plugin

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	fwkplugin "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/plugin"
	fwkrh "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/requesthandling"
	fwksched "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/scheduling"
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
	// mounted from a Kubernetes Secret. The secret is never in the YAML and
	// never logged — a derived salt in a log is a forgeable credential.
	SaltSecretEnv string `json:"saltSecretEnv"`

	// PropagateToEngine rewrites the request body's cache_salt so vLLM's own
	// prefix cache partitions identically (ADR-007). Defaults true.
	//
	// With it false the EPP routing index is closed while the engine's real KV
	// cache stays shared — the weaker half of the mitigation presented as the
	// whole, which is worse than no mitigation because it would be published
	// as one.
	PropagateToEngine *bool `json:"propagateToEngine,omitempty"`

	// FailClosed rejects requests with absent or malformed identity rather than
	// routing them with an empty salt. Defaults true.
	FailClosed *bool `json:"failClosed,omitempty"`
}

func (c *Config) propagate() bool  { return c.PropagateToEngine == nil || *c.PropagateToEngine }
func (c *Config) failClosed() bool { return c.FailClosed == nil || *c.FailClosed }

// TenantSalt binds the prefix cache salt to authenticated tenant identity.
//
// It implements requestcontrol.RequestHeaderProcessor, which is the hook that
// runs "after InferenceRequest creation but before admission control" — and
// therefore before any DataProducer computes prefix block hashes. That ordering
// is the whole reason this works: PreRequest fires after scheduling, far too
// late to influence the hash chain the scheduler already used.
type TenantSalt struct {
	typedName fwkplugin.TypedName
	cfg       Config
	secret    []byte
}

// Compile-time proof that we satisfy the framework's interfaces. Without these
// the plugin would register happily and then be silently inert, because nothing
// would ever call it — a failure mode that produces a "hardened" run behaving
// exactly like the default one.
var (
	_ fwkplugin.Plugin = (*TenantSalt)(nil)
)

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

// RequestHeader derives the salt and stamps it onto the request.
//
// Runs before data production, so the prefix hash chain is seeded with the
// derived value (obligation 2), and the same value reaches the engine
// (obligation 3).
func (p *TenantSalt) RequestHeader(_ context.Context, request *fwksched.InferenceRequest) error {
	salt, err := p.saltFor(request.Headers)
	if err != nil {
		// Fail closed: reject rather than route with an empty salt. An empty
		// salt is the shared default namespace — the exact exposure this plugin
		// exists to close — and failing open would look like success.
		return err
	}
	if salt == "" {
		return nil // fail-open, only reachable in the default (leaking) profile
	}
	if p.cfg.propagate() {
		ApplySalt(request.Body, salt)
	}
	return nil
}

// ApplySalt stamps the derived salt onto whichever request variant is populated.
//
// CacheSalt is not a field on InferenceRequestBody — it lives on each endpoint
// type (completions, chat, messages, ...) and on TokenizedRequest, which is what
// the prefix hasher actually reads. Setting only one of them would close the
// channel for one API surface and silently leave the others open, which is the
// kind of partial fix that is worse than none because it still gets published as
// a fix.
//
// Every assignment OVERRIDES rather than deferring to a client-supplied value:
// that value is precisely the forgery vector being closed.
func ApplySalt(body *fwkrh.InferenceRequestBody, salt string) int {
	if body == nil || salt == "" {
		return 0
	}
	applied := 0
	set := func(target *string) {
		*target = salt
		applied++
	}

	if body.Completions != nil {
		set(&body.Completions.CacheSalt)
	}
	if body.ChatCompletions != nil {
		set(&body.ChatCompletions.CacheSalt)
	}
	if body.Messages != nil {
		set(&body.Messages.CacheSalt)
	}
	if body.Responses != nil {
		set(&body.Responses.CacheSalt)
	}
	if body.Conversations != nil {
		set(&body.Conversations.CacheSalt)
	}
	if body.Embeddings != nil {
		set(&body.Embeddings.CacheSalt)
	}
	// The one that seeds the EPP's own prefix hash chain (obligation 2). The
	// others carry it to the engine (obligation 3).
	if body.TokenizedRequest != nil {
		set(&body.TokenizedRequest.CacheSalt)
	}
	return applied
}

func (p *TenantSalt) saltFor(headers map[string]string) (string, error) {
	tenant, err := TenantFromHeaders(headers, p.cfg.IdentityHeader)
	if err != nil {
		if p.cfg.failClosed() {
			return "", fmt.Errorf("%s: %w (header %q)", PluginType, err, p.cfg.IdentityHeader)
		}
		return "", nil
	}
	return DeriveSalt(p.secret, tenant)
}

// Propagates reports whether obligation 3 is active, so the deploy smoke test can
// assert the hardened profile actually has it on rather than assuming.
func (p *TenantSalt) Propagates() bool { return p.cfg.propagate() }

// FailsClosed reports obligation-1 enforcement, for the same reason.
func (p *TenantSalt) FailsClosed() bool { return p.cfg.failClosed() }

func init() {
	// Registration happens here rather than in a fork of upstream: Register
	// writes to an exported package-level registry, so a blank import of this
	// package from our own main.go is enough (ADR-002, STATE.md F-02).
	//
	// Alpha stability is honest — this has not been through upstream review, and
	// running it requires --allow-experimental-plugins. Registering it as Beta to
	// avoid the flag would be a small lie with a large payoff for us and none for
	// the reader.
	fwkplugin.Register(PluginType, fwkplugin.StabilityAlpha, Factory)
}
