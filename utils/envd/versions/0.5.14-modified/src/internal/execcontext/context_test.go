package execcontext

import (
	"errors"
	"os"
	"os/user"
	"strconv"
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

func TestNormalizeGroupsDeduplicatesAndSorts(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		want []uint32
		in   []uint32
	}{
		{name: "empty", in: nil, want: nil},
		{name: "single", in: []uint32{10001}, want: []uint32{10001}},
		{
			name: "unsorted with duplicates",
			in:   []uint32{20001, 10001, 20001, 10001, 0},
			want: []uint32{0, 10001, 20001},
		},
		{
			// The kernel may return the primary GID inside the supplementary
			// list; the result must not contain it twice.
			name: "primary gid repeated",
			in:   []uint32{10001, 10001},
			want: []uint32{10001},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, NormalizeGroups(tc.in))
		})
	}
}

func TestNormalizeGroupsDoesNotMutateInput(t *testing.T) {
	t.Parallel()

	in := []uint32{30, 10, 20, 10}
	original := append([]uint32(nil), in...)

	NormalizeGroups(in)

	assert.Equal(t, original, in, "input slice must not be reordered in place")
}

// TestCaptureStartupIdentityUsesRealIDs is the central guard for the setuid
// case: the snapshot must describe the OCI User (real IDs), never envd's
// effective identity, which is root under setuid.
func TestCaptureStartupIdentityUsesRealIDs(t *testing.T) {
	t.Parallel()

	identity := CaptureStartupIdentity(nil)

	require.NotNil(t, identity)
	assert.Equal(t, uint32(os.Getuid()), identity.UID, "must snapshot real UID, not effective")
	assert.Equal(t, uint32(os.Getgid()), identity.GID, "must snapshot real GID, not effective")
}

func TestCaptureStartupIdentityIncludesSupplementaryGroups(t *testing.T) {
	t.Parallel()

	identity := CaptureStartupIdentity(nil)

	require.NotNil(t, identity)
	assert.Contains(t, identity.Groups, identity.GID, "primary GID must be part of the group list")

	current, err := os.Getgroups()
	require.NoError(t, err)

	for _, group := range current {
		assert.Contains(t, identity.Groups, uint32(group),
			"supplementary group %d from the kernel must be preserved", group)
	}

	assert.Equal(t, NormalizeGroups(identity.Groups), identity.Groups,
		"groups must be stored deduplicated and sorted")
}

func TestCaptureStartupIdentityFallsBackToDecimalUIDWithoutPasswdEntry(t *testing.T) {
	t.Parallel()

	identity := CaptureStartupIdentity(nil)
	require.NotNil(t, identity)

	// When a passwd entry exists the username is used; otherwise the decimal UID
	// is the display name. Either way the capture must succeed and the numeric
	// identity must be intact.
	if _, err := user.LookupId(strconv.Itoa(os.Getuid())); err != nil {
		assert.Equal(t, strconv.Itoa(os.Getuid()), identity.Username,
			"a UID with no passwd entry must fall back to its decimal form")
	}

	assert.NotEmpty(t, identity.Username)
}

func TestCaptureStartupIdentityPrefersStartupEnvironmentHome(t *testing.T) {
	t.Parallel()

	env := EnvironmentSnapshot([]string{"HOME=/opt/app/home"})

	identity := CaptureStartupIdentity(env)

	require.NotNil(t, identity)
	assert.Equal(t, "/opt/app/home", identity.HomeDir,
		"HOME from the startup environment must win, so a setuid envd does not adopt /root")
}

func TestCaptureStartupIdentityIgnoresEmptyHome(t *testing.T) {
	t.Parallel()

	withoutHome := CaptureStartupIdentity(nil)
	withEmptyHome := CaptureStartupIdentity(EnvironmentSnapshot([]string{"HOME="}))

	assert.Equal(t, withoutHome.HomeDir, withEmptyHome.HomeDir,
		"an empty HOME must not overwrite the resolved home directory")
}

func TestIdentityUserRoundTrip(t *testing.T) {
	t.Parallel()

	identity := &Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001, 20001},
		Username: "appuser",
		HomeDir:  "/home/appuser",
	}

	u := identity.User()

	require.NotNil(t, u)
	assert.Equal(t, "10001", u.Uid)
	assert.Equal(t, "10001", u.Gid)
	assert.Equal(t, "appuser", u.Username)
	assert.Equal(t, "/home/appuser", u.HomeDir)
}

func TestIdentityUserOnNilIdentity(t *testing.T) {
	t.Parallel()

	var identity *Identity

	assert.Nil(t, identity.User())
	assert.False(t, identity.MatchesCurrentProcess())
}

