package permissions

import (
	"errors"
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"slices"
	"strings"
	"syscall"

	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
)

func expand(path, homedir string) (string, error) {
	if len(path) == 0 {
		return path, nil
	}

	if path[0] != '~' {
		return path, nil
	}

	if len(path) > 1 && path[1] != '/' && path[1] != '\\' {
		return "", errors.New("cannot expand user-specific home dir")
	}

	return filepath.Join(homedir, path[1:]), nil
}

func ExpandAndResolve(path string, user *user.User, defaultPath *string) (string, error) {
	path = execcontext.ResolveDefaultWorkdir(path, defaultPath)

	path, err := expand(path, user.HomeDir)
	if err != nil {
		return "", fmt.Errorf("failed to expand path '%s' for user '%s': %w", path, user.Username, err)
	}

	if filepath.IsAbs(path) {
		return path, nil
	}

	// The filepath.Abs can correctly resolve paths like /home/user/../file
	path = filepath.Join(user.HomeDir, path)

	abs, err := filepath.Abs(path)
	if err != nil {
		return "", fmt.Errorf("failed to resolve path '%s' for user '%s' with home dir '%s': %w", path, user.Username, user.HomeDir, err)
	}

	return abs, nil
}

// getSubpaths returns path and all of its ancestors below the root, root-most
// first. "/" itself is not included.
//
// The path is made absolute first: for a relative path filepath.Dir eventually
// returns "." forever, so the walk would never reach "/" and would loop
// indefinitely.
func getSubpaths(path string) (subpaths []string) {
	if !filepath.IsAbs(path) {
		abs, err := filepath.Abs(path)
		if err != nil {
			// Without a working directory there is nothing to walk up from.
			return []string{path}
		}

		path = abs
	}

	path = filepath.Clean(path)

	for path != "/" {
		subpaths = append(subpaths, path)

		parent := filepath.Dir(path)
		if parent == path {
			// Defensive: filepath.Dir is a fixed point only at "/", but never
			// spin if a future path shape reaches one elsewhere.
			break
		}

		path = parent
	}

	slices.Reverse(subpaths)

	return subpaths
}

func EnsureDirs(path string, uid, gid int) error {
	subpaths := getSubpaths(path)
	for _, subpath := range subpaths {
		info, err := os.Stat(subpath)
		if err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("failed to stat directory: %w", err)
		}

		if err != nil && os.IsNotExist(err) {
			err = os.Mkdir(subpath, 0o755)
			if err != nil && !os.IsExist(err) {
				return fmt.Errorf("failed to create directory: %w", err)
			}

			// Chown even if another process created the directory (os.IsExist),
			// since it may not have called Chown yet. Chown is idempotent.
			err = os.Chown(subpath, uid, gid)
			if err != nil {
				return fmt.Errorf("failed to chown directory: %w", err)
			}

			continue
		}

		if !info.IsDir() {
			return fmt.Errorf("path is a file: %s", subpath)
		}
	}

	return nil
}

// DescribeCwdAccess explains why a target identity may be unable to use path as
// a working directory.
//
// It is DIAGNOSTIC ONLY and never decides the outcome. The kernel is the sole
// authority on directory search: it also honors POSIX ACLs, SELinux, and
// capabilities, none of which are visible in the classic permission bits. An
// earlier version of this code denied requests based on those bits alone and
// would reject a request the kernel would have allowed via an ACL entry.
//
// The returned string is empty when nothing suspicious was found, so callers can
// append it to a real failure without inventing an explanation. Every ancestor is
// inspected, because search permission is required on the whole path, and a
// missing execute bit on a parent is the usual cause.
func DescribeCwdAccess(path string, identity *execcontext.Identity) string {
	if identity == nil {
		return ""
	}

	// root and any identity holding the directory's group are still subject to the
	// kernel's decision; this only points at the most likely component.
	var blocking []string

	for _, subpath := range getSubpaths(path) {
		info, err := os.Stat(subpath)
		if err != nil {
			blocking = append(blocking, fmt.Sprintf("%s (stat failed: %v)", subpath, err))

			continue
		}

		stat, ok := info.Sys().(*syscall.Stat_t)
		if !ok {
			continue
		}

		if searchPermitted(info.Mode().Perm(), stat, identity) {
			continue
		}

		blocking = append(blocking, fmt.Sprintf(
			"%s (owner uid=%d gid=%d mode=%04o)",
			subpath, stat.Uid, stat.Gid, info.Mode().Perm(),
		))
	}

	if len(blocking) == 0 {
		return ""
	}

	return "path components without search permission for this user: " + strings.Join(blocking, ", ")
}

// searchPermitted evaluates the classic permission bits only. It is a heuristic
// used to build a diagnostic message, not an authorization decision.
func searchPermitted(mode os.FileMode, stat *syscall.Stat_t, identity *execcontext.Identity) bool {
	if identity.UID == 0 {
		return true
	}

	if stat.Uid == identity.UID {
		return mode&0o100 != 0
	}

	if stat.Gid == identity.GID || slices.Contains(identity.Groups, stat.Gid) {
		return mode&0o010 != 0
	}

	return mode&0o001 != 0
}

// CwdFailureContext renders the user and directory context that must accompany a
// failure to start a command in a working directory.
func CwdFailureContext(path string, identity *execcontext.Identity) string {
	if identity == nil {
		return fmt.Sprintf("cwd '%s'", path)
	}

	context := fmt.Sprintf(
		"user '%s' (uid=%d gid=%d groups=%v) could not run in cwd '%s'",
		identity.Username, identity.UID, identity.GID, identity.Groups, path,
	)

	if detail := DescribeCwdAccess(path, identity); detail != "" {
		context += "; " + detail
	}

	return context
}
