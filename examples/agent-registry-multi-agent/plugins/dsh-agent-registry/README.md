# DSH Agent Registry tools

Read-only Agent Registry discovery for the local DeepSeek Harness demo. By default the plugin performs a lightweight
cross-Registry discovery on the first step of each user turn and supplies the results as governed capability candidates.
The model still decides whether a candidate is relevant enough to describe and invoke.

The plugin registers three model-facing tools:

- `registry_list_registries` wraps `DescribeRegistryList` and returns only CAM-visible Registries.
- `registry_list_records` wraps `DescribeRegistryRecordList`. With no `registry_id`, it discovers every visible ACTIVE Registry and searches each one; pass `registry_id` to restrict the search.
- `registry_describe_record` wraps `DescribeRegistryRecord`, accepts the Registry identity returned by discovery, and exposes the resolved Version identity.

Runtime configuration is supplied through environment variables:

```text
AGENT_REGISTRY_ENDPOINT
TENCENTCLOUD_REGION
AGENT_REGISTRY_ID            # optional compatibility default for record detail
TENCENTCLOUD_SECRET_ID
TENCENTCLOUD_SECRET_KEY
TENCENTCLOUD_TOKEN            # optional temporary-credential token
```

`AGENT_REGISTRY_ENDPOINT` defaults to `https://registry.tencentcloudapi.com/`.
Secrets are read only when a tool executes. Do not put them in `cordis.patch.yml`.

Optional plugin configuration:

```yaml
autoDiscover: true       # default: true
autoDiscoverLimit: 20    # default: 20
```

The discovery policy is domain-agnostic: it does not encode a delivery workflow or fixed agent roles. Discovery errors
are returned as non-blocking context so the user's task can continue with directly available capabilities.
Candidate projection prioritizes A2A records and samples across Registries before filling remaining slots with MCP,
Agent Skills, and other descriptor types, so one large Registry cannot hide a user's smaller Registry.
