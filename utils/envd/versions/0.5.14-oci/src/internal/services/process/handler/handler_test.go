package handler

import (
	"bytes"
	"context"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
	"testing"

	"connectrpc.com/connect"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
	"github.com/e2b-dev/infra/packages/envd/internal/services/cgroups"
	rpc "github.com/e2b-dev/infra/packages/envd/internal/services/spec/process"
)

func testLogger() *zerolog.Logger {
	logger := zerolog.Nop()

	return &logger
}

// capturingLogger returns a logger writing into buf, so a test can assert that a
// warning was actually emitted rather than assuming it.
func capturingLogger(buf *bytes.Buffer) *zerolog.Logger {
	logger := zerolog.New(buf)

	return &logger
}

// newHandlerWithLogger is newHandler with an explicit logger.
func newHandlerWithLogger(
	t *testing.T,
	logger *zerolog.Logger,
	identity *execcontext.Identity,
	req *rpc.StartRequest,
	defaults *execcontext.Defaults,
) (*Handler, error) {
	t.Helper()

	ctx, cancel := context.WithCancel(t.Context())
	t.Cleanup(cancel)

	return New(ctx, identity, req, logger, defaults, cgroups.NewNoopManager(), cancel)
}

// currentIdentity is the identity a child process would inherit without any
// Credential: envd's effective IDs and current group list.
func currentIdentity(t *testing.T) *execcontext.Identity {
	t.Helper()

	current, err := os.Getgroups()
	require.NoError(t, err)

	groups := make([]uint32, 0, len(current)+1)
	groups = append(groups, uint32(os.Getegid()))

	for _, group := range current {
		groups = append(groups, uint32(group))
	}

	return &execcontext.Identity{
		UID:      uint32(os.Geteuid()),
		GID:      uint32(os.Getegid()),
		Groups:   execcontext.NormalizeGroups(groups),
		Username: "envd-effective",
		HomeDir:  "/home/envd-effective",
	}
}

func startRequest(cmd string, args []string, cwd *string, envs map[string]string) *rpc.StartRequest {
	if envs == nil {
		envs = map[string]string{}
	}

	return &rpc.StartRequest{
		Process: &rpc.ProcessConfig{
			Cmd:  cmd,
			Args: args,
			Cwd:  cwd,
			Envs: envs,
		},
	}
}

func newHandler(
	t *testing.T,
	identity *execcontext.Identity,
	req *rpc.StartRequest,
	defaults *execcontext.Defaults,
) (*Handler, error) {
	t.Helper()

	ctx, cancel := context.WithCancel(t.Context())
	t.Cleanup(cancel)

	return New(ctx, identity, req, testLogger(), defaults, cgroups.NewNoopManager(), cancel)
}

func envValue(cmd *exec.Cmd, key string) (string, bool) {
	prefix := key + "="
	value := ""
	found := false

	// Later entries win, matching exec's own semantics.
	for _, entry := range cmd.Env {
		if strings.HasPrefix(entry, prefix) {
			value = strings.TrimPrefix(entry, prefix)
			found = true
		}
	}

	return value, found
}

// TestHandlerInheritsCredentialsForMatchingIdentity is the unprivileged-envd
// case: when the target is already envd's effective identity, no Credential is
// set, so the child does not require the privileges setgroups needs.
func TestHandlerInheritsCredentialsForMatchingIdentity(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir:         &workdir,
		EnvVars:         execcontext.EnvironmentSnapshot(nil),
		StartupIdentity: currentIdentity(t),
	}

	h, err := newHandler(t, currentIdentity(t), startRequest("/bin/true", nil, nil, nil), defaults)

	require.NoError(t, err)
	assert.Nil(t, h.cmd.SysProcAttr.Credential,
		"a target equal to envd's effective identity must not trigger setgroups")
}

// TestHandlerSetsCredentialForDifferentUID is the setuid default path in
// miniature: the target differs from the effective identity, so envd must set a
// Credential and drop privileges rather than letting the child inherit euid 0.
func TestHandlerSetsCredentialForDifferentUID(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      10001,
		GID:      10001,
		Groups:   []uint32{10001, 20001},
		Username: "appuser",
		HomeDir:  "/home/appuser",
	}

	h, err := newHandler(t, target, startRequest("/bin/true", nil, nil, nil), defaults)

	require.NoError(t, err)
	require.NotNil(t, h.cmd.SysProcAttr.Credential, "a differing identity must set a Credential")
	assert.Equal(t, uint32(10001), h.cmd.SysProcAttr.Credential.Uid)
	assert.Equal(t, uint32(10001), h.cmd.SysProcAttr.Credential.Gid)
	assert.Equal(t, []uint32{10001, 20001}, h.cmd.SysProcAttr.Credential.Groups,
		"the resolved groups must be used verbatim, not rebuilt from a username")
}

