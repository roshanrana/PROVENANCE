package plugin

import (
	"reflect"
	"testing"

	fwkrh "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/requesthandling"
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
