package permissions

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
)

// TestExpandAndResolveUsesStartupCwdWithoutRequestedPath is the Workdir default:
// with no requested cwd the captured startup cwd is used, and an absolute OCI
// Workdir must not be joined onto the home directory.
func TestExpandAndResolveUsesStartupCwdWithoutRequestedPath(t *testing.T) {
	t.Parallel()

	ociWorkdir := "/opt/app/work"
	identity := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Username: "appuser",
		HomeDir:  "/home/appuser",
	}

	got, err := ExpandAndResolve("", identity.User(), &ociWorkdir)

	require.NoError(t, err)
	assert.Equal(t, "/opt/app/work", got,
		"an absolute OCI Workdir must be used as-is, never joined onto HomeDir")
}

func TestExpandAndResolvePrefersExplicitPath(t *testing.T) {
	t.Parallel()

	ociWorkdir := "/opt/app/work"
	identity := &execcontext.Identity{Username: "appuser", HomeDir: "/home/appuser"}

	got, err := ExpandAndResolve("/tmp", identity.User(), &ociWorkdir)

	require.NoError(t, err)
	assert.Equal(t, "/tmp", got)
}

// TestExpandAndResolveDoesNotFallBackToHomeDir pins the regression this delivery
// fixes: with a captured startup cwd, the default must never become HomeDir.
func TestExpandAndResolveDoesNotFallBackToHomeDir(t *testing.T) {
	t.Parallel()

	ociWorkdir := "/opt/app/work"
	identity := &execcontext.Identity{Username: "appuser", HomeDir: "/home/appuser"}

	got, err := ExpandAndResolve("", identity.User(), &ociWorkdir)

	require.NoError(t, err)
	assert.NotEqual(t, "/home/appuser", got)
	assert.Equal(t, "/opt/app/work", got)
}

// TestExpandAndResolveRelativePathSemanticsPreserved documents the pre-existing
// behavior for relative request paths: they are joined onto HomeDir. This is
// unchanged by this delivery and is asserted so a future change is deliberate.
func TestExpandAndResolveRelativePathSemanticsPreserved(t *testing.T) {
	t.Parallel()

	ociWorkdir := "/opt/app/work"
	identity := &execcontext.Identity{Username: "appuser", HomeDir: "/home/appuser"}

	got, err := ExpandAndResolve("sub/dir", identity.User(), &ociWorkdir)

	require.NoError(t, err)
	assert.Equal(t, "/home/appuser/sub/dir", got)
}

func TestExpandAndResolveTildeExpansion(t *testing.T) {
	t.Parallel()

	identity := &execcontext.Identity{Username: "appuser", HomeDir: "/home/appuser"}

	got, err := ExpandAndResolve("~/logs", identity.User(), nil)

	require.NoError(t, err)
	assert.Equal(t, "/home/appuser/logs", got)
}

// DescribeCwdAccess is diagnostic only: it must never be the thing that decides
// whether a command runs. The kernel is the authority (it also honors POSIX ACLs,
// SELinux, and capabilities), so these tests assert on the *message*, not on an
// allow/deny outcome.

func TestDescribeCwdAccessSilentWhenOwnerCanSearch(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0o700))

	assert.Empty(t, DescribeCwdAccess(dir, currentIdentity(t)),
		"no diagnostic should be produced when the bits already permit search")
}

func TestDescribeCwdAccessSilentForSupplementaryGroupMatch(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0o710))

	info, err := os.Stat(dir)
	require.NoError(t, err)

	stat := statT(t, info)

	// The directory's group is only a supplementary group of the identity. This is
	// the "shared group" case from the acceptance matrix.
	identity := &execcontext.Identity{
		UID:      stat.Uid + 1000,
		GID:      stat.Gid + 2000,
		Groups:   execcontext.NormalizeGroups([]uint32{stat.Gid + 2000, stat.Gid}),
		Username: "shared-group-member",
	}

	assert.NotContains(t, DescribeCwdAccess(dir, identity), dir,
		"a supplementary group match must not be reported as blocking")
}