// TestMatchesCurrentProcessComparesEffectiveIdentity pins the security-critical
// rule: the comparison is against the effective identity, so a setuid envd
// (euid 0) never concludes that a non-root target needs no Credential.
func TestMatchesCurrentProcessComparesEffectiveIdentity(t *testing.T) {
	t.Parallel()

	current := CaptureStartupIdentity(nil)
	require.NotNil(t, current)

	sameAsEffective := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()),
		Groups: currentProcessGroups(t),
	}
	assert.True(t, sameAsEffective.MatchesCurrentProcess(),
		"an identity equal to the effective identity needs no Credential")

	differentUID := &Identity{
		UID:    uint32(os.Geteuid()) + 1,
		GID:    uint32(os.Getegid()),
		Groups: currentProcessGroups(t),
	}
	assert.False(t, differentUID.MatchesCurrentProcess())

	differentGID := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()) + 1,
		Groups: currentProcessGroups(t),
	}
	assert.False(t, differentGID.MatchesCurrentProcess())
}

func TestMatchesCurrentProcessRequiresIdenticalGroups(t *testing.T) {
	t.Parallel()

	extraGroup := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()),
		Groups: NormalizeGroups(append(currentProcessGroups(t), 65099)),
	}
	assert.False(t, extraGroup.MatchesCurrentProcess(),
		"a differing group list must force a Credential, not be ignored")

	missingGroups := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()),
		Groups: nil,
	}

	if len(currentProcessGroups(t)) > 0 {
		assert.False(t, missingGroups.MatchesCurrentProcess(),
			"dropping the group list must not count as a match")
	}
}

// TestMatchesCurrentProcessTracksEffectiveUID asserts the decision reads the
// effective UID.
//
// In an ordinary test process the real and effective UIDs are equal, so this
// cannot by itself distinguish the two. The distinction is proven under genuine
// setuid in context_setuid_linux_test.go, where real != effective; this case only
// pins the same-identity behavior.
func TestMatchesCurrentProcessTracksEffectiveUID(t *testing.T) {
	t.Parallel()

	if os.Getuid() != os.Geteuid() {
		t.Skip("real and effective UID differ; the setuid test covers this case directly")
	}

	effectiveIdentity := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()),
		Groups: currentProcessGroups(t),
	}

	assert.True(t, effectiveIdentity.MatchesCurrentProcess(),
		"an identity equal to the effective identity must match")

	differentUID := &Identity{
		UID:    uint32(os.Geteuid()) + 4242,
		GID:    uint32(os.Getegid()),
		Groups: currentProcessGroups(t),
	}

	assert.False(t, differentUID.MatchesCurrentProcess(),
		"a different UID must require a Credential")
}

func TestIdentityForUsernameResolvesRoot(t *testing.T) {
	t.Parallel()

	identity, err := IdentityForUsername("root")
	require.NoError(t, err)

	assert.Equal(t, uint32(0), identity.UID)
	assert.Equal(t, uint32(0), identity.GID)
	assert.Equal(t, "root", identity.Username)
	assert.Contains(t, identity.Groups, uint32(0))
	assert.Equal(t, NormalizeGroups(identity.Groups), identity.Groups)
}

func TestIdentityForUsernameRejectsUnknownUser(t *testing.T) {
	t.Parallel()

	identity, err := IdentityForUsername("definitely-not-a-real-user-9d3f1a")

	require.Error(t, err)
	assert.Nil(t, identity)
	assert.Contains(t, err.Error(), "definitely-not-a-real-user-9d3f1a",
		"the error must name the user that could not be resolved")
}

func TestResolveDefaultWorkdir(t *testing.T) {
	t.Parallel()

	ociWorkdir := "/opt/app/work"

	tests := []struct {
		defaultWorkdir *string
		name           string
		requested      string
		want           string
	}{
		{
			name:           "explicit request wins",
			requested:      "/tmp",
			defaultWorkdir: &ociWorkdir,
			want:           "/tmp",
		},
		{
			name:           "no request uses startup cwd",
			requested:      "",
			defaultWorkdir: &ociWorkdir,
			want:           "/opt/app/work",
		},
		{
			name:           "no request and no default",
			requested:      "",
			defaultWorkdir: nil,
			want:           "",
		},
		{
			name:           "explicit request without default",
			requested:      "/tmp",
			defaultWorkdir: nil,
			want:           "/tmp",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, ResolveDefaultWorkdir(tc.requested, tc.defaultWorkdir))
		})
	}
}

