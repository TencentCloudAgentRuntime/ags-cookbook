package execcontext

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEnvironmentSnapshot(t *testing.T) {
	t.Parallel()

	env := EnvironmentSnapshot([]string{
		"PATH=/first",
		"EMPTY=",
		"INVALID",
		"VALUE_WITH_EQUALS=a=b",
		"PATH=/last",
	})

	path, ok := env.Load("PATH")
	require.True(t, ok)
	assert.Equal(t, "/last", path)

	empty, ok := env.Load("EMPTY")
	require.True(t, ok)
	assert.Empty(t, empty)

	value, ok := env.Load("VALUE_WITH_EQUALS")
	require.True(t, ok)
	assert.Equal(t, "a=b", value)

	_, ok = env.Load("INVALID")
	assert.False(t, ok)
}
