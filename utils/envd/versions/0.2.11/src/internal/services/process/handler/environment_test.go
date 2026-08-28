package handler

import (
	"os/user"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/e2b-dev/infra/packages/envd/internal/utils"
)

func TestBuildProcessEnvironmentDoesNotInheritByDefault(t *testing.T) {
	t.Setenv(enableAllEnvVar, "")
	t.Setenv("ENVD_TEST_PARENT_ONLY", "parent")

	got := effectiveEnvironment(buildProcessEnvironment(testUser(), testEnvVars(), nil))

	require.NotContains(t, got, "ENVD_TEST_PARENT_ONLY")
}

func TestBuildProcessEnvironmentInheritsWhenEnabled(t *testing.T) {
	t.Setenv(enableAllEnvVar, "1")
	t.Setenv("ENVD_TEST_PARENT_ONLY", "parent")

	got := effectiveEnvironment(buildProcessEnvironment(testUser(), testEnvVars(), nil))

	require.Equal(t, "parent", got["ENVD_TEST_PARENT_ONLY"])
}

func TestBuildProcessEnvironmentOverrideOrder(t *testing.T) {
	t.Setenv(enableAllEnvVar, "1")
	t.Setenv("ENVD_TEST_OVERRIDE", "parent")
	t.Setenv("PATH", "/parent/bin")

	envVars := testEnvVars()
	envVars.Store("ENVD_TEST_OVERRIDE", "global")

	got := effectiveEnvironment(buildProcessEnvironment(
		testUser(),
		envVars,
		map[string]string{"ENVD_TEST_OVERRIDE": "request"},
	))

	require.Equal(t, "/parent/bin", got["PATH"])
	require.Equal(t, "/home/tester", got["HOME"])
	require.Equal(t, "tester", got["USER"])
	require.Equal(t, "tester", got["LOGNAME"])
	require.Equal(t, "request", got["ENVD_TEST_OVERRIDE"])
}

func testUser() *user.User {
	return &user.User{
		Username: "tester",
		HomeDir:  "/home/tester",
	}
}

func testEnvVars() *utils.Map[string, string] {
	return utils.NewMap[string, string]()
}

func effectiveEnvironment(entries []string) map[string]string {
	env := make(map[string]string, len(entries))
	for _, entry := range entries {
		key, value, ok := strings.Cut(entry, "=")
		if ok {
			env[key] = value
		}
	}

	return env
}
