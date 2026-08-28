package execcontext

import (
	"errors"
	"fmt"
	"os"
	"os/user"
	"slices"
	"strconv"
	"strings"

	"github.com/e2b-dev/infra/packages/envd/internal/utils"
)

// Identity is a numeric snapshot of a Linux execution identity.
//
// It exists because *user.User cannot represent the identity envd actually runs
// with: it has no field for supplementary groups, and looking a username up
// again in the passwd database can silently substitute the account's configured
// primary group for the GID the OCI runtime really applied. An OCI User that is
// a bare numeric UID may have no passwd entry at all, in which case there is no
// username to look up.
//
// UID, GID, and Groups are therefore the authoritative fields. Username and
// HomeDir are best-effort display and convenience values.
type Identity struct {
	// Username is a display name. For a UID with no passwd entry it is the
	// decimal UID.
	Username string

	// HomeDir may be empty when it cannot be determined.
	HomeDir string

	// Groups holds the primary GID plus supplementary groups, deduplicated and
	// sorted so identity comparisons and test assertions do not depend on the
	// order the kernel happened to return.
	Groups []uint32

	UID uint32
	GID uint32

	// GroupsIncomplete records that the supplementary groups could not be read
	// (for example a missing or unreadable /etc/group) and that Groups therefore
	// holds only the primary GID.
	//
	// It is a flag rather than an error because losing the supplementary groups
	// must not reject a command that would otherwise run: the primary identity is
	// still correct. Callers that can log should surface it.
	GroupsIncomplete bool
}

