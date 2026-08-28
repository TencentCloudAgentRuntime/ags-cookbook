package permissions

import (
	"net/http"
	"net/http/httptest"
	"os"
	"os/user"
	"strconv"
	"testing"

	"connectrpc.com/authn"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
)

func TestGetCurrentUserUsesEffectiveIDs(t *testing.T) {
	t.Parallel()

	// GetCurrentUser describes the running process, which is the effective
	// identity. It is deliberately NOT the OCI startup identity — see
	// execcontext.CaptureStartupIdentity for that.
	u := GetCurrentUser()

	assert.Equal(t, strconv.Itoa(os.Geteuid()), u.Uid)
	assert.Equal(t, strconv.Itoa(os.Getegid()), u.Gid)
	assert.NotEmpty(t, u.Username)
}

// TestGetAuthIdentityUsesStartupIdentityWithoutAuthorization is the default
// path: no BasicAuth means the command runs as the OCI startup identity, with
// its exact numeric IDs and supplementary groups.
func TestGetAuthIdentityUsesStartupIdentityWithoutAuthorization(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001, 20001},
		Username: "appuser",
		HomeDir:  "/home/appuser",
	}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}

	got, err := GetAuthIdentity(t.Context(), defaults)

	require.NoError(t, err)
	assert.Same(t, startup, got, "the startup snapshot must be used verbatim")
	assert.Equal(t, []uint32{10001, 20001}, got.Groups,
		"supplementary groups must survive the default path")
}

// TestGetAuthIdentityDoesNotRebuildStartupIdentityFromUsername guards the bug
// class where the default path looks the username up again: that would replace
// the runtime-applied GID and drop supplementary groups.
func TestGetAuthIdentityDoesNotRebuildStartupIdentityFromUsername(t *testing.T) {
	t.Parallel()

	// "root" resolves in every rootfs, but with gid 0 and only group 0. If the
	// implementation re-resolved the username, these fabricated numbers would be
	// replaced by the real ones.
	startup := &execcontext.Identity{
		UID:      0,
		GID:      4242,
		Groups:   []uint32{4242, 5150},
		Username: "root",
		HomeDir:  "/opt/app/work",
	}
	defaults := &execcontext.Defaults{User: "root", StartupIdentity: startup}

	got, err := GetAuthIdentity(t.Context(), defaults)

	require.NoError(t, err)
	assert.Equal(t, uint32(4242), got.GID, "the captured GID must not be replaced by the passwd primary group")
	assert.Equal(t, []uint32{4242, 5150}, got.Groups, "captured groups must not be rebuilt from the username")
	assert.Equal(t, "/opt/app/work", got.HomeDir)
}

// TestGetAuthIdentityWorksForNumericUIDWithoutPasswdEntry covers business image
// B: the OCI User is a bare numeric UID with no /etc/passwd entry.
func TestGetAuthIdentityWorksForNumericUIDWithoutPasswdEntry(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      61234,
		GID:      61234,
		Groups:   []uint32{61234},
		Username: "61234", // decimal fallback: no passwd entry exists
		HomeDir:  "",
	}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}

	got, err := GetAuthIdentity(t.Context(), defaults)

	require.NoError(t, err, "a UID without a passwd entry must not fail the request")
	assert.Equal(t, uint32(61234), got.UID)
	assert.Equal(t, uint32(61234), got.GID)
	assert.Same(t, startup, got)
}

func TestGetAuthIdentityPrefersExplicitUsername(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001},
		Username: "appuser",
	}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}
	ctx := authn.SetInfo(t.Context(), &user.User{Username: "root", Uid: "0", Gid: "0"})

	got, err := GetAuthIdentity(ctx, defaults)

	require.NoError(t, err)
	assert.Equal(t, uint32(0), got.UID, "an explicit username must override the startup identity")
	assert.Equal(t, uint32(0), got.GID)
	assert.Equal(t, "root", got.Username)
}

// TestGetAuthIdentityResolvesExplicitUsernameGroupsFromRootfs proves the
// explicit path resolves groups from the business rootfs rather than reusing the
// startup groups.
func TestGetAuthIdentityResolvesExplicitUsernameGroupsFromRootfs(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001, 20001},
		Username: "appuser",
	}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}
	ctx := authn.SetInfo(t.Context(), &user.User{Username: "root", Uid: "0", Gid: "0"})

	got, err := GetAuthIdentity(ctx, defaults)
	require.NoError(t, err)

	expected, err := execcontext.IdentityForUsername("root")
	require.NoError(t, err)

	assert.Equal(t, expected.Groups, got.Groups,
		"explicit-user groups must come from the rootfs, not from the startup snapshot")
	assert.NotContains(t, got.Groups, uint32(20001),
		"the startup supplementary group must not leak into an explicit identity")
}