func TestResolveDefaultUsername(t *testing.T) {
	t.Parallel()

	explicit := "appuser"

	got, err := ResolveDefaultUsername(&explicit, "startup")
	require.NoError(t, err)
	assert.Equal(t, "appuser", got)

	got, err = ResolveDefaultUsername(nil, "startup")
	require.NoError(t, err)
	assert.Equal(t, "startup", got)

	_, err = ResolveDefaultUsername(nil, "")
	require.Error(t, err)
}

func currentProcessGroups(t *testing.T) []uint32 {
	t.Helper()

	current, err := os.Getgroups()
	require.NoError(t, err)

	groups := make([]uint32, 0, len(current)+1)
	groups = append(groups, uint32(os.Getegid()))

	for _, group := range current {
		groups = append(groups, uint32(group))
	}

	return NormalizeGroups(groups)
}

// TestResolveDefaultWorkdirWithRootFallback documents the fallback main.go uses
// when os.Getwd() fails: the default becomes "/", not "unset".
//
// An unset default makes ExpandAndResolve fall back to the user's home directory,
// which the behavior contract forbids ("no cwd -> OCI Workdir, never HomeDir").
func TestResolveDefaultWorkdirWithRootFallback(t *testing.T) {
	t.Parallel()

	rootFallback := "/"

	assert.Equal(t, "/", ResolveDefaultWorkdir("", &rootFallback),
		"the root fallback must be used verbatim for a request without a cwd")
	assert.Equal(t, "/tmp", ResolveDefaultWorkdir("/tmp", &rootFallback),
		"an explicit cwd must still win over the fallback")

	// The failure mode the fallback exists to prevent: a nil default resolves to
	// the empty string, which callers then join onto HomeDir.
	assert.Empty(t, ResolveDefaultWorkdir("", nil),
		"a nil default yields an empty path, which is why main.go substitutes /")
}

func TestIdentityForUsernameReportsGroupLookupFailureShape(t *testing.T) {
	t.Parallel()

	// root always resolves with its groups, so this asserts the success shape;
	// the failure branch returns a usable identity ALONGSIDE an error, which the
	// signature must allow.
	identity, err := IdentityForUsername("root")

	require.NoError(t, err)
	require.NotNil(t, identity)
	assert.NotEmpty(t, identity.Groups,
		"a successful resolution must carry at least the primary group")
}

// TestCaptureStartupWorkdirUsesGetwdResult is the normal path.
func TestCaptureStartupWorkdirUsesGetwdResult(t *testing.T) {
	t.Parallel()

	cwd, err := CaptureStartupWorkdir(func() (string, error) { return "/opt/app/work", nil })

	require.NoError(t, err)
	assert.Equal(t, "/opt/app/work", cwd)
}

// TestCaptureStartupWorkdirFallsBackToRoot is the requirement behind the fallback:
// the default must never be left empty, because an empty default makes path
// resolution fall back to the user's home directory, which the contract forbids.
func TestCaptureStartupWorkdirFallsBackToRoot(t *testing.T) {
	t.Parallel()

	tests := []struct {
		getwd func() (string, error)
		name  string
	}{
		{
			name:  "getwd fails",
			getwd: func() (string, error) { return "", errors.New("getcwd: no such file or directory") },
		},
		{
			name:  "getwd returns empty",
			getwd: func() (string, error) { return "", nil },
		},
		{
			name:  "getwd fails but returns a path",
			getwd: func() (string, error) { return "/unreliable", errors.New("stale") },
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			cwd, err := CaptureStartupWorkdir(tc.getwd)

			require.Error(t, err, "the caller must be able to report the problem")
			assert.Equal(t, "/", cwd,
				"the default must be / so it never reverts to the user's home directory")
			assert.NotEmpty(t, cwd)
		})
	}
}

// TestCaptureStartupWorkdirFallbackDoesNotResolveToHomeDir ties the fallback to
// the behavior it protects: with "/" as the default, a request without a cwd
// resolves to "/", not to HomeDir.
func TestCaptureStartupWorkdirFallbackDoesNotResolveToHomeDir(t *testing.T) {
	t.Parallel()

	cwd, err := CaptureStartupWorkdir(func() (string, error) { return "", errors.New("boom") })
	require.Error(t, err)

	assert.Equal(t, "/", ResolveDefaultWorkdir("", &cwd))
	assert.NotEmpty(t, ResolveDefaultWorkdir("", &cwd),
		"an empty resolution is what would trigger the HomeDir fallback")
}