func TestDescribeCwdAccessSilentForPrimaryGroupMatch(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0o710))

	info, err := os.Stat(dir)
	require.NoError(t, err)

	stat := statT(t, info)

	// The primary GID alone must be honored, even when Groups was not populated.
	identity := &execcontext.Identity{
		UID:      stat.Uid + 1000,
		GID:      stat.Gid,
		Username: "primary-group-member",
	}

	assert.NotContains(t, DescribeCwdAccess(dir, identity), dir)
}

func TestDescribeCwdAccessSilentForRoot(t *testing.T) {
	t.Parallel()

	dir := filepath.Join(t.TempDir(), "locked")
	require.NoError(t, os.Mkdir(dir, 0o000))

	identity := &execcontext.Identity{UID: 0, GID: 0, Groups: []uint32{0}, Username: "root"}

	assert.Empty(t, DescribeCwdAccess(dir, identity),
		"root is not blocked by permission bits")
}

func TestDescribeCwdAccessNamesTheBlockingLeaf(t *testing.T) {
	t.Parallel()

	dir := filepath.Join(t.TempDir(), "private")
	require.NoError(t, os.Mkdir(dir, 0o700))

	info, err := os.Stat(dir)
	require.NoError(t, err)

	stat := statT(t, info)

	identity := &execcontext.Identity{
		UID:      stat.Uid + 1000,
		GID:      stat.Gid + 1000,
		Groups:   []uint32{stat.Gid + 1000},
		Username: "otheruser",
	}

	detail := DescribeCwdAccess(dir, identity)

	require.NotEmpty(t, detail,
		"a blocked component must produce a diagnostic, not an empty string")
	assert.Contains(t, detail, "without search permission",
		"the diagnostic must say what is wrong")
	assert.Contains(t, detail, dir, "the blocking directory must be named")
	assert.Contains(t, detail, "0700", "the mode must be reported")
}

// TestDescribeCwdAccessNamesABlockingAncestor is the case a leaf-only check
// misses: search permission is needed on every component, and a locked-down
// parent is the usual cause.
func TestDescribeCwdAccessNamesABlockingAncestor(t *testing.T) {
	t.Parallel()

	parent := filepath.Join(t.TempDir(), "locked-parent")
	require.NoError(t, os.Mkdir(parent, 0o700))

	leaf := filepath.Join(parent, "open-leaf")
	require.NoError(t, os.Mkdir(leaf, 0o777))

	info, err := os.Stat(parent)
	require.NoError(t, err)

	stat := statT(t, info)

	identity := &execcontext.Identity{
		UID:      stat.Uid + 1000,
		GID:      stat.Gid + 1000,
		Groups:   []uint32{stat.Gid + 1000},
		Username: "otheruser",
	}

	detail := DescribeCwdAccess(leaf, identity)

	require.NotEmpty(t, detail,
		"a blocked ancestor must produce a diagnostic, not an empty string")
	assert.Contains(t, detail, "without search permission")
	assert.Contains(t, detail, parent,
		"a blocking ancestor must be reported even when the leaf itself is world-searchable")
}

func TestDescribeCwdAccessSilentForWorldExecutablePath(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0o711))

	info, err := os.Stat(dir)
	require.NoError(t, err)

	stat := statT(t, info)

	identity := &execcontext.Identity{
		UID:      stat.Uid + 1000,
		GID:      stat.Gid + 1000,
		Groups:   []uint32{stat.Gid + 1000},
		Username: "anyuser",
	}

	assert.NotContains(t, DescribeCwdAccess(dir, identity), dir,
		"the world execute bit permits search for unrelated users")
}

func TestDescribeCwdAccessWithNilIdentity(t *testing.T) {
	t.Parallel()

	assert.Empty(t, DescribeCwdAccess(t.TempDir(), nil))
}

// TestCwdFailureContextAlwaysNamesUserAndCwd is the requirement from the spec:
// a cwd failure must carry both the target user and the directory.
func TestCwdFailureContextAlwaysNamesUserAndCwd(t *testing.T) {
	t.Parallel()

	dir := filepath.Join(t.TempDir(), "private")
	require.NoError(t, os.Mkdir(dir, 0o700))

	identity := &execcontext.Identity{
		UID:      60123,
		GID:      60124,
		Groups:   []uint32{60124},
		Username: "otheruser",
	}

	context := CwdFailureContext(dir, identity)

	assert.Contains(t, context, "otheruser", "the target user must be named")
	assert.Contains(t, context, dir, "the cwd must be named")
	assert.Contains(t, context, "60123", "the numeric UID must be included")
	assert.Contains(t, context, "60124", "the numeric GID must be included")
	assert.Contains(t, context, "without search permission",
		"the blocking component diagnostic must be appended, not dropped")
}

