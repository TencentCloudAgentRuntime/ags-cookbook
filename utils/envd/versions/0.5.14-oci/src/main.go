package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"connectrpc.com/authn"
	connectcors "connectrpc.com/cors"
	"github.com/go-chi/chi/v5"
	"github.com/rs/cors"

	"github.com/e2b-dev/infra/packages/envd/internal/api"
	"github.com/e2b-dev/infra/packages/envd/internal/execcontext"
	"github.com/e2b-dev/infra/packages/envd/internal/host"
	"github.com/e2b-dev/infra/packages/envd/internal/logs"
	"github.com/e2b-dev/infra/packages/envd/internal/permissions"
	"github.com/e2b-dev/infra/packages/envd/internal/services/cgroups"
	filesystemRpc "github.com/e2b-dev/infra/packages/envd/internal/services/filesystem"
	processRpc "github.com/e2b-dev/infra/packages/envd/internal/services/process"
	processSpec "github.com/e2b-dev/infra/packages/envd/internal/services/spec/process"
	"github.com/e2b-dev/infra/packages/envd/pkg"
)

const (
	// Allow enough time for proxied downstream requests.
	idleTimeout = 640 * time.Second
	maxAge      = 2 * time.Hour

	defaultPort = 49983

	portScannerInterval = 1000 * time.Millisecond

	kilobyte = 1024
	megabyte = 1024 * kilobyte
)

var (
	commitSHA string

	isNotFC bool
	port    int64

	versionFlag  bool
	commitFlag   bool
	startCmdFlag string
	cgroupRoot   string
)

func parseFlags() {
	flag.BoolVar(
		&isNotFC,
		"isnotfc",
		true,
		"isNotFCmode prints all logs to stdout",
	)

	flag.BoolVar(
		&versionFlag,
		"version",
		false,
		"print envd version",
	)

	flag.BoolVar(
		&commitFlag,
		"commit",
		false,
		"print envd source commit",
	)

	flag.Int64Var(
		&port,
		"port",
		defaultPort,
		"a port on which the daemon should run",
	)

	flag.StringVar(
		&startCmdFlag,
		"cmd",
		"",
		"a command to run on the daemon start",
	)

	flag.StringVar(
		&cgroupRoot,
		"cgroup-root",
		"/sys/fs/cgroup",
		"cgroup root directory",
	)

	flag.Parse()
}

func withCORS(h http.Handler) http.Handler {
	middleware := cors.New(cors.Options{
		AllowedOrigins: []string{"*"},
		AllowedMethods: []string{
			http.MethodHead,
			http.MethodGet,
			http.MethodPost,
			http.MethodPut,
			http.MethodPatch,
			http.MethodDelete,
		},
		AllowedHeaders: []string{"*"},
		ExposedHeaders: append(
			connectcors.ExposedHeaders(),
			"Location",
			"Cache-Control",
			"X-Content-Type-Options",
		),
		MaxAge: int(maxAge.Seconds()),
	})

	return middleware.Handler(h)
}

