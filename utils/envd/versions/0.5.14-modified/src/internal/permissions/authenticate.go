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

func GetAuthUser(ctx context.Context, defaultUser string, startupUser *user.User) (*user.User, error) {
	u, ok := authn.GetInfo(ctx).(*user.User)
	if !ok {
		// Keep the exact effective UID/GID captured when envd started. Looking the
		// username up again can silently replace the effective GID with the
		// account's primary group.
		if startupUser != nil && defaultUser == startupUser.Username {
			return startupUser, nil
		}

		username, err := execcontext.ResolveDefaultUsername(nil, defaultUser)
		if err != nil {
			return nil, connect.NewError(connect.CodeUnauthenticated, fmt.Errorf("no user specified"))
		}

		u, err := GetUser(username)
		if err != nil {
			return nil, authn.Errorf("invalid default user: '%s'", username)
		}

		return u, nil
	}

	return u, nil
}
