//go:build linux

package execcontext

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// The tests in context_test.go run in a process where the real and effective
// UID are usually identical, so they cannot distinguish "compares effective IDs"
// from "compares real IDs" — the two agree. That distinction is the whole point
// of the setuid contract: a setuid envd has ruid = OCI User and euid = 0, and an
// implementation comparing real IDs would decide no Credential is needed and
// hand the command a root effective UID.
//
// These tests create the real condition. The test binary re-executes itself
// through a root-owned mode-4755 wrapper under an unprivileged Credential, so
// the child genuinely runs with ruid != euid, and then asserts what
// CaptureStartupIdentity and MatchesCurrentProcess report in that state.
//
// They need root to chown/chmod the wrapper and are skipped otherwise. Set
// ENVD_SKIP_PRIVILEGED_TESTS=1 to skip them even as root.

const (
	setuidProbeEnv = "ENVD_SETUID_IDENTITY_PROBE"

	probeUID = 60321
	probeGID = 60322

	// Supplementary groups the probe child is given. The test process itself
	// usually has none beyond its primary group (a container is typically
	// `groups=0`), so without a child that really carries extra groups a snapshot
	// that silently dropped them would look correct.
	probeSupplementaryA = 60401
	probeSupplementaryB = 60402
)

type identityProbe struct {
	Username string `json:"username"`
	HomeDir  string `json:"home_dir"`

	CapturedGroups []uint32 `json:"captured_groups"`
	ProcessGroups  []int    `json:"process_groups"`

	RealUID      int    `json:"real_uid"`
	EffectiveUID int    `json:"effective_uid"`
	RealGID      int    `json:"real_gid"`
	EffectiveGID int    `json:"effective_gid"`
	CapturedUID  uint32 `json:"captured_uid"`
	CapturedGID  uint32 `json:"captured_gid"`

	// MatchesSelf is MatchesCurrentProcess() for the captured (real) identity.
	// Under setuid it must be false: the captured identity is the OCI user, the
	// effective identity is root, so a Credential is required.
	MatchesSelf bool `json:"matches_self"`

	// MatchesEffective is MatchesCurrentProcess() for an identity built from the
	// effective IDs. It must be true, confirming the comparison really does read
	// the effective identity.
	MatchesEffective bool `json:"matches_effective"`

	// DegradedMatchesSelf is MatchesCurrentProcess() for an identity that has the
	// effective UID and GID but only the primary group, as an unreadable
	// /etc/group would produce. It must be false: the process holds more groups,
	// so a Credential is still required.
	DegradedMatchesSelf bool `json:"degraded_matches_self"`
}

// TestMain lets the test binary act as its own probe when re-executed.
func TestMain(m *testing.M) {
	if os.Getenv(setuidProbeEnv) == "1" {
		emitIdentityProbe()

		return
	}

	os.Exit(m.Run())
}

func emitIdentityProbe() {
	captured := CaptureStartupIdentity(nil)

	processGroups, _ := os.Getgroups()

	effective := &Identity{
		UID:    uint32(os.Geteuid()),
		GID:    uint32(os.Getegid()),
		Groups: NormalizeGroups(currentEffectiveGroups()),
	}

	degraded := &Identity{
		UID:              uint32(os.Geteuid()),
		GID:              uint32(os.Getegid()),
		Groups:           []uint32{uint32(os.Getegid())},
		GroupsIncomplete: true,
	}

	probe := identityProbe{
		RealUID:          os.Getuid(),
		EffectiveUID:     os.Geteuid(),
		RealGID:          os.Getgid(),
		EffectiveGID:     os.Getegid(),
		ProcessGroups:    processGroups,
		CapturedUID:      captured.UID,
		CapturedGID:      captured.GID,
		CapturedGroups:   captured.Groups,
		Username:         captured.Username,
		HomeDir:          captured.HomeDir,
		MatchesSelf:      captured.MatchesCurrentProcess(),
		MatchesEffective: effective.MatchesCurrentProcess(),

		DegradedMatchesSelf: degraded.MatchesCurrentProcess(),
	}

	encoded, err := json.Marshal(probe)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode probe: %v\n", err)
		os.Exit(1)
	}

	fmt.Println(string(encoded))
	os.Exit(0)
}