func main() {
	parseFlags()

	if versionFlag {
		fmt.Printf("%s\n", pkg.Version)

		return
	}

	if commitFlag {
		fmt.Printf("%s\n", commitSHA)

		return
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Snapshot the environment first: the startup identity uses it for HOME, so
	// a setuid envd does not adopt root's home directory.
	startupEnv := execcontext.EnvironmentSnapshot(os.Environ())
	startupIdentity := execcontext.CaptureStartupIdentity(startupEnv)

	defaults := &execcontext.Defaults{
		User:            startupIdentity.Username,
		StartupIdentity: startupIdentity,
		EnvVars:         startupEnv,
	}

	// Capture the startup working directory. Under AGS this is the business OCI
	// image's Workdir, and it becomes the default cwd for commands that do not
	// request one. A failure falls back to "/" rather than leaving the default
	// unset, because an unset default reinstates the home-directory fallback the
	// behavior contract forbids.
	cwd, err := execcontext.CaptureStartupWorkdir(os.Getwd)
	if err != nil {
		fmt.Fprintf(os.Stderr, "%v; defaulting to %q\n", err, cwd)
	}

	defaults.Workdir = &cwd

	isFCBoolStr := strconv.FormatBool(!isNotFC)
	defaults.EnvVars.Store("E2B_SANDBOX", isFCBoolStr)

	mmdsChan := make(chan *host.MMDSOpts, 1)
	defer close(mmdsChan)
	if !isNotFC {
		go host.PollForMMDSOpts(ctx, mmdsChan, defaults.EnvVars)
	}

	l := logs.NewLogger(ctx, isNotFC, mmdsChan)

	m := chi.NewRouter()

	envLogger := l.With().Str("logger", "envd").Logger()
	fsLogger := l.With().Str("logger", "filesystem").Logger()
	filesystemRpc.Handle(m, &fsLogger, defaults)

	// Keep process management consistent without creating envd-owned cgroups.
	cgroupManager := cgroups.NewNoopManager()
	defer func() {
		err := cgroupManager.Close()
		if err != nil {
			fmt.Fprintf(os.Stderr, "failed to close cgroup manager: %v\n", err)
		}
	}()

	processLogger := l.With().Str("logger", "process").Logger()
	processService := processRpc.Handle(m, &processLogger, defaults, cgroupManager)

	service := api.New(&envLogger, defaults, mmdsChan, isNotFC)
	handler := api.HandlerFromMux(service, m)
	middleware := authn.NewMiddleware(permissions.AuthenticateUsername)

	s := &http.Server{
		Handler: withCORS(
			service.WithAuthorization(
				middleware.Wrap(handler),
			),
		),
		Addr: fmt.Sprintf("0.0.0.0:%d", port),
		// We remove the timeouts as the connection is terminated by closing of the sandbox and keepalive close.
		ReadTimeout:  0,
		WriteTimeout: 0,
		IdleTimeout:  idleTimeout,
	}

	// Retained for callers that still provide a startup command.
	if startCmdFlag != "" {
		tag := "startCmd"
		cwd := "/home/user"
		identity, err := execcontext.IdentityForUsername("root")
		if err != nil {
			log.Fatalf("error getting user: %v", err) //nolint:gocritic // probably fine to bail if we're done?
		}

		if err = processService.InitializeStartProcess(ctx, identity, &processSpec.StartRequest{
			Tag: &tag,
			Process: &processSpec.ProcessConfig{
				Envs: make(map[string]string),
				Cmd:  "/bin/bash",
				Args: []string{"-l", "-c", startCmdFlag},
				Cwd:  &cwd,
			},
		}); err != nil {
			log.Fatalf("error starting process: %v", err)
		}
	}

	err = s.ListenAndServe()
	if err != nil {
		log.Fatalf("error starting server: %v", err)
	}
}

func createCgroupManager() (m cgroups.Manager) {
	defer func() {
		if m == nil {
			fmt.Fprintf(os.Stderr, "falling back to no-op cgroup manager\n")
			m = cgroups.NewNoopManager()
		}
	}()

	metrics, err := host.GetMetrics()
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to calculate host metrics: %v\n", err)

		return nil
	}

	// try to keep 1/8 of the memory free, but no more than 128 MB
	maxMemoryReserved := min(metrics.MemTotal/8, uint64(128)*megabyte)
	memoryMax := metrics.MemTotal - maxMemoryReserved
	memoryHigh := memoryMax // same as memory.max — OOM-kill immediately when throttling can't reclaim enough

	opts := []cgroups.Cgroup2ManagerOption{
		cgroups.WithCgroup2ProcessType(cgroups.ProcessTypePTY, "ptys", map[string]string{
			"cpu.weight":  "200", // gets much preferred cpu access, to help keep these real time
			"memory.high": fmt.Sprintf("%d", memoryHigh),
			"memory.max":  fmt.Sprintf("%d", memoryMax),
		}),
		cgroups.WithCgroup2ProcessType(cgroups.ProcessTypeSocat, "socats", map[string]string{
			"cpu.weight": "150", // gets slightly preferred cpu access
			"memory.min": fmt.Sprintf("%d", 5*megabyte),
			"memory.low": fmt.Sprintf("%d", 8*megabyte),
		}),
		cgroups.WithCgroup2ProcessType(cgroups.ProcessTypeUser, "user", map[string]string{
			"memory.high": fmt.Sprintf("%d", memoryHigh),
			"memory.max":  fmt.Sprintf("%d", memoryMax),
			"cpu.weight":  "50", // less than envd, and less than core processes that default to 100
		}),
	}
	if cgroupRoot != "" {
		opts = append(opts, cgroups.WithCgroup2RootSysFSPath(cgroupRoot))
	}

	mgr, err := cgroups.NewCgroup2Manager(opts...)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create cgroup2 manager: %v\n", err)

		return nil
	}

	return mgr
}