// TestHandlerSetsCredentialWhenOnlyGroupsDiffer catches the subtler leak: same
// UID and GID, but a different supplementary group set still requires a
// Credential, otherwise the child keeps envd's groups.
func TestHandlerSetsCredentialWhenOnlyGroupsDiffer(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := currentIdentity(t)
	target.Groups = execcontext.NormalizeGroups(append(slices.Clone(target.Groups), 65099))

	h, err := newHandler(t, target, startRequest("/bin/true", nil, nil, nil), defaults)

	require.NoError(t, err)
	require.NotNil(t, h.cmd.SysProcAttr.Credential,
		"a differing group list must not be ignored just because UID and GID match")
	assert.Contains(t, h.cmd.SysProcAttr.Credential.Groups, uint32(65099))
}

// TestHandlerSetsCredentialForRealUIDMatchUnderSetuid models the exact bug the
// spec forbids. It simulates a setuid envd by constructing a target equal to the
// *real* IDs while the process's effective IDs differ. The decision must be
// driven by the effective identity, so a Credential is still required.
func TestHandlerSetsCredentialForRealUIDMatchUnderSetuid(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	// A distinct UID stands in for "the OCI real UID under a setuid envd whose
	// effective UID is 0". It differs from the effective UID, so the Credential
	// must be set — an implementation comparing real IDs would skip it.
	ociUID := uint32(os.Geteuid()) + 4242
	target := &execcontext.Identity{
		UID:      ociUID,
		GID:      ociUID,
		Groups:   []uint32{ociUID},
		Username: "oci-user",
		HomeDir:  "/opt/app/work",
	}

	h, err := newHandler(t, target, startRequest("/bin/true", nil, nil, nil), defaults)

	require.NoError(t, err)
	require.NotNil(t, h.cmd.SysProcAttr.Credential,
		"the default command must drop privileges back to the OCI identity")
	assert.Equal(t, ociUID, h.cmd.SysProcAttr.Credential.Uid,
		"the child must run as the OCI UID, not as envd's effective root")
}

func TestHandlerUsesStartupCwdWithoutRequestedCwd(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	h, err := newHandler(t, currentIdentity(t), startRequest("/bin/true", nil, nil, nil), defaults)

	require.NoError(t, err)
	assert.Equal(t, workdir, h.cmd.Dir, "the captured startup cwd must be the default")
}

func TestHandlerPrefersExplicitCwd(t *testing.T) {
	t.Parallel()

	startupCwd := t.TempDir()
	explicit := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &startupCwd,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	h, err := newHandler(t, currentIdentity(t), startRequest("/bin/true", nil, &explicit, nil), defaults)

	require.NoError(t, err)
	assert.Equal(t, explicit, h.cmd.Dir)
}

// TestHandlerDoesNotFallBackToHomeDirForCwd pins the Workdir regression: with a
// captured startup cwd the default must not become the user's home directory.
func TestHandlerDoesNotFallBackToHomeDirForCwd(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	identity := currentIdentity(t)
	identity.HomeDir = "/home/should-not-be-used"

	h, err := newHandler(t, identity, startRequest("/bin/true", nil, nil, nil), defaults)

	require.NoError(t, err)
	assert.Equal(t, workdir, h.cmd.Dir)
	assert.NotEqual(t, identity.HomeDir, h.cmd.Dir)
}

// TestHandlerPWDMatchesCmdDir is the consistency requirement: the child's PWD
// must describe the directory it actually starts in.
func TestHandlerPWDMatchesCmdDir(t *testing.T) {
	t.Parallel()

	startupCwd := t.TempDir()
	explicit := t.TempDir()

	tests := []struct {
		requested *string
		name      string
		wantDir   string
	}{
		{name: "default cwd", requested: nil, wantDir: startupCwd},
		{name: "explicit cwd", requested: &explicit, wantDir: explicit},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			defaults := &execcontext.Defaults{
				Workdir: &startupCwd,
				// A stale PWD in the startup snapshot, as envd's own environment
				// would carry after an explicit cwd is requested.
				EnvVars: execcontext.EnvironmentSnapshot([]string{"PWD=/stale/from/envd"}),
			}

			h, err := newHandler(t, currentIdentity(t), startRequest("/bin/true", nil, tc.requested, nil), defaults)

			require.NoError(t, err)
			assert.Equal(t, tc.wantDir, h.cmd.Dir)

			pwd, ok := envValue(h.cmd, "PWD")
			require.True(t, ok, "PWD must be set for the child")
			assert.Equal(t, h.cmd.Dir, pwd, "PWD must equal cmd.Dir")
			assert.NotEqual(t, "/stale/from/envd", pwd,
				"the stale PWD from envd's own environment must be replaced")
		})
	}
}

