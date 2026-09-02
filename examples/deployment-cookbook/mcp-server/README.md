# MCP Server Deployment Cookbook

This directory contains examples for running Model Context Protocol (MCP) servers on AGR Deployments.

The [simple](./simple/README.md) example deploys the official Everything MCP Server and connects to it with the official Python MCP SDK.

The walkthrough covers:

1. calling the server through the production Deployment endpoint;
2. watching active instances move from `0` to `N` and back to `0` after idle `STOP`;
3. keeping the AGS `BEST_EFFORT` affinity value while starting a fresh MCP session after an instance stops.

The example uses a published example image. To build and push a copy to your own registry, see [simple/dockerfiles](./simple/dockerfiles/README.md).