// TestIdentityForUsernameDegradesWithoutRejectingOnGroupFailure pins the
// availability contract: losing the supplementary groups must NOT reject the
// request. The primary identity is still correct, so the command runs and the
// loss is recorded on the identity for the caller to log.
//
// This is what an unreadable /etc/group produces. Rejecting instead would turn a
// working explicit-user request into an authentication failure. The lookup is
// stubbed rather than removing /etc/group, so the failure branch is exercised for
// real.
func TestIdentityForUsernameDegradesWithoutRejectingOnGroupFailure(t *testing.T) {
	original := groupIDsFor
	groupIDsFor = func(*user.User) ([]string, error) {
		return nil, errors.New("open /etc/group: no such file or directory")
	}

	t.Cleanup(func() { groupIDsFor = original })

	identity, err := IdentityForUsername("root")

	require.NoError(t, err,
		"an unreadable group database must not reject the request")
	require.NotNil(t, identity)
	assert.Equal(t, uint32(0), identity.UID, "the primary identity must still be correct")
	assert.Equal(t, []uint32{0}, identity.Groups,
		"the primary group must still be present so the command can run")
	assert.True(t, identity.GroupsIncomplete,
		"the loss must be recorded so a caller can log it")
}

func TestIdentityForUsernameDoesNotFlagCompleteGroups(t *testing.T) {
	identity, err := IdentityForUsername("root")

	require.NoError(t, err)
	require.NotNil(t, identity)
	assert.False(t, identity.GroupsIncomplete,
		"a successful group lookup must not be flagged as incomplete")
	assert.NotEmpty(t, identity.Groups)
}

func TestCaptureStartupIdentityDoesNotFlagCompleteGroups(t *testing.T) {
	t.Parallel()

	identity := CaptureStartupIdentity(nil)

	require.NotNil(t, identity)
	assert.False(t, identity.GroupsIncomplete,
		"os.Getgroups succeeds in a normal process, so nothing should be flagged")
}

// TestCaptureStartupIdentityIgnoresPasswdGID is what the Identity type exists to
// prevent: a passwd entry may name a different primary group than the GID the OCI
// runtime actually applied, and the runtime value must win.
//
// The test process's passwd GID usually equals its runtime GID, which would hide
// an overwrite, so the lookup is stubbed to report a deliberately different GID.
func TestCaptureStartupIdentityIgnoresPasswdGID(t *testing.T) {
	original := lookupUID
	lookupUID = func(uid string) (*user.User, error) {
		return &user.User{
			Uid:      uid,
			Gid:      "65123", // deliberately not the runtime GID
			Username: "passwd-name",
			HomeDir:  "/passwd/home",
		}, nil
	}

	t.Cleanup(func() { lookupUID = original })

	identity := CaptureStartupIdentity(nil)

	require.NotNil(t, identity)
	assert.Equal(t, uint32(os.Getgid()), identity.GID,
		"the runtime GID must win; a passwd GID must never overwrite it")
	assert.NotEqual(t, uint32(65123), identity.GID)
	assert.Contains(t, identity.Groups, uint32(os.Getgid()),
		"the group list must be built from the runtime identity")
	assert.NotContains(t, identity.Groups, uint32(65123))

	// The lookup is still allowed to supply display information.
	assert.Equal(t, "passwd-name", identity.Username)
	assert.Equal(t, "/passwd/home", identity.HomeDir)
}

// TestCaptureStartupIdentityIgnoresPasswdUID is the same guard for the UID.
func TestCaptureStartupIdentityIgnoresPasswdUID(t *testing.T) {
	original := lookupUID
	lookupUID = func(string) (*user.User, error) {
		return &user.User{Uid: "65124", Gid: "65123", Username: "passwd-name"}, nil
	}

	t.Cleanup(func() { lookupUID = original })

	identity := CaptureStartupIdentity(nil)

	require.NotNil(t, identity)
	assert.Equal(t, uint32(os.Getuid()), identity.UID,
		"the runtime UID must win over anything the passwd entry claims")
	assert.NotEqual(t, uint32(65124), identity.UID)
}

// TestMatchesCurrentProcessIgnoresGroupsIncompleteFlag pins that the flag is
// diagnostic only: it must not influence whether a Credential is needed.
func TestMatchesCurrentProcessIgnoresGroupsIncompleteFlag(t *testing.T) {
	t.Parallel()

	matching := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()),
		Groups: currentProcessGroups(t),
	}

	flagged := *matching
	flagged.GroupsIncomplete = true

	assert.Equal(t, matching.MatchesCurrentProcess(), flagged.MatchesCurrentProcess(),
		"the diagnostic flag must not change the credential decision")
}