type Defaults struct {
	EnvVars *utils.Map[string, string]

	// StartupIdentity is the identity the OCI runtime applied to envd. It is the
	// default identity for requests that carry no explicit username.
	StartupIdentity *Identity

	// Workdir is the default working directory. In AGS it is captured from the
	// business image's OCI Workdir at startup.
	Workdir *string

	// User is the default username, retained for the /init compatibility
	// interface.
	User string
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

// NormalizeGroups returns the group list deduplicated and sorted ascending.
//
// setgroups tolerates duplicates, but a deterministic list keeps identity
// comparisons and assertions independent of the order os.Getgroups returned.
func NormalizeGroups(groups []uint32) []uint32 {
	if len(groups) == 0 {
		return nil
	}

	normalized := slices.Clone(groups)
	slices.Sort(normalized)

	return slices.Compact(normalized)
}

// CaptureStartupIdentity snapshots the identity the OCI runtime applied to this
// process.
//
// It reads the real UID and GID, not the effective ones: a setuid envd has
// effective UID 0 while its real UID is still the OCI User, and recording root
// as the startup identity would let the default command inherit a root
// effective UID instead of dropping back down to the OCI User.
//
// Nothing here depends on the passwd database. A lookup failure only leaves
// Username as the decimal UID and HomeDir possibly empty; it never fails the
// capture, so an OCI User with no passwd entry still yields a usable identity.
// startupEnv supplies HOME so a setuid envd does not adopt root's home.
func CaptureStartupIdentity(startupEnv *utils.Map[string, string]) *Identity {
	uid := os.Getuid()
	gid := os.Getgid()

	identity := &Identity{
		UID:      uint32(uid),
		GID:      uint32(gid),
		Username: strconv.Itoa(uid),
	}

	groups := []uint32{uint32(gid)}

	if supplementary, err := os.Getgroups(); err == nil {
		for _, group := range supplementary {
			groups = append(groups, uint32(group))
		}
	} else {
		identity.GroupsIncomplete = true
	}

	identity.Groups = NormalizeGroups(groups)

	// Best-effort enrichment. A missing passwd entry is expected for a numeric
	// OCI User and must not change the numeric identity above.
	if u, err := lookupUID(strconv.Itoa(uid)); err == nil {
		if u.Username != "" {
			identity.Username = u.Username
		}

		identity.HomeDir = u.HomeDir
	}

	// Prefer the startup environment's HOME: it is what the OCI image and
	// runtime actually set for this process. Deriving it from the effective user
	// would give a setuid envd /root.
	if startupEnv != nil {
		if home, ok := startupEnv.Load("HOME"); ok && home != "" {
			identity.HomeDir = home
		}
	}

	return identity
}

// CaptureStartupWorkdir returns the working directory to use as the default for
// commands that do not request one. Under AGS this is the business OCI image's
// Workdir.
//
// getwd is injected so the failure branch is testable. On failure the result is
// "/" and a description of the problem, never an empty string: an empty default
// makes path resolution fall back to the user's home directory, which the
// behavior contract forbids.
func CaptureStartupWorkdir(getwd func() (string, error)) (string, error) {
	cwd, err := getwd()
	if err != nil {
		return "/", fmt.Errorf("failed to determine startup working directory: %w", err)
	}

	if cwd == "" {
		return "/", errors.New("startup working directory is empty")
	}

	return cwd, nil
}

// lookupUID is the passwd lookup used to enrich a captured identity, indirected
// so a test can prove the enrichment never touches the numeric identity.
var lookupUID = user.LookupId

// IdentityForUsername resolves a username in the business rootfs into a full
// numeric identity, including supplementary groups from /etc/group.
func IdentityForUsername(username string) (*Identity, error) {
	u, err := user.Lookup(username)
	if err != nil {
		return nil, fmt.Errorf("error looking up user '%s': %w", username, err)
	}

	return identityFromUser(u)
}

// groupIDsFor is the supplementary-group lookup, indirected so the failure branch
// is reachable in tests without mutating /etc/group.
var groupIDsFor = func(u *user.User) ([]string, error) { return u.GroupIds() }

func identityFromUser(u *user.User) (*Identity, error) {
	uid, err := strconv.ParseUint(u.Uid, 10, 32)
	if err != nil {
		return nil, fmt.Errorf("error parsing uid '%s' for user '%s': %w", u.Uid, u.Username, err)
	}

	gid, err := strconv.ParseUint(u.Gid, 10, 32)
	if err != nil {
		return nil, fmt.Errorf("error parsing gid '%s' for user '%s': %w", u.Gid, u.Username, err)
	}

	identity := &Identity{
		UID:      uint32(uid),
		GID:      uint32(gid),
		Username: u.Username,
		HomeDir:  u.HomeDir,
	}

	groups := []uint32{uint32(gid)}

	groupIDs, err := groupIDsFor(u)
	if err != nil {
		// Run with the primary group rather than rejecting the request: the
		// primary identity is correct and this is exactly what an unreadable
		// /etc/group produces. The loss is recorded on the identity so a caller
		// that can log will not hide it.
		identity.Groups = NormalizeGroups(groups)
		identity.GroupsIncomplete = true

		return identity, nil
	}

	for _, id := range groupIDs {
		parsed, parseErr := strconv.ParseUint(id, 10, 32)
		if parseErr != nil {
			continue
		}

		groups = append(groups, uint32(parsed))
	}

	identity.Groups = NormalizeGroups(groups)

	return identity, nil
}

// User adapts the identity to the *user.User shape the filesystem API and path
// helpers still take. Supplementary groups are not representable there, so
// callers that need them must use the Identity itself.
func (i *Identity) User() *user.User {
	if i == nil {
		return nil
	}

	return &user.User{
		Uid:      strconv.FormatUint(uint64(i.UID), 10),
		Gid:      strconv.FormatUint(uint64(i.GID), 10),
		Username: i.Username,
		HomeDir:  i.HomeDir,
	}
}

// MatchesCurrentProcess reports whether a child process would already have this
// identity without envd setting any credentials.
//
// The comparison is against the *effective* IDs and the current group list, not
// the real IDs. Under setuid the real UID equals the default target while the
// effective UID is 0; comparing real IDs would conclude "nothing to do" and leak
// a root effective UID to the command.
func (i *Identity) MatchesCurrentProcess() bool {
	if i == nil {
		return false
	}

	if i.UID != uint32(os.Geteuid()) || i.GID != uint32(os.Getegid()) {
		return false
	}

	current, err := os.Getgroups()
	if err != nil {
		// Without a reliable group list, do not claim a match.
		return false
	}

	currentGroups := make([]uint32, 0, len(current)+1)
	currentGroups = append(currentGroups, uint32(os.Getegid()))

	for _, group := range current {
		currentGroups = append(currentGroups, uint32(group))
	}

	return slices.Equal(i.Groups, NormalizeGroups(currentGroups))
}

// ResolveDefaultWorkdir implements "explicit request wins, otherwise the
// captured startup cwd".
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