// TestCwdFailureContextWithoutADiagnosableCause still names user and cwd: the
// kernel may refuse for a reason the permission bits do not show (an ACL, SELinux,
// a missing capability), and the message must not become uninformative or invent a
// cause in that case.
func TestCwdFailureContextWithoutADiagnosableCause(t *testing.T) {
	t.Parallel()

	// Make every component searchable, so the heuristic finds nothing to report.
	dir := t.TempDir()

	root := os.TempDir()
	for current := dir; strings.HasPrefix(current, root) && current != root; current = filepath.Dir(current) {
		require.NoError(t, os.Chmod(current, 0o777))
	}

	identity := &execcontext.Identity{
		UID:      60123,
		GID:      60124,
		Groups:   []uint32{60124},
		Username: "otheruser",
	}

	require.Empty(t, DescribeCwdAccess(dir, identity),
		"precondition: every component must look searchable for this case to be meaningful")

	context := CwdFailureContext(dir, identity)

	assert.Contains(t, context, "otheruser")
	assert.Contains(t, context, dir)
	assert.NotContains(t, context, "without search permission",
		"no cause should be invented when the bits look fine")
}

func TestCwdFailureContextWithNilIdentity(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()

	context := CwdFailureContext(dir, nil)

	assert.Contains(t, context, dir)
}

func currentIdentity(t *testing.T) *execcontext.Identity {
	t.Helper()

	identity := execcontext.CaptureStartupIdentity(nil)
	require.NotNil(t, identity)

	// The tests create files as the running (effective) user, so compare against
	// that rather than the real UID.
	identity.UID = uint32(os.Geteuid())
	identity.GID = uint32(os.Getegid())

	if identity.Username == "" {
		identity.Username = strconv.Itoa(os.Geteuid())
	}

	return identity
}

func statT(t *testing.T, info os.FileInfo) *syscall.Stat_t {
	t.Helper()

	stat, ok := info.Sys().(*syscall.Stat_t)
	require.True(t, ok, "expected a Linux stat structure")

	return stat
}

// TestGetSubpathsHandlesRelativePathsWithoutLooping guards a real hang: for a
// relative path filepath.Dir eventually returns "." forever, so a walk that
// stops only at "/" never terminates. DescribeCwdAccess is on the error path, so
// a hang there would turn a bad request into a stuck request.
func TestGetSubpathsHandlesRelativePathsWithoutLooping(t *testing.T) {
	t.Parallel()

	done := make(chan []string, 1)

	go func() {
		done <- getSubpaths("relative/path/here")
	}()

	select {
	case subpaths := <-done:
		require.NotEmpty(t, subpaths)

		for _, subpath := range subpaths {
			assert.True(t, filepath.IsAbs(subpath),
				"a relative input must be resolved to absolute components, got %q", subpath)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("getSubpaths did not terminate for a relative path")
	}
}

func TestGetSubpathsWalksAncestorsExcludingRoot(t *testing.T) {
	t.Parallel()

	assert.Equal(t,
		[]string{"/opt", "/opt/app", "/opt/app/work"},
		getSubpaths("/opt/app/work"),
		"ancestors must be root-most first, and / itself is not included")

	assert.Empty(t, getSubpaths("/"), "the root has no components below it")
}

func TestGetSubpathsCleansRedundantSegments(t *testing.T) {
	t.Parallel()

	assert.Equal(t,
		[]string{"/opt", "/opt/work"},
		getSubpaths("/opt/app/../work"))
}

// TestDescribeCwdAccessTerminatesForRelativePath is the caller-level version of
// the loop guard.
func TestDescribeCwdAccessTerminatesForRelativePath(t *testing.T) {
	t.Parallel()

	identity := &execcontext.Identity{UID: 60123, GID: 60124, Username: "otheruser"}

	done := make(chan string, 1)

	go func() {
		done <- DescribeCwdAccess("some/relative/dir", identity)
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("DescribeCwdAccess did not terminate for a relative path")
	}
}