func currentEffectiveGroups() []uint32 {
	current, _ := os.Getgroups()

	groups := make([]uint32, 0, len(current)+1)
	groups = append(groups, uint32(os.Getegid()))

	for _, group := range current {
		groups = append(groups, uint32(group))
	}

	return groups
}

// runUnderSetuid re-executes this test binary through a root-owned mode-4755
// wrapper, started as an unprivileged user, and returns what the child reported.
func runUnderSetuid(t *testing.T) identityProbe {
	t.Helper()

	if os.Getenv("ENVD_SKIP_PRIVILEGED_TESTS") == "1" {
		t.Skip("ENVD_SKIP_PRIVILEGED_TESTS=1: skipping setuid identity tests")
	}

	if os.Geteuid() != 0 {
		t.Skip("setuid identity tests need an effective UID of 0 to prepare the wrapper")
	}

	self, err := os.Executable()
	require.NoError(t, err)

	dir := t.TempDir()

	// Every ancestor up to the temp root needs the execute bit, otherwise the
	// unprivileged child cannot even reach the wrapper.
	root := os.TempDir()
	for current := dir; strings.HasPrefix(current, root) && current != root; current = filepath.Dir(current) {
		require.NoError(t, os.Chmod(current, 0o777))
	}

	// A tiny C-free wrapper: copy the test binary and mark it setuid root. Copying
	// avoids changing the mode of the binary the test framework is running.
	wrapper := filepath.Join(dir, "identity-probe")

	data, err := os.ReadFile(self)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(wrapper, data, 0o755))
	require.NoError(t, os.Chown(wrapper, 0, 0))
	require.NoError(t, os.Chmod(wrapper, os.ModeSetuid|0o755))

	info, err := os.Stat(wrapper)
	require.NoError(t, err)
	require.NotZero(t, info.Mode()&os.ModeSetuid,
		"the wrapper must be setuid or this test proves nothing")

	cmd := exec.Command(wrapper)
	cmd.Env = append(os.Environ(), setuidProbeEnv+"=1")
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Credential: &syscall.Credential{
			Uid: probeUID,
			Gid: probeGID,
			// Give the child real supplementary groups, so a snapshot that dropped
			// them is observable. The test process itself typically has none.
			Groups: []uint32{probeGID, probeSupplementaryA, probeSupplementaryB},
		},
	}

	output, err := cmd.Output()
	if err != nil {
		t.Skipf("could not execute the setuid probe (filesystem may be mounted nosuid): %v", err)
	}

	var probe identityProbe
	require.NoError(t, json.Unmarshal([]byte(strings.TrimSpace(string(output))), &probe),
		"probe output was: %q", output)

	return probe
}

// TestSetuidCaptureUsesRealIdentity is the contract under genuine setuid: the
// snapshot must describe the OCI user (real IDs), not envd's root effective
// identity.
func TestSetuidCaptureUsesRealIdentity(t *testing.T) {
	probe := runUnderSetuid(t)

	require.NotEqual(t, probe.RealUID, probe.EffectiveUID,
		"the probe must genuinely run setuid for this test to mean anything")
	assert.Equal(t, probeUID, probe.RealUID)
	assert.Equal(t, 0, probe.EffectiveUID, "a root-owned 4755 binary must yield euid 0")

	assert.Equal(t, uint32(probeUID), probe.CapturedUID,
		"the captured identity must be the OCI real UID, not the effective root UID")
	assert.Equal(t, uint32(probeGID), probe.CapturedGID)
	assert.NotEqual(t, uint32(0), probe.CapturedUID,
		"root must never be recorded as the OCI startup identity")
}

// TestSetuidMatchesCurrentProcessReadsEffectiveIdentity is the assertion the
// non-privileged tests cannot make: with ruid != euid, an identity equal to the
// real IDs must NOT match, while one equal to the effective IDs must. This is
// what forces the default command to get a Credential and drop privileges.
func TestSetuidMatchesCurrentProcessReadsEffectiveIdentity(t *testing.T) {
	probe := runUnderSetuid(t)

	require.NotEqual(t, probe.RealUID, probe.EffectiveUID,
		"the probe must genuinely run setuid for this test to mean anything")

	assert.False(t, probe.MatchesSelf,
		"the captured (real) identity must not match the effective identity under setuid; "+
			"returning true here would skip the Credential and leak a root effective UID")

	assert.True(t, probe.MatchesEffective,
		"an identity equal to the effective identity must match, proving the comparison "+
			"reads the effective IDs rather than the real ones")
}

