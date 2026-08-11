//go:build linux

package handler

import (
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
	rpc "github.com/e2b-dev/infra/packages/envd/internal/services/spec/process"
)

// The unit tests in handler_test.go assert on the exec.Cmd that would be
// started. They cannot prove the resulting process really has the intended
// identity, because changing UID requires privileges.
//
// The tests here do prove it, by actually starting processes under a real
// Credential and reading the identity the kernel gave them. They need root and
// are skipped otherwise, so `make test` stays runnable for an unprivileged
// developer while CI (which runs as root in the golang container) exercises
// them.
//
// Set ENVD_SKIP_PRIVILEGED_TESTS=1 to skip them even as root.

const (
	// A UID/GID pair that is very unlikely to collide with a real account in the
	// test container, so the assertions describe this test's own process.
	testTargetUID = 60123
	testTargetGID = 60124

	testSupplementaryGroupA = 60201
	testSupplementaryGroupB = 60202
)

func requirePrivileged(t *testing.T) {
	t.Helper()

	if os.Getenv("ENVD_SKIP_PRIVILEGED_TESTS") == "1" {
		t.Skip("ENVD_SKIP_PRIVILEGED_TESTS=1: skipping privileged identity tests")
	}

	if os.Geteuid() != 0 {
		t.Skip("privileged identity tests need an effective UID of 0 to set credentials")
	}
}

// runAndCapture starts the request through the real handler and returns the
// process's stdout, so the identity assertions read what the kernel actually
// applied rather than what the request asked for.
func runAndCapture(t *testing.T, identity *execcontext.Identity, req *rpc.StartRequest, defaults *execcontext.Defaults) string {
	t.Helper()

	h, err := newHandler(t, identity, req, defaults)
	require.NoError(t, err)

	data, dataCancel := h.DataEvent.Fork()
	defer dataCancel()

	_, err = h.Start(0)
	require.NoError(t, err)

	go h.Wait()

	var out strings.Builder

	for event := range data {
		out.Write(event.Data.GetStdout())
		out.Write(event.Data.GetStderr())
	}

	return out.String()
}

func identityProbeRequest(cwd *string) *rpc.StartRequest {
	// `id -u`, `id -g`, and the supplementary group list, one value per line, plus
	// the directory the process actually landed in.
	script := `printf 'uid=%s\n' "$(id -u)"; printf 'gid=%s\n' "$(id -g)"; printf 'groups=%s\n' "$(id -G)"; printf 'pwd=%s\n' "$(pwd)"; printf 'PWD=%s\n' "$PWD"`

	return startRequest("/bin/sh", []string{"-c", script}, cwd, nil)
}

func parseProbe(t *testing.T, output string) map[string]string {
	t.Helper()

	values := map[string]string{}

	for _, line := range strings.Split(strings.TrimSpace(output), "\n") {
		key, value, ok := strings.Cut(strings.TrimSpace(line), "=")
		if ok {
			values[key] = value
		}
	}

	require.Contains(t, values, "uid", "probe output was: %q", output)

	return values
}

// traversableDir returns a directory an unprivileged target UID can actually
// enter. t.TempDir() creates its per-test parent as 0700 owned by the test user,
// so a dropped process cannot traverse into it; every ancestor up to the temp
// root therefore needs the execute bit as well.
func traversableDir(t *testing.T) string {
	t.Helper()

	dir := t.TempDir()

	// Walk up to the process temp root, granting search to everyone. Only the
	// per-run test directories are touched, all of which Go removes afterwards.
	root := os.TempDir()
	for current := dir; strings.HasPrefix(current, root) && current != root; current = filepath.Dir(current) {
		require.NoError(t, os.Chmod(current, 0o777))
	}

	return dir
}

