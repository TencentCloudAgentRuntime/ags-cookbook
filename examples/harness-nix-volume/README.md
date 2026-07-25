# Mount Agents into AGS Sandboxes with Image Volumes

This example shows how AGS uses image volumes to mount an **Agent and its own dependencies** into a sandbox on demand. The main image provides the code and task environment, while the Agent image volume provides the Agent runtime. The two can be built, combined, and upgraded independently.

This example uses Claude Code as the Agent. The same mounting pattern applies to Agents such as Codex, Pi, and OpenCode, as well as custom Harnesses. Nix is the packaging mechanism used here to produce a minimal, self-contained software closure; the core AGS capability is mounting an independent Agent image volume into the sandbox.

This approach solves both **dependency conflicts between the main image and the Agent** and **combinatorial image growth across environments and Agent/Harness variants**.

The main image only starts envd and a result website on port `8080`. Claude Code is not installed in the main image; it comes from the volume mounted at `/nix`. A local Python helper runs Claude Code through envd and prints a URL that opens directly in a browser.

The default task is intentionally small: find three important AI news items from the last 24 hours and write a short Chinese briefing with source links.

## Problems This Design Solves

### 1. Dependency conflicts between the main image and the Agent

An RL environment's main image usually pins the Python, Node.js, compilers, and system libraries required by the task. Claude Code, Codex, Pi, OpenCode, and custom Harnesses bring their own runtime dependencies. Installing an Agent directly into the main image can introduce version conflicts, pollute `PATH`, or change an otherwise reproducible task environment whenever the Agent is upgraded.

Nix places the Agent and its dependencies in isolated, hashed `/nix/store` paths. The Agent runs from its own closure without overwriting files in the main image. Commands that the Agent runs for the task still use the main image's original toolchain.

### 2. Combinatorial growth in environment images

RL systems often contain many main images, such as the task environments in the SWE-bench family. They may also support many Agent types and versions: Claude Code, Codex, Pi, OpenCode, and frequently changing custom Harnesses.

Baking every Agent into every main image creates a Cartesian product:

| Approach | Images to maintain | When an Agent or Harness changes |
|---|---|---|
| Agent baked into the main image | `M environments × N Agent/Harness versions` | Rebuild every affected main image |
| Agent mounted through an image volume | `M environment images + N Agent/Harness volumes` | Rebuild only the affected volume |

This design makes the task environment and Agent/Harness independently selectable and independently upgradable. At sandbox startup, choose a main image and mount the required Agent volume instead of prebuilding every possible combination.

## What You Will See

A successful run prints:

```text
RESULT_URL=https://8080-<instance-id>.<region>.tencentags.com/
```

Open that URL to watch the page move through three states:

1. The sandbox is ready and waiting.
2. Claude Code is searching and analyzing.
3. The final report, source links, and resolved Claude Code path are displayed.

The result page is directly accessible.

## Quick Start

### 1. Prepare the environment

You need:

