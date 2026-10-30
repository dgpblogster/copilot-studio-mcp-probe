# copilot-studio-mcp-probe

A small read-only MCP client that connects to the Microsoft Copilot Studio MCP server and
prints what it actually advertises: the tool catalog before and after you select an
environment, the action list behind each tool, and the per-action side-effect contracts.

**The findings are in [CATALOG.md](CATALOG.md)**, captured 2026-10-30 from package v1.0.2.
The point of shipping the probe alongside them is that you should not have to take my capture
on trust.

## Why

The Copilot Studio MCP documentation lists five tools. Connect a client and you get nine
different ones, none of them on that list, until you sign in and pick an environment. Then you
get fourteen. Four of the five documented tools take an `action` parameter, and those four
carry 51 actions between them, including `delete`, `publish` and `set_enabled`.

That matters because most MCP clients approve by tool name. One approval for `manage_agents`
covers `list` and `delete` equally, because the verb is a parameter value rather than part of
the name.

This repository accompanies [The Workbench](https://www.theworkbench.blog).

## Running it

Needs Python 3.9 or later and Node.js 22.18.0 or later on PATH. The server is an npm package;
the probe launches it with `npx` over stdio, exactly as a real client does.

```bash
python probe.py --no-sign-in      # bootstrap catalog only: no browser, no account, no tenant
```

That is the honest place to start. It reaches npm and nothing else, and it reproduces the
first half of CATALOG.md in about ten seconds.

```bash
python probe.py                   # full capture
```

The full run opens a Microsoft work-account sign-in in your browser, lists your environments,
and asks you to choose one. Pressing Enter picks the first **Developer** environment, because
Microsoft's guidance is to evaluate in a development environment and the server's own
instructions say never to choose a production environment implicitly.

It writes `capture.json` and then calls `copilot_studio_disconnect`.

## What it will not do

The probe calls only reads. It derives the write list from the action names themselves:

```python
WRITE_PREFIXES = ("create", "update", "delete", "publish", "set_", "start_",
                  "generate_", "test", "validate")
```

Actions matching those prefixes are **named and described, never called**. The probe also never
touches `copilot_studio_prepare_connection` or `copilot_studio_setup_connection`, which create
or repair real Power Platform connections and Dataverse references, including in production.

It asks the server to describe the write actions instead, using the call shape the server
requires:

```json
{ "action": "describe_actions",
  "parameters": { "tool": "manage_agents", "actions": ["delete", "publish"] } }
```

That is `discover_resources`, and both `parameters.tool` and `parameters.actions` are required.
The documentation mentions the action but not the arguments, so the call fails if you follow
the article literally.

## What it captures

`capture.json` holds the server info and capabilities, the `initialize` instructions block, the
tool catalogs before and after selection with every action enum, the `serverInstructions`
returned on selection, the `describe_actions` contracts for the write actions, and the list of
skill resources.

**It contains no credentials.** It does record your environment type and the shape of what came
back. Read it before you paste it anywhere, the same as any capture.

## Reading the results honestly

Two things the capture cannot tell you, and the probe does not pretend otherwise.

Whether an action is *permitted* for your account. Tool discovery is not permission; the
documentation is explicit that an action can be denied even when the tool is listed.

Whether this catalog is still current. The server reports `listChanged: true` for both tools
and resources, and availability depends on rollout, environment, permissions and client policy.
Run the probe rather than quoting a capture that is weeks old.

## Contributing

This repository is a publishing surface for the blog rather than a community project, so it
does not accept pull requests. If the catalog no longer matches what the server advertises, the
comments on the related blog post are the right place, and that is where corrections come from.

## License

MIT. See [LICENSE](LICENSE).