// TestPrivilegedDefaultCommandDropsToTargetIdentity is the setuid default path
// proven for real: envd runs with effective UID 0, the target is a different
// UID, and the started process must actually end up as that UID with exactly the
// intended groups.
func TestPrivilegedDefaultCommandDropsToTargetIdentity(t *testing.T) {
	requirePrivileged(t)

	workdir := traversableDir(t)

	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      testTargetUID,
		GID:      testTargetGID,
		Groups:   execcontext.NormalizeGroups([]uint32{testTargetGID, testSupplementaryGroupA, testSupplementaryGroupB}),
		Username: strconv.Itoa(testTargetUID),
		HomeDir:  workdir,
	}

	probe := parseProbe(t, runAndCapture(t, target, identityProbeRequest(nil), defaults))

	assert.Equal(t, strconv.Itoa(testTargetUID), probe["uid"],
		"the process must run as the target UID, not as envd's effective root")
	assert.Equal(t, strconv.Itoa(testTargetGID), probe["gid"])

	gotGroups := strings.Fields(probe["groups"])
	for _, want := range []int{testTargetGID, testSupplementaryGroupA, testSupplementaryGroupB} {
		assert.Contains(t, gotGroups, strconv.Itoa(want),
			"supplementary group %d must be applied to the process", want)
	}

	assert.NotContains(t, gotGroups, "0",
		"group 0 must not survive the drop to an unprivileged identity")
}

// TestPrivilegedNoRootEUIDLeak is the leak check stated as its own assertion:
// after the drop, the process must not be able to act as root.
func TestPrivilegedNoRootEUIDLeak(t *testing.T) {
	requirePrivileged(t)

	workdir := traversableDir(t)

	rootOnly := workdir + "/root-only"
	require.NoError(t, os.Mkdir(rootOnly, 0o700))
	require.NoError(t, os.Chown(rootOnly, 0, 0))

	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      testTargetUID,
		GID:      testTargetGID,
		Groups:   []uint32{testTargetGID},
		Username: strconv.Itoa(testTargetUID),
		HomeDir:  workdir,
	}

	// `id -u` reports the real UID; `id -un`-independent euid check uses the
	// shell's own view. Reading a root-only directory is the behavioral proof.
	script := `printf 'euid=%s\n' "$(id -u)"; if ls ` + rootOnly + ` >/dev/null 2>&1; then printf 'root_dir=readable\n'; else printf 'root_dir=denied\n'; fi`

	out := runAndCapture(t, target, startRequest("/bin/sh", []string{"-c", script}, nil, nil), defaults)
	probe := map[string]string{}

	for _, line := range strings.Split(strings.TrimSpace(out), "\n") {
		key, value, ok := strings.Cut(strings.TrimSpace(line), "=")
		if ok {
			probe[key] = value
		}
	}

	assert.Equal(t, strconv.Itoa(testTargetUID), probe["euid"])
	assert.Equal(t, "denied", probe["root_dir"],
		"a dropped process must not retain root's ability to read a 0700 root-owned directory")
}

// TestPrivilegedExplicitRootRunsAsRoot is the explicit-user path: an explicit
// root request must actually execute as root.
func TestPrivilegedExplicitRootRunsAsRoot(t *testing.T) {
	requirePrivileged(t)

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	rootIdentity, err := execcontext.IdentityForUsername("root")
	require.NoError(t, err)

	probe := parseProbe(t, runAndCapture(t, rootIdentity, identityProbeRequest(nil), defaults))

	assert.Equal(t, "0", probe["uid"])
	assert.Equal(t, "0", probe["gid"])
}

// TestPrivilegedExplicitCwdAndPWDConsistency proves cmd.Dir and PWD agree in a
// real process for both the default and explicit cwd.
func TestPrivilegedExplicitCwdAndPWDConsistency(t *testing.T) {
	requirePrivileged(t)

	startupCwd := traversableDir(t)
	explicit := traversableDir(t)

	defaults := &execcontext.Defaults{
		Workdir: &startupCwd,
		EnvVars: execcontext.EnvironmentSnapshot([]string{"PWD=/stale/from/envd"}),
	}

	target := &execcontext.Identity{
		UID:      testTargetUID,
		GID:      testTargetGID,
		Groups:   []uint32{testTargetGID},
		Username: strconv.Itoa(testTargetUID),
		HomeDir:  startupCwd,
	}

	t.Run("default cwd is the startup cwd", func(t *testing.T) {
		probe := parseProbe(t, runAndCapture(t, target, identityProbeRequest(nil), defaults))

		assert.Equal(t, startupCwd, probe["pwd"])
		assert.Equal(t, startupCwd, probe["PWD"])
		assert.NotEqual(t, "/stale/from/envd", probe["PWD"])
	})

	t.Run("explicit cwd wins and PWD follows", func(t *testing.T) {
		probe := parseProbe(t, runAndCapture(t, target, identityProbeRequest(&explicit), defaults))

		assert.Equal(t, explicit, probe["pwd"])
		assert.Equal(t, explicit, probe["PWD"], "PWD must follow an explicit cwd")
	})
}