- [uv](https://docs.astral.sh/uv/), Docker, and a container registry accessible to AGS.
- Tencent Cloud credentials and a `ROLE_ARN` that permits AGS to use image volumes.
- Network access to the model endpoint and web search.

You do not need Nix on the host. The Nix build runs inside a `nixos/nix` container.

Install the Python dependencies once:

```bash
make setup
```

### 2. Configure AGS and image references

```bash
cp .env.example .env
```

Reserve full registry destinations for the two images that will be built later. This step only defines their names and tags; it does not build or push anything. Step 4 tags and pushes the local build outputs to these references, and step 5 passes them to AGS when creating the Tool.

Set these values in `.env`:

```bash
TENCENTCLOUD_SECRET_ID=...
TENCENTCLOUD_SECRET_KEY=...
TENCENTCLOUD_REGION=ap-guangzhou
ROLE_ARN=qcs::cam::uin/<your-uin>:roleName/ags-image-volume-role

# Destinations used by the later build and push steps.
MAIN_IMAGE_REF=ccr.ccs.tencentyun.com/your-namespace/claude-code-nix-main:v1
CLAUDE_CODE_VOLUME_IMAGE_REF=ccr.ccs.tencentyun.com/your-namespace/claude-code-nix-volume:v1
```

Both destinations must be in a registry that AGS can pull from. The main image provides envd and the result page; the Agent image volume provides Claude Code and its runtime dependencies.

### 3. Configure the model

The model settings can be stored in the local `.env` file:

```dotenv
ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
ANTHROPIC_API_KEY="<your-api-key>"
ANTHROPIC_MODEL="deepseek-v4-flash"
```

`.env` is excluded by both `.gitignore` and `.dockerignore`, so it is neither committed to Git nor sent in the Docker build context. Do not commit it manually or copy the key into an image through Dockerfile `COPY`, `ARG`, or `ENV` instructions.

Alternatively, export the same variables in the current shell. The helper accepts either `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`. It does not store the key in the AGS Tool; it exposes the value only to the Claude Code process as `ANTHROPIC_AUTH_TOKEN`, matching the [DeepSeek Claude Code integration guide](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/).

### 4. Build and push the images

For the first run, build the main image and Agent image volume:

```bash
make build-images
make push-images
```

`make push-images` pushes both images configured in `.env` to the registry. As long as their contents do not change, later runs can reuse those images without rebuilding them.

If you already have a Tool configured with the required main image and Agent image volume, you can skip this section without rebuilding or pushing either image. Set `TOOL_ID="sdt-xxxxxxxx"` in `.env`; the next step will start an instance directly from that Tool.

### 5. Run the task

```bash
make run
```

When `TOOL_ID` is unset, the helper creates an AGS custom Tool from the images you just pushed, mounts the Agent volume read-only at `/nix`, and starts a sandbox instance. When `TOOL_ID` is set, it starts the instance directly from that Tool.

Open `RESULT_URL` when it appears. The page refreshes automatically.

`RESULT_URL` is printed before the Agent starts its task, so the page can show the transition from waiting to analyzing to complete. The instance uses `AuthMode=PUBLIC`, so result port `8080` is directly accessible. To change the task, set `TASK_TOPIC` and `AGENT_TASK` before running it again.

Tools created by the helper use time-limited sandboxes with a one-hour timeout. Their instances are released automatically at expiration and can also be cleaned up earlier.

### 6. Clean up

Stop the instance and keep the Tool for reuse:

```bash
make cleanup
```

Stop the instance and delete the Tool:

```bash
DELETE_TOOL=1 make cleanup
```

## How a Task Runs

Arrows run from top to bottom in execution order. The middle “Inside the AGS sandbox” box is the sandbox instance; all other components are outside it.

```mermaid
sequenceDiagram
  autonumber
  box Outside the sandbox: customer and AGS control plane
    actor User as Customer / browser
    participant Runner as Local run.py
    participant AGS as AGS control plane
  end
  box Inside the AGS sandbox
    participant Web as Result service :8080
    participant Envd as envd :49983
    participant Agent as Agent (Claude Code)
  end
  box Outside the sandbox: model and search services
    participant External as Model API / WebSearch
  end

  User->>Runner: Run make run
  Runner->>AGS: Create a Tool and start a one-hour time-limited instance
  Note over Web,Envd: The main image starts the result service and envd
  Note right of Agent: The Agent image volume is mounted read-only at /nix
  AGS-->>Runner: Instance ready; return instance_id
  Runner-->>User: Print RESULT_URL
  User->>Web: Open the result page on public port 8080
  Web-->>User: Show “waiting”
  Runner->>Envd: Execute /nix/.../bin/claude
  Envd->>Agent: Start the Agent
  Agent-->>Web: Publish “running” through the writable result directory
  User->>Web: Refresh GET /api/status automatically
  Web-->>User: Show “running”
  Agent->>External: Call the model and search public information
  External-->>Agent: Return information for the analysis
  Agent-->>Web: Write the report and publish “complete”
  User->>Web: Refresh GET /api/status automatically
  Web-->>User: Show the final report
  Runner->>Web: Verify final state and report
  Web-->>Runner: status=complete
```

The main image provides only envd and the result service, while the image volume provides only the Agent and its dependencies. The local helper creates resources, starts the Agent through envd, and verifies the result; the Agent inside the sandbox writes the report.

## AGS Image Volumes and Nix

AGS provides a general image-volume mounting capability. It does not require the volume to be built with Nix, nor does it inspect or manage software dependencies inside the volume. A volume can contain one standalone binary, a prepared set of files, or a complete dependency closure produced by another package manager or build system.

The user only needs to ensure that the volume matches the sandbox architecture, runs from the agreed mount path, and contains the Agent's own dependencies. AGS mounts those files into the sandbox; the packaging technology and contents of the volume are entirely up to the user.

This example uses Nix because it can start from a target program and identify all referenced transitive dependencies, producing a minimal self-contained runtime closure. `nix-store -qR` collects the Claude Code runtime closure, and only those `/nix/store` paths enter the Agent image volume. Any other tool that produces a self-contained runtime or complete dependency closure can be used instead.

This minimal closure creates a clear dependency boundary and lets the Agent ship independently of the main image:

- **Dependency-conflict isolation:** the Agent uses its own hashed paths and does not overwrite main-image libraries.
- **No combinatorial image growth:** any main image can mount the required Agent or Harness volume at runtime.
- **No repeated installation:** multiple main images can reuse the same Agent runtime.
- **No main-image pollution:** the read-only volume mounts at `/nix` and does not install into `/usr` or modify `PATH`.
- **Independent upgrades:** publish a new Agent or Harness volume without rebuilding every main image.

### The volume isolates the Agent runtime

The volume provides Claude Code's own runtime. It does not replace the customer's task environment.

For example, if the Agent runs `python test.py` in a repository, command resolution still follows the main image's `PATH` and uses its Python. Only Claude Code itself is started through the absolute path under `/nix`.

## Inspect Run Evidence

Each run writes these files under `.state/`:

| File | Contents |
|---|---|
| `runtime-report.json` | Auth mode, Nix path, Claude Code version, model, and final status |
| `claude-output.json` | Structured Claude Code output without the API key |
| `page-status.json` | Final data read back from the public page |
| `result_url` | Browser-ready result URL |

## Main Files

| Path | Purpose |
|---|---|
| `nix/default.nix` | Build the example Agent's (Claude Code) runtime closure |
| `scripts/build_volume.py` | Build the closure and volume image |
| `images/main/Dockerfile` | Build the main image with envd and the result service |
| `images/main/start_demo.py` | Supervise envd and the result service |
| `images/main/demo_server.py` | Serve the status API and result page |
| `scripts/run.py` | Create AGS resources, run the Agent, and verify the result |
| `scripts/cleanup.py` | Clean up the instance and Tool |

All runtime and lifecycle scripts are Python. The Makefile only provides short user-facing commands.
