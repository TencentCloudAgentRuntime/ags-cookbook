# MCP Server Deployment Cookbook

This directory shows how to run an existing Model Context Protocol (MCP) server on an AGR Deployment while keeping client usage native.

The current [simple](./simple/README.md) scenario deploys the official Everything MCP Server over Streamable HTTP. It uses the official Python SDK for `initialize`, `tools/list`, and `tools/call`; the only AGS-specific client behavior is carried by supported HTTP request and response hooks.

The scenario separates three observable results:

1. one native MCP session completes through the production Deployment data plane;
2. MCP traffic activates an observed number `N` of instances and returns to zero after idle `STOP`;
3. a retained AGS `BEST_EFFORT` affinity value can be reused with a newly initialized MCP session after the original instance stops.

It does not claim that the number of clients equals the number of instances or that an MCP protocol session survives instance replacement.

The pinned image source and publication instructions are under [simple/dockerfiles](./simple/dockerfiles/README.md).