// TestPrivilegedNumericUIDWithoutPasswdEntryExecutes covers business image B for
// real: a UID with no passwd entry must still run.
func TestPrivilegedNumericUIDWithoutPasswdEntryExecutes(t *testing.T) {
	requirePrivileged(t)

	// Confirm the UID genuinely has no passwd entry, so the test means what it
	// claims.
	if _, err := user.LookupId(strconv.Itoa(testTargetUID)); err == nil {
		t.Skipf("uid %d unexpectedly has a passwd entry in this environment", testTargetUID)
	}

	workdir := traversableDir(t)

	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      testTargetUID,
		GID:      testTargetGID,
		Groups:   []uint32{testTargetGID},
		Username: strconv.Itoa(testTargetUID), // decimal fallback
		HomeDir:  workdir,
	}

	probe := parseProbe(t, runAndCapture(t, target, identityProbeRequest(nil), defaults))

	assert.Equal(t, strconv.Itoa(testTargetUID), probe["uid"],
		"a UID without a passwd entry must still execute with that UID")
	assert.Equal(t, workdir, probe["pwd"])
}

// TestPrivilegedSameIdentityInheritsWithoutSetgroups proves the no-redundant-
// setgroups path works in a real process: running as envd's own identity must
// succeed without a Credential.
func TestPrivilegedSameIdentityInheritsWithoutSetgroups(t *testing.T) {
	requirePrivileged(t)

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	identity := currentIdentity(t)

	h, err := newHandler(t, identity, identityProbeRequest(nil), defaults)
	require.NoError(t, err)
	require.Nil(t, h.cmd.SysProcAttr.Credential, "no Credential should be needed here")

	probe := parseProbe(t, runAndCapture(t, identity, identityProbeRequest(nil), defaults))

	assert.Equal(t, strconv.Itoa(os.Geteuid()), probe["uid"])
	assert.Equal(t, workdir, probe["pwd"])
}

// TestPrivilegedRealSetuidBinaryIdentity is the closest local analogue of the
// AGS deployment: a root-owned mode-4755 helper executed by a non-root user, so
// the kernel produces ruid=<user>, euid=0 — exactly the state envd runs in
// behind an Image Volume mount. It verifies the identity envd would capture in
// that state (real UID, not effective).
func TestPrivilegedRealSetuidBinaryIdentity(t *testing.T) {
	requirePrivileged(t)

	if _, err := exec.LookPath("go"); err != nil {
		t.Skip("go toolchain not available to build the setuid probe")
	}

	dir := traversableDir(t)

	source := dir + "/probe.go"
	probeSource := `package main

import (
	"fmt"
	"os"
)

func main() {
	groups, _ := os.Getgroups()
	fmt.Printf("ruid=%d\neuid=%d\nrgid=%d\negid=%d\ngroups=%v\n",
		os.Getuid(), os.Geteuid(), os.Getgid(), os.Getegid(), groups)
}
`
	require.NoError(t, os.WriteFile(source, []byte(probeSource), 0o644))

	binary := dir + "/probe"
	build := exec.Command("go", "build", "-o", binary, source)
	build.Env = append(os.Environ(), "GOCACHE=/tmp/go-build", "GOFLAGS=")

	if output, err := build.CombinedOutput(); err != nil {
		t.Skipf("could not build the setuid probe: %v: %s", err, output)
	}

	// Root-owned, mode 4755: the same file metadata the Image Volume artifact
	// must provide.
	require.NoError(t, os.Chown(binary, 0, 0))
	require.NoError(t, os.Chmod(binary, os.ModeSetuid|0o755))

	info, err := os.Stat(binary)
	require.NoError(t, err)
	require.NotZero(t, info.Mode()&os.ModeSetuid, "the probe must be setuid for this test to mean anything")

	// Execute it as an unprivileged user, the way the OCI runtime executes envd.
	run := exec.Command(binary)
	run.SysProcAttr = &syscall.SysProcAttr{
		Credential: &syscall.Credential{
			Uid:    testTargetUID,
			Gid:    testTargetGID,
			Groups: []uint32{testTargetGID},
		},
	}

	output, err := run.CombinedOutput()
	if err != nil {
		t.Skipf("could not execute the setuid probe (filesystem may be mounted nosuid): %v: %s", err, output)
	}

	probe := map[string]string{}

	for _, line := range strings.Split(strings.TrimSpace(string(output)), "\n") {
		key, value, ok := strings.Cut(strings.TrimSpace(line), "=")
		if ok {
			probe[key] = value
		}
	}

	assert.Equal(t, strconv.Itoa(testTargetUID), probe["ruid"],
		"setuid must preserve the invoking (OCI) real UID")
	assert.Equal(t, "0", probe["euid"],
		"setuid on a root-owned 4755 binary must give effective UID 0")
	assert.Equal(t, strconv.Itoa(testTargetGID), probe["rgid"])

	// This is the state that made the original implementation wrong: reading the
	// effective UID here would record root as the OCI User.
	assert.NotEqual(t, probe["ruid"], probe["euid"],
		"the test is only meaningful when real and effective UID differ")
}