// TestHandlerRequestEnvOverridesPWD documents the precedence: request-level
// environment variables still win, matching the existing env contract.
func TestHandlerRequestEnvOverridesPWD(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	req := startRequest("/bin/true", nil, nil, map[string]string{"PWD": "/explicit/from/request"})

	h, err := newHandler(t, currentIdentity(t), req, defaults)

	require.NoError(t, err)
	assert.Equal(t, workdir, h.cmd.Dir, "cmd.Dir must still be the resolved path")

	pwd, ok := envValue(h.cmd, "PWD")
	require.True(t, ok)
	assert.Equal(t, "/explicit/from/request", pwd,
		"a request-level PWD keeps the existing override semantics")
}

// TestHandlerStartupEnvironmentIsInherited guards the pre-existing capability
// that must not regress.
func TestHandlerStartupEnvironmentIsInherited(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot([]string{
			"OCI_IMAGE_VAR=from-image",
			"OVERRIDDEN=default-value",
		}),
	}

	req := startRequest("/bin/true", nil, nil, map[string]string{"OVERRIDDEN": "request-value"})

	h, err := newHandler(t, currentIdentity(t), req, defaults)
	require.NoError(t, err)

	inherited, ok := envValue(h.cmd, "OCI_IMAGE_VAR")
	require.True(t, ok, "startup environment must be inherited")
	assert.Equal(t, "from-image", inherited)

	overridden, ok := envValue(h.cmd, "OVERRIDDEN")
	require.True(t, ok)
	assert.Equal(t, "request-value", overridden, "request env must override startup env")
}

func TestHandlerSetsIdentityEnvironment(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	identity := currentIdentity(t)
	identity.Username = "appuser"
	identity.HomeDir = "/home/appuser"

	h, err := newHandler(t, identity, startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)

	home, ok := envValue(h.cmd, "HOME")
	require.True(t, ok)
	assert.Equal(t, "/home/appuser", home)

	user, ok := envValue(h.cmd, "USER")
	require.True(t, ok)
	assert.Equal(t, "appuser", user)

	logname, ok := envValue(h.cmd, "LOGNAME")
	require.True(t, ok)
	assert.Equal(t, "appuser", logname)
}

func TestHandlerRejectsMissingCwd(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	missing := filepath.Join(workdir, "does-not-exist")
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	_, err := newHandler(t, currentIdentity(t), startRequest("/bin/true", nil, &missing, nil), defaults)

	require.Error(t, err)
	assert.Equal(t, connect.CodeInvalidArgument, connect.CodeOf(err))
	assert.Contains(t, err.Error(), missing, "the error must name the directory")
}

// TestHandlerStartFailureNamesUserAndCwd asserts that a start failure carries the
// user and cwd context.
//
// It runs only with an effective UID of 0. Without privileges, setting any
// Credential fails with EPERM regardless of the directory, so the test would pass
// for the wrong reason and prove nothing about the cwd. The privileged Linux
// tests cover the same behavior for a genuinely unreachable directory and for an
// unreachable ancestor.
func TestHandlerStartFailureNamesUserAndCwd(t *testing.T) {
	t.Parallel()

	if os.Geteuid() != 0 {
		t.Skip("setting a Credential needs an effective UID of 0; " +
			"without it every start fails with EPERM and the cwd cause is not isolated")
	}

	base := t.TempDir()

	root := os.TempDir()
	for current := base; strings.HasPrefix(current, root) && current != root; current = filepath.Dir(current) {
		require.NoError(t, os.Chmod(current, 0o777))
	}
	private := filepath.Join(base, "private")
	require.NoError(t, os.Mkdir(private, 0o700))
	require.NoError(t, os.Chown(private, 0, 0))

	defaults := &execcontext.Defaults{
		Workdir: &base,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      60123,
		GID:      60124,
		Groups:   []uint32{60124},
		Username: "otheruser",
		HomeDir:  base,
	}

	// Control: the same identity in a world-searchable directory must succeed, so
	// a failure below is attributable to the directory and not to the Credential.
	control, err := newHandler(t, target, startRequest("/bin/true", nil, &base, nil), defaults)
	require.NoError(t, err)
	_, err = control.Start(0)
	require.NoError(t, err,
		"control: this identity must be able to start in a world-searchable cwd")

	h, err := newHandler(t, target, startRequest("/bin/true", nil, &private, nil), defaults)
	require.NoError(t, err, "handler construction must not pre-judge the kernel's decision")

	_, err = h.Start(0)

	require.Error(t, err, "the kernel must refuse to enter a directory this user cannot search")
	assert.Contains(t, err.Error(), "otheruser", "the error must name the target user")
	assert.Contains(t, err.Error(), private, "the error must name the cwd")
}