// TestSetuidCaptureFallsBackToDecimalUsername covers the numeric-OCI-User case
// under setuid: uid 60321 has no passwd entry, so the display name is its
// decimal form and HOME must not become root's home.
func TestSetuidCaptureFallsBackToDecimalUsername(t *testing.T) {
	probe := runUnderSetuid(t)

	assert.Equal(t, strconv.Itoa(probeUID), probe.Username,
		"a UID without a passwd entry must be named by its decimal UID")
	assert.NotEqual(t, "/root", probe.HomeDir,
		"a setuid envd must not adopt root's home directory")
	assert.NotEqual(t, "root", probe.Username)
}

// TestSetuidCapturePreservesGroups is the coverage that a same-process test
// cannot provide: the probe child really carries supplementary groups, so a
// snapshot that dropped them fails here. In a typical container the test process
// itself has only group 0, which would make the omission invisible.
func TestSetuidCapturePreservesGroups(t *testing.T) {
	probe := runUnderSetuid(t)

	require.Greater(t, len(probe.ProcessGroups), 1,
		"the probe child must really carry supplementary groups for this test to bite")

	assert.Contains(t, probe.CapturedGroups, uint32(probeGID),
		"the primary GID must be part of the captured group list")

	for _, want := range []uint32{probeSupplementaryA, probeSupplementaryB} {
		assert.Contains(t, probe.CapturedGroups, want,
			"supplementary group %d applied by the runtime must appear in the snapshot", want)
	}

	assert.NotContains(t, probe.CapturedGroups, uint32(0),
		"group 0 must not appear in the captured identity of an unprivileged OCI user")

	// Every group the kernel reports must be in the snapshot: this is what makes a
	// silent drop detectable rather than merely unlikely.
	for _, group := range probe.ProcessGroups {
		assert.Contains(t, probe.CapturedGroups, uint32(group),
			"kernel-reported group %d must be preserved", group)
	}

	assert.Equal(t, NormalizeGroups(probe.CapturedGroups), probe.CapturedGroups,
		"captured groups must be deduplicated and sorted")
}

// TestSetuidCaptureIgnoresPasswdGID is the assertion a same-process test cannot
// make: the passwd lookup must enrich only the display name and home directory,
// never the numeric identity.
//
// In an ordinary test process the passwd GID and the runtime GID agree, so an
// implementation that overwrote GID from passwd would still look correct. The
// probe child runs with a GID that deliberately differs from any passwd entry for
// its UID, which makes the overwrite observable.
func TestSetuidCaptureIgnoresPasswdGID(t *testing.T) {
	probe := runUnderSetuid(t)

	assert.Equal(t, uint32(probeGID), probe.CapturedGID,
		"the captured GID must be the runtime GID, never a GID read from passwd")

	// The probe UID has no passwd entry at all, so any GID coming from a lookup
	// would be wrong by construction.
	assert.Equal(t, strconv.Itoa(probeUID), probe.Username,
		"a UID with no passwd entry must keep its decimal display name")

	assert.NotEqual(t, uint32(0), probe.CapturedGID,
		"root's GID must never be substituted for the runtime GID")
}

// TestSetuidDegradedIdentityDoesNotMatchProcess is the group-loss leak, proven in
// a process that really holds supplementary groups.
//
// An identity that lost its supplementary groups must NOT be mistaken for the
// current process just because the primary IDs agree: matching would skip the
// Credential and hand the command the current effective identity. An ordinary test
// process typically has no extra groups, so only the probe child can show this.
func TestSetuidDegradedIdentityDoesNotMatchProcess(t *testing.T) {
	probe := runUnderSetuid(t)

	require.Greater(t, len(probe.ProcessGroups), 1,
		"the probe child must hold supplementary groups for this test to bite")

	assert.False(t, probe.DegradedMatchesSelf,
		"an identity holding only the primary group must not match a process that "+
			"holds more groups; matching would skip the Credential")

	assert.True(t, probe.MatchesEffective,
		"control: the complete effective identity must still match")
}