// TestPrivilegedUnreachableCwdFailsWithUserAndCwdContext is acceptance case A7
// proven end to end: the kernel refuses to start the process in a directory the
// target user cannot search, and envd's error names both the user and the cwd.
func TestPrivilegedUnreachableCwdFailsWithUserAndCwdContext(t *testing.T) {
	requirePrivileged(t)

	base := traversableDir(t)

	private := filepath.Join(base, "appuser-only")
	require.NoError(t, os.Mkdir(private, 0o700))
	require.NoError(t, os.Chown(private, 0, 0))

	defaults := &execcontext.Defaults{
		Workdir: &base,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      testTargetUID,
		GID:      testTargetGID,
		Groups:   []uint32{testTargetGID},
		Username: "otheruser",
		HomeDir:  base,
	}

	h, err := newHandler(t, target, identityProbeRequest(&private), defaults)
	require.NoError(t, err,
		"envd must not pre-judge the kernel: construction succeeds and the kernel decides")

	_, err = h.Start(0)

	require.Error(t, err, "the kernel must refuse a directory this user cannot search")
	assert.Contains(t, err.Error(), "otheruser", "the error must name the target user")
	assert.Contains(t, err.Error(), private, "the error must name the cwd")
	assert.Contains(t, err.Error(), "without search permission",
		"the diagnostic should point at the blocking component")
}

// TestPrivilegedUnreachableAncestorFailsWithContext is the case a leaf-only check
// misses: the cwd itself is world-searchable but a parent is not. The error must
// still name the user, the cwd, and the blocking ancestor.
func TestPrivilegedUnreachableAncestorFailsWithContext(t *testing.T) {
	requirePrivileged(t)

	base := traversableDir(t)

	lockedParent := filepath.Join(base, "locked-parent")
	require.NoError(t, os.Mkdir(lockedParent, 0o700))
	require.NoError(t, os.Chown(lockedParent, 0, 0))

	openLeaf := filepath.Join(lockedParent, "open-leaf")
	require.NoError(t, os.Mkdir(openLeaf, 0o777))

	defaults := &execcontext.Defaults{
		Workdir: &base,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      testTargetUID,
		GID:      testTargetGID,
		Groups:   []uint32{testTargetGID},
		Username: "otheruser",
		HomeDir:  base,
	}

	h, err := newHandler(t, target, identityProbeRequest(&openLeaf), defaults)
	require.NoError(t, err)

	_, err = h.Start(0)

	require.Error(t, err,
		"a 0700 ancestor must still prevent the process from starting, even with a 0777 leaf")
	assert.Contains(t, err.Error(), "otheruser")
	assert.Contains(t, err.Error(), openLeaf, "the requested cwd must be named")
	assert.Contains(t, err.Error(), lockedParent,
		"the blocking ancestor must be named, which a leaf-only check would miss")
}