// TestStartErrorCodeMapsPermissionRefusal pins the Connect code a permission
// refusal produces, so a caller can tell "this user cannot run here" apart from
// "the request was malformed".
func TestStartErrorCodeMapsPermissionRefusal(t *testing.T) {
	t.Parallel()

	assert.Equal(t, connect.CodePermissionDenied,
		StartErrorCode(&fs.PathError{Op: "fork/exec", Path: "/bin/sh", Err: syscall.EACCES}),
		"EACCES from exec must map to PermissionDenied")

	assert.Equal(t, connect.CodePermissionDenied,
		StartErrorCode(&fs.PathError{Op: "fork/exec", Path: "/bin/sh", Err: syscall.EPERM}),
		"EPERM from exec must map to PermissionDenied")

	assert.Equal(t, connect.CodeInvalidArgument,
		StartErrorCode(&fs.PathError{Op: "fork/exec", Path: "/nope", Err: syscall.ENOENT}),
		"a missing executable is an argument problem, not a permission problem")

	assert.Equal(t, connect.CodeInvalidArgument,
		StartErrorCode(errors.New("some other failure")))
}

// TestHandlerDoesNotPreJudgeKernelPermission guards against the regression this
// design avoids: envd must not deny a request based on permission bits alone,
// because the kernel also honors POSIX ACLs, SELinux, and capabilities that the
// bits do not show.
func TestHandlerDoesNotPreJudgeKernelPermission(t *testing.T) {
	t.Parallel()

	private := filepath.Join(t.TempDir(), "private")
	require.NoError(t, os.Mkdir(private, 0o700))

	defaults := &execcontext.Defaults{
		Workdir: &private,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      60123,
		GID:      60124,
		Groups:   []uint32{60124},
		Username: "otheruser",
		HomeDir:  "/home/otheruser",
	}

	_, err := newHandler(t, target, startRequest("/bin/true", nil, &private, nil), defaults)

	require.NoError(t, err,
		"construction must succeed and leave the authorization decision to the kernel")
}

func TestHandlerRejectsNilIdentity(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	_, err := newHandler(t, nil, startRequest("/bin/true", nil, nil, nil), defaults)

	require.Error(t, err)
	assert.Equal(t, connect.CodeInternal, connect.CodeOf(err))
}

// TestHandlerRunsCommandInResolvedDirectory is the end-to-end check that the
// resolved directory and PWD are what the process actually observes, not just
// what the struct fields say. It reads the handler's own stdout event stream,
// which is the path a real request takes.
func TestHandlerRunsCommandInResolvedDirectory(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	req := startRequest("/bin/sh", []string{"-c", "pwd; printf '%s\\n' \"$PWD\""}, nil, nil)

	h, err := newHandler(t, currentIdentity(t), req, defaults)
	require.NoError(t, err)

	data, dataCancel := h.DataEvent.Fork()
	defer dataCancel()

	_, err = h.Start(0)
	require.NoError(t, err)

	go h.Wait()

	var stdout strings.Builder

	for event := range data {
		stdout.Write(event.Data.GetStdout())
	}

	lines := strings.Fields(strings.TrimSpace(stdout.String()))
	require.Len(t, lines, 2, "expected pwd and $PWD on separate lines: %q", stdout.String())

	// t.TempDir may sit under a symlinked path (e.g. /tmp -> /private/tmp), so
	// compare resolved paths for the shell's own view of the directory.
	wantResolved, err := filepath.EvalSymlinks(workdir)
	require.NoError(t, err)

	gotResolved, err := filepath.EvalSymlinks(lines[0])
	require.NoError(t, err)

	assert.Equal(t, wantResolved, gotResolved, "the process must run in the resolved directory")
	assert.Equal(t, workdir, lines[1], "$PWD in the process must be the resolved directory")
}

