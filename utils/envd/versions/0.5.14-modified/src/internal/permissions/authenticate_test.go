package permissions

import (
	"os"
	"os/user"
	"strconv"
	"testing"

	"connectrpc.com/authn"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGetCurrentUserUsesEffectiveIDs(t *testing.T) {
	t.Parallel()

	u := GetCurrentUser()

	assert.Equal(t, strconv.Itoa(os.Geteuid()), u.Uid)
	assert.Equal(t, strconv.Itoa(os.Getegid()), u.Gid)
	assert.NotEmpty(t, u.Username)
}

func TestGetAuthUserUsesStartupIdentityWithoutAuthorization(t *testing.T) {
	t.Parallel()

	startupUser := &user.User{
		Uid:      "1234",
		Gid:      "5678",
		Username: "startup-user",
		HomeDir:  "/startup-home",
	}

	got, err := GetAuthUser(t.Context(), startupUser.Username, startupUser)

	require.NoError(t, err)
	assert.Same(t, startupUser, got)
}

func TestGetAuthUserPrefersAuthorizedIdentity(t *testing.T) {
	t.Parallel()

	startupUser := &user.User{Uid: "1234", Gid: "5678", Username: "startup-user"}
	authorizedUser := &user.User{Uid: "42", Gid: "43", Username: "authorized-user"}
	ctx := authn.SetInfo(t.Context(), authorizedUser)

	got, err := GetAuthUser(ctx, startupUser.Username, startupUser)

	require.NoError(t, err)
	assert.Same(t, authorizedUser, got)
}
