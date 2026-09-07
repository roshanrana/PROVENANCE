package plugin

import (
	"context"
	"reflect"
	"testing"

	fwkplugin "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/plugin"
	fwkrh "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/requesthandling"
	fwksched "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/scheduling"
	"github.com/llm-d/llm-d-router/pkg/epp/framework/plugins/requestcontrol/dataproducer/tokenizer"
)

const testSalt = "0123456789abcdef"

// TestApplySaltSeedsWhateverTheHasherWouldRead is the test that actually
// protects the mitigation.
//
// The EPP's prefix hash chain is seeded with tokenizer.CacheSaltFromBody(body).
// If that function reads a variant ApplySalt does not write, the hardened
// profile routes that request in the shared namespace while still reporting
// itself as hardened — a leak that no smoke test would show, because everything
// else about the deployment looks correct.
//
// So rather than asserting a hand-written list of variants, this asks the
// upstream function directly, for each variant in turn.
func TestApplySaltSeedsWhateverTheHasherWouldRead(t *testing.T) {
	for _, tc := range []struct {
		name string
		body func() *fwkrh.InferenceRequestBody
	}{
		{"completions", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{Completions: &fwkrh.CompletionsRequest{}}
		}},
		{"chat_completions", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{ChatCompletions: &fwkrh.ChatCompletionsRequest{}}
		}},
		{"messages", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{Messages: &fwkrh.MessagesRequest{}}
		}},
		{"responses", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{Responses: &fwkrh.ResponsesRequest{}}
		}},
		{"conversations", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{Conversations: &fwkrh.ConversationsRequest{}}
		}},
		{"embeddings", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{Embeddings: &fwkrh.EmbeddingsRequest{}}
		}},
		// The tokenized path — vLLM /inference/v1/generate, and the shape an
		// SGLang-backed pool is driven through. Missing before T-038a.
		{"generate", func() *fwkrh.InferenceRequestBody {
			return &fwkrh.InferenceRequestBody{Generate: &fwkrh.GenerateRequest{}}
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			body := tc.body()
			if got := ApplySalt(body, testSalt); got == 0 {
				t.Fatalf("ApplySalt wrote nothing for the %s variant", tc.name)
			}
			if got := tokenizer.CacheSaltFromBody(body); got != testSalt {
				t.Fatalf("hasher would read %q, want %q — this variant routes in the shared namespace", got, testSalt)
			}
		})
	}
}

// TestEveryBodyVariantWithACacheSaltIsCovered fails when upstream adds a new
// endpoint variant carrying CacheSalt.
//
// Without it, a routine dependency bump would silently reopen the channel for
// whatever surface the new variant serves, and the first sign would be a
// published claim that is no longer true.
func TestEveryBodyVariantWithACacheSaltIsCovered(t *testing.T) {
	// Set by ApplySalt today. A variant appearing upstream that is not here is
	// the failure this test exists to catch.
	covered := map[string]bool{
		"Completions": true, "ChatCompletions": true, "Messages": true,
		"Responses": true, "Conversations": true, "Embeddings": true,
		"Generate": true, "TokenizedPrompt": true,
	}

	bodyType := reflect.TypeOf(fwkrh.InferenceRequestBody{})
	for i := range bodyType.NumField() {
		field := bodyType.Field(i)
		if field.Type.Kind() != reflect.Ptr || field.Type.Elem().Kind() != reflect.Struct {
			continue
		}
		if _, hasSalt := field.Type.Elem().FieldByName("CacheSalt"); !hasSalt {
			continue
		}
		if !covered[field.Name] {
			t.Errorf("InferenceRequestBody.%s carries CacheSalt but ApplySalt never sets it; "+
				"requests on that surface would route in the shared namespace", field.Name)
		}
	}
}

func TestApplySaltOverridesAClientSuppliedValue(t *testing.T) {
	// The forgery vector. Deferring to what the client sent would leave a tenant
	// able to name another tenant's namespace, which is the whole exposure.
	body := &fwkrh.InferenceRequestBody{
		ChatCompletions: &fwkrh.ChatCompletionsRequest{CacheSalt: "attacker-supplied"},
	}
	ApplySalt(body, testSalt)
	if body.ChatCompletions.CacheSalt != testSalt {
		t.Fatalf("client value survived: %q", body.ChatCompletions.CacheSalt)
	}
}

func TestApplySaltIsANoOpWithoutASalt(t *testing.T) {
	body := &fwkrh.InferenceRequestBody{Completions: &fwkrh.CompletionsRequest{}}
	if got := ApplySalt(body, ""); got != 0 {
		t.Fatalf("wrote %d fields with an empty salt", got)
	}
	if ApplySalt(nil, testSalt) != 0 {
		t.Fatal("nil body should be a no-op, not a panic")
	}
}

// TestRequestHeaderSaltsTheTokenizedPath is the end-to-end assertion S-03 asked
// for: not that ApplySalt can set a field, but that a request arriving with a
// tenant header comes out the other side with a derived salt on the
// pre-tokenized body.
//
// That path is the one an SGLang-backed pool is driven through, and it is the
// one that was silently unsalted until ec00137. Testing ApplySalt alone would
// not have caught that, because ApplySalt was never reached for it.
func TestRequestHeaderSaltsTheTokenizedPath(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	p := &TenantSalt{
		typedName: fwkplugin.TypedName{Type: PluginType, Name: "t"},
		cfg:       Config{IdentityHeader: DefaultIdentityHeader},
		secret:    secret,
	}

	body := &fwkrh.InferenceRequestBody{Generate: &fwkrh.GenerateRequest{}}
	request := &fwksched.InferenceRequest{
		Headers: map[string]string{DefaultIdentityHeader: "equity-research"},
		Body:    body,
	}

	if err := p.RequestHeader(context.Background(), request); err != nil {
		t.Fatalf("RequestHeader: %v", err)
	}

	want, err := DeriveSalt(secret, "equity-research")
	if err != nil {
		t.Fatalf("DeriveSalt: %v", err)
	}
	if body.Generate.CacheSalt != want {
		t.Fatalf("Generate.CacheSalt = %q, want the derived salt %q", body.Generate.CacheSalt, want)
	}
	// And the hasher must agree, since it is what actually seeds the chain.
	if got := tokenizer.CacheSaltFromBody(body); got != want {
		t.Fatalf("hasher would read %q, want %q", got, want)
	}
}

// TestTwoTenantsDoNotShareANamespaceOnTheTokenizedPath states the property the
// mitigation exists for, on the surface that was leaking.
func TestTwoTenantsDoNotShareANamespaceOnTheTokenizedPath(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	p := &TenantSalt{
		typedName: fwkplugin.TypedName{Type: PluginType, Name: "t"},
		cfg:       Config{IdentityHeader: DefaultIdentityHeader},
		secret:    secret,
	}

	salts := make([]string, 0, 2)
	for _, tenant := range []string{"equity-research", "m-and-a"} {
		body := &fwkrh.InferenceRequestBody{Generate: &fwkrh.GenerateRequest{}}
		req := &fwksched.InferenceRequest{
			Headers: map[string]string{DefaultIdentityHeader: tenant},
			Body:    body,
		}
		if err := p.RequestHeader(context.Background(), req); err != nil {
			t.Fatalf("RequestHeader(%s): %v", tenant, err)
		}
		salts = append(salts, body.Generate.CacheSalt)
	}
	if salts[0] == salts[1] {
		t.Fatal("two tenants received the same salt: the namespaces are not disjoint")
	}
	if salts[0] == "" || salts[1] == "" {
		t.Fatal("an empty salt is the shared default namespace, not isolation")
	}
}