func TestHandlerPtySharesIdentityAndCwdPath(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	req := startRequest("/bin/sh", []string{"-c", "exit 0"}, nil, nil)
	req.Pty = &rpc.PTY{Size: &rpc.PTY_Size{Cols: 80, Rows: 24}}

	h, err := newHandler(t, currentIdentity(t), req, defaults)
	require.NoError(t, err)

	assert.Equal(t, workdir, h.cmd.Dir, "the PTY path shares the resolved cwd")

	pwd, ok := envValue(h.cmd, "PWD")
	require.True(t, ok)
	assert.Equal(t, workdir, pwd)
	assert.Nil(t, h.cmd.SysProcAttr.Credential,
		"a PTY for envd's own identity must not require setgroups either")
}

// TestHandlerIdentityVariablesDescribeTheTargetUser is the asymmetry the PWD fix
// exposed: HOME/USER/LOGNAME must describe the user the command actually runs as.
// The startup snapshot carries envd's own values, which are wrong for an explicit
// user, so they must not win.
func TestHandlerIdentityVariablesDescribeTheTargetUser(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		// envd's own identity variables, as an OCI image would set them.
		EnvVars: execcontext.EnvironmentSnapshot([]string{
			"HOME=/home/appuser",
			"USER=appuser",
			"LOGNAME=appuser",
		}),
	}

	target := &execcontext.Identity{
		UID:      0,
		GID:      0,
		Groups:   []uint32{0},
		Username: "root",
		HomeDir:  "/root",
	}

	h, err := newHandler(t, target, startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)

	home, ok := envValue(h.cmd, "HOME")
	require.True(t, ok)
	assert.Equal(t, "/root", home, "HOME must be the target user's, not envd's")

	user, ok := envValue(h.cmd, "USER")
	require.True(t, ok)
	assert.Equal(t, "root", user)

	logname, ok := envValue(h.cmd, "LOGNAME")
	require.True(t, ok)
	assert.Equal(t, "root", logname)
}

// TestHandlerRequestEnvOverridesIdentityVariables keeps the documented
// precedence: request-level variables are still last.
func TestHandlerRequestEnvOverridesIdentityVariables(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	req := startRequest("/bin/true", nil, nil, map[string]string{
		"HOME": "/explicit/home",
		"USER": "explicit-user",
	})

	h, err := newHandler(t, currentIdentity(t), req, defaults)
	require.NoError(t, err)

	home, ok := envValue(h.cmd, "HOME")
	require.True(t, ok)
	assert.Equal(t, "/explicit/home", home)

	user, ok := envValue(h.cmd, "USER")
	require.True(t, ok)
	assert.Equal(t, "explicit-user", user)
}

// TestHandlerStartupEnvDoesNotOverridePWD is the specific regression the ordering
// change guards: a startup snapshot PWD must not survive into the command.
func TestHandlerStartupEnvDoesNotOverridePWD(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot([]string{"PWD=/stale/from/envd"}),
	}

	h, err := newHandler(t, currentIdentity(t), startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)

	pwd, ok := envValue(h.cmd, "PWD")
	require.True(t, ok)
	assert.Equal(t, workdir, pwd)
	assert.Equal(t, h.cmd.Dir, pwd)
}

// TestHandlerWarnsWhenGroupsAreIncomplete asserts the degraded-groups case is
// actually reported. Running with only the primary group is a legitimate fallback
// for an unreadable /etc/group, but a silent fallback makes a later permission
// error inexplicable.
func TestHandlerWarnsWhenGroupsAreIncomplete(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	identity := currentIdentity(t)
	identity.GroupsIncomplete = true

	var logs bytes.Buffer

	_, err := newHandlerWithLogger(t, capturingLogger(&logs), identity,
		startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)

	output := logs.String()
	assert.Contains(t, output, "supplementary groups could not be read",
		"a degraded group list must be reported, not silently accepted")
	assert.Contains(t, output, identity.Username,
		"the warning must name the affected user")
}

// TestHandlerDoesNotWarnForCompleteGroups keeps the warning meaningful.
func TestHandlerDoesNotWarnForCompleteGroups(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	var logs bytes.Buffer

	_, err := newHandlerWithLogger(t, capturingLogger(&logs), currentIdentity(t),
		startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)

	assert.NotContains(t, logs.String(), "supplementary groups could not be read",
		"a complete group list must not produce a warning")
}

