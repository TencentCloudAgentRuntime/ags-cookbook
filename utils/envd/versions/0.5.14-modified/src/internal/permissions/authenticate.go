package permissions

import (
	"context"
	"fmt"
	"os/user"

	"connectrpc.com/authn"
	"connectrpc.com/connect"

	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
)

func AuthenticateUsername(_ context.Context, req authn.Request) (any, error) {
	username, _, ok := req.BasicAuth()
	if !ok {
		// When no username is provided, ignore the authentication method (not all endpoints require it)
		// Missing user is then handled in the GetAuthUser function
		return nil, nil
	}

	u, err := GetUser(username)
	if err != nil {
		return nil, authn.Errorf("invalid username: '%s'", username)
	}

	return u, nil
}

// GetAuthIdentity resolves the identity a request should execute as.
//
// Without an explicit username the request uses the startup identity captured
// from the OCI runtime, numeric fields and supplementary groups included. The
// username is deliberately not looked up again: doing so would drop the
// supplementary groups the runtime applied, substitute the account's configured
// primary group for the real GID, and fail outright for an OCI User that has no
// passwd entry.
//
// With an explicit username the target user is resolved in the business rootfs,
// including its supplementary groups from /etc/group.
func GetAuthIdentity(ctx context.Context, defaults *execcontext.Defaults) (*execcontext.Identity, error) {
	if u, ok := authn.GetInfo(ctx).(*user.User); ok {
		identity, err := execcontext.IdentityForUsername(u.Username)
		if err != nil {
			return nil, authn.Errorf("invalid username: '%s'", u.Username)
		}

		return identity, nil
	}

	if defaults != nil && defaults.StartupIdentity != nil {
		// An /init caller may override the default username. Honor that only
		// when it names a different user than the startup identity, so the
		// normal path keeps the exact numeric snapshot.
		if defaults.User != "" && defaults.User != defaults.StartupIdentity.Username {
			identity, err := execcontext.IdentityForUsername(defaults.User)
			if err != nil {
				return nil, authn.Errorf("invalid default user: '%s'", defaults.User)
			}

			return identity, nil
		}

		return defaults.StartupIdentity, nil
	}

	// No startup snapshot: fall back to the configured default username.
	defaultUser := ""
	if defaults != nil {
		defaultUser = defaults.User
	}

	username, err := execcontext.ResolveDefaultUsername(nil, defaultUser)
	if err != nil {
		return nil, connect.NewError(connect.CodeUnauthenticated, fmt.Errorf("no user specified"))
	}

	identity, err := execcontext.IdentityForUsername(username)
	if err != nil {
		return nil, authn.Errorf("invalid default user: '%s'", username)
	}

	return identity, nil
}

// GetAuthUser is the *user.User view of GetAuthIdentity, for the filesystem API
// and path helpers that do not need supplementary groups.
func GetAuthUser(ctx context.Context, defaults *execcontext.Defaults) (*user.User, error) {
	identity, err := GetAuthIdentity(ctx, defaults)
	if err != nil {
		return nil, err
	}

	return identity.User(), nil
}
