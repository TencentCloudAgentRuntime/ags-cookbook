package execcontext

import (
	"errors"
	"os/user"
	"strings"

	"github.com/e2b-dev/infra/packages/envd/internal/utils"
)

type Defaults struct {
	EnvVars     *utils.Map[string, string]
	User        string
	StartupUser *user.User
	Workdir     *string
}

// EnvironmentSnapshot copies an environment in KEY=VALUE form. Capturing it
// during startup makes it stable even if envd changes its own environment later.
func EnvironmentSnapshot(environ []string) *utils.Map[string, string] {
	result := utils.NewMap[string, string]()

	for _, item := range environ {
		key, value, ok := strings.Cut(item, "=")
		if ok {
			result.Store(key, value)
		}
	}

	return result
}

func ResolveDefaultWorkdir(workdir string, defaultWorkdir *string) string {
	if workdir != "" {
		return workdir
	}

	if defaultWorkdir != nil {
		return *defaultWorkdir
	}

	return ""
}

func ResolveDefaultUsername(username *string, defaultUsername string) (string, error) {
	if username != nil {
		return *username, nil
	}

	if defaultUsername != "" {
		return defaultUsername, nil
	}

	return "", errors.New("username not provided")
}