// TestHandlerSetsCredentialEvenWhenGroupsAreIncomplete closes a future-regression
// gap on a security-critical path.
//
// GroupsIncomplete means the supplementary groups could not be read. It is a
// diagnostic, NOT a reason to skip the Credential: skipping it hands the command
// envd's effective identity, which under setuid is root. A change that treated the
// flag as "identity unknown, inherit instead" would leak a root effective UID.
func TestHandlerSetsCredentialEvenWhenGroupsAreIncomplete(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:              60123,
		GID:              60124,
		Groups:           []uint32{60124},
		Username:         "degraded-user",
		HomeDir:          workdir,
		GroupsIncomplete: true,
	}

	h, err := newHandler(t, target, startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)

	require.NotNil(t, h.cmd.SysProcAttr.Credential,
		"a degraded group list must never suppress the Credential; doing so would "+
			"leave the command with envd's effective identity (root under setuid)")
	assert.Equal(t, uint32(60123), h.cmd.SysProcAttr.Credential.Uid)
	assert.Equal(t, uint32(60124), h.cmd.SysProcAttr.Credential.Gid)
	assert.Equal(t, []uint32{60124}, h.cmd.SysProcAttr.Credential.Groups,
		"the primary group must still be applied")
}

// TestHandlerUsesResolvedGroupsNotProcessGroups guards the other half: the
// Credential must carry the groups resolved for the TARGET, never envd's own.
func TestHandlerUsesResolvedGroupsNotProcessGroups(t *testing.T) {
	t.Parallel()

	workdir := t.TempDir()
	defaults := &execcontext.Defaults{
		Workdir: &workdir,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      60123,
		GID:      60124,
		Groups:   []uint32{60124, 60201},
		Username: "target-user",
		HomeDir:  workdir,
	}

	h, err := newHandler(t, target, startRequest("/bin/true", nil, nil, nil), defaults)
	require.NoError(t, err)
	require.NotNil(t, h.cmd.SysProcAttr.Credential)

	assert.Equal(t, []uint32{60124, 60201}, h.cmd.SysProcAttr.Credential.Groups,
		"the target's resolved groups must be used verbatim")

	current, err := os.Getgroups()
	require.NoError(t, err)

	for _, group := range current {
		if group == 60124 || group == 60201 {
			continue
		}

		assert.NotContains(t, h.cmd.SysProcAttr.Credential.Groups, uint32(group),
			"envd's own group %d must not leak into the target's Credential", group)
	}
}

// TestHandlerStartFailurePreservesErrorChain pins the wrapping verb. The context
// is added with %w, not %v, so errors.Is still sees the underlying syscall error
// and StartErrorCode can map a permission refusal to PermissionDenied. Switching
// to %v would silently downgrade every refusal to InvalidArgument.
func TestHandlerStartFailurePreservesErrorChain(t *testing.T) {
	t.Parallel()

	if os.Geteuid() != 0 {
		t.Skip("setting a Credential needs an effective UID of 0; " +
			"without it every start fails with EPERM and the cwd cause is not isolated")
	}

	base := t.TempDir()

	root := os.TempDir()
	for current := base; strings.HasPrefix(current, root) && current != root; current = filepath.Dir(current) {
		require.NoError(t, os.Chmod(current, 0o777))
	}

	private := filepath.Join(base, "private")
	require.NoError(t, os.Mkdir(private, 0o700))
	require.NoError(t, os.Chown(private, 0, 0))

	defaults := &execcontext.Defaults{
		Workdir: &base,
		EnvVars: execcontext.EnvironmentSnapshot(nil),
	}

	target := &execcontext.Identity{
		UID:      60123,
		GID:      60124,
		Groups:   []uint32{60124},
		Username: "otheruser",
		HomeDir:  base,
	}

	h, err := newHandler(t, target, startRequest("/bin/true", nil, &private, nil), defaults)
	require.NoError(t, err)

	_, err = h.Start(0)
	require.Error(t, err)

	assert.True(t, errors.Is(err, os.ErrPermission),
		"the wrapped error must remain inspectable; %%v instead of %%w would break this")
	assert.Equal(t, connect.CodePermissionDenied, StartErrorCode(err),
		"a permission refusal must still map to PermissionDenied after wrapping")
}
