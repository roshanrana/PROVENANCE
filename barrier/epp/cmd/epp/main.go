// Command epp is the PROVENANCE Endpoint Picker.
//
// It is upstream's runner, unmodified, plus one registered plugin. That is the
// whole binary — and it is the point (ADR-002). A reviewer can see that we
// changed nothing about how llm-d routes; we only added a plugin they could drop
// into their own build. A fork would carry permanent merge burden and would leave
// every reader wondering what else we changed.
package main

import (
	"context"
	"os"

	"github.com/llm-d/llm-d-router/cmd/epp/runner"

	// Blank import for the side effect: the package's init() calls
	// plugin.Register, which is all that is needed to make "tenant-salt"
	// available to the YAML config.
	_ "github.com/roshanrana/provenance/barrier/epp/plugin"
)

func main() {
	if err := runner.NewRunner().WithExecutableName("provenance-epp").Run(context.Background()); err != nil {
		os.Exit(1)
	}
}