func TestGetAuthIdentityRejectsUnknownExplicitUsername(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{UID: 10001, GID: 10001, Username: "appuser"}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}
	ctx := authn.SetInfo(t.Context(), &user.User{Username: "ghost-user-7c1e", Uid: "0", Gid: "0"})

	got, err := GetAuthIdentity(ctx, defaults)

	require.Error(t, err, "an unknown username must fail, never fall back to the default identity")
	assert.Nil(t, got)
	assert.Contains(t, err.Error(), "ghost-user-7c1e")
}

// TestGetAuthIdentityHonorsInitDefaultUserOverride records the /init
// compatibility interface: a caller-provided DefaultUser that names a different
// user is honored. AGS does not set it, so the frozen table is unaffected.
func TestGetAuthIdentityHonorsInitDefaultUserOverride(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001},
		Username: "appuser",
	}
	defaults := &execcontext.Defaults{User: "root", StartupIdentity: startup}

	got, err := GetAuthIdentity(t.Context(), defaults)

	require.NoError(t, err)
	assert.Equal(t, uint32(0), got.UID, "an /init DefaultUser override must win over the startup identity")
	assert.Equal(t, "root", got.Username)
}

func TestGetAuthIdentityFallsBackToDefaultUsernameWithoutSnapshot(t *testing.T) {
	t.Parallel()

	defaults := &execcontext.Defaults{User: "root"}

	got, err := GetAuthIdentity(t.Context(), defaults)

	require.NoError(t, err)
	assert.Equal(t, uint32(0), got.UID)
}

func TestGetAuthIdentityWithoutSnapshotOrDefaultFails(t *testing.T) {
	t.Parallel()

	got, err := GetAuthIdentity(t.Context(), &execcontext.Defaults{})

	require.Error(t, err)
	assert.Nil(t, got)
}

// TestGetAuthUserProjectsIdentity checks the *user.User adapter the filesystem
// API still consumes.
func TestGetAuthUserProjectsIdentity(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      10001,
		GID:      20001,
		Groups:   []uint32{20001, 30001},
		Username: "appuser",
		HomeDir:  "/home/appuser",
	}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}

	got, err := GetAuthUser(t.Context(), defaults)

	require.NoError(t, err)
	assert.Equal(t, "10001", got.Uid)
	assert.Equal(t, "20001", got.Gid, "the adapter must carry the captured GID, not a passwd lookup")
	assert.Equal(t, "appuser", got.Username)
	assert.Equal(t, "/home/appuser", got.HomeDir)
}

// TestAuthenticateUsernameThroughMiddleware drives the real authn middleware so
// the no-BasicAuth and explicit-BasicAuth paths are covered end to end rather
// than by constructing an authn.Request, whose only field is unexported.
func TestAuthenticateUsernameThroughMiddleware(t *testing.T) {
	t.Parallel()

	startup := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001, 20001},
		Username: "appuser",
		HomeDir:  "/home/appuser",
	}
	defaults := &execcontext.Defaults{User: startup.Username, StartupIdentity: startup}

	var (
		resolved *execcontext.Identity
		resolErr error
	)

	inner := http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		resolved, resolErr = GetAuthIdentity(r.Context(), defaults)
	})
	handler := authn.NewMiddleware(AuthenticateUsername).Wrap(inner)

	t.Run("no basic auth uses startup identity", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/process.Process/Start", nil)
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)

		require.NoError(t, resolErr)
		assert.Same(t, startup, resolved)
	})

	t.Run("explicit basic auth username wins", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/process.Process/Start", nil)
		req.SetBasicAuth("root", "")
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)

		require.NoError(t, resolErr)
		require.NotNil(t, resolved)
		assert.Equal(t, uint32(0), resolved.UID)
		assert.Equal(t, "root", resolved.Username)
	})

	t.Run("unknown basic auth username is rejected", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/process.Process/Start", nil)
		req.SetBasicAuth("ghost-user-7c1e", "")
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)

		// The middleware rejects the request before the handler runs, so the
		// default identity is never substituted for the unknown user.
		assert.NotEqual(t, http.StatusOK, rec.Code,
			"an unknown username must be rejected, not silently defaulted")
	})
}
