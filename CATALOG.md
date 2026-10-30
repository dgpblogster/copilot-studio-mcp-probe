# What the Copilot Studio MCP server actually advertises

**Captured 2026-10-30** from `@microsoft/copilot-studio-mcp` **v1.0.2**, against a
**Developer** environment. Re-derive it yourself with [probe.py](probe.py); do not trust this
file over your own capture, because the server reports `listChanged: true` for both tools and
resources and the catalog is expected to move.

Tenant, account, environment and artifact identifiers are omitted throughout. Nothing below
needs them.

## The server

| Field | Value |
|---|---|
| `serverInfo.name` | `copilot-studio-mcp-bridge` |
| `serverInfo.version` | `1.0.2` |
| `protocolVersion` | `2025-06-18` |
| `capabilities` | `tools.listChanged: true`, `resources.listChanged: true` |
| `initialize.instructions` | **6,662 characters** of behavioral instructions for your client |

Status before sign-in: `ring: "prod"`, `signedIn: false`, **`credentialsPersisted: false`**.

Two consequences of that last field. There is no token cache, so every new client process needs
a fresh browser sign-in; and the session exists only for the lifetime of the server process.

The bridge's instructions open with: *"This bridge is fixed to the prod service deployment.
Service-ring selection is unavailable; environment selection does not change the deployment."*
It also states: *"It contains no authoring skills."*

## The catalog has two halves

**Before sign-in: 9 tools.** All local to the bridge. None of them appear in the published tool
table.

```
copilot_studio_status                 copilot_studio_connect
copilot_studio_list_environments      copilot_studio_select_environment
copilot_studio_disconnect             copilot_studio_clear_read_cache
copilot_studio_prepare_connection     copilot_studio_setup_connection
copilot_studio_connection_setup_status
```

The bridge anticipates the confusion: *"The disconnected bootstrap catalog contains only local
setup tools, not restricted versions of online authoring tools."*

**After selecting an environment: 14 tools.** The selection response reports `onlineTools: 5`,
and those five are added to the nine above. It also returns a **second** instruction block,
`serverInstructions`, separate from the one delivered at `initialize`.

## The five online tools, and their 51 actions

Four of the five take an `action` parameter. Those four carry **51 actions** between them.
Actions marked **W** write.

### `manage_agents` — 17 actions

```
create W           create_evaluation_suite W   delete W
generate_evaluation_cases W                    get_definition
get_evaluation_run get_evaluation_suite        get_publish_status
get_summary        list                        list_evaluation_suites
publish W          search                      start_evaluation_run W
test W             update W                    validate W
```

### `manage_workflows` — 15 actions

```
create W           delete W            get_definition      get_run
get_summary        inspect_run         list                list_run_actions
list_runs          publish W           search              set_enabled W
test W             update W            validate W
```

### `discover_resources` — 12 actions

```
browse_parameter_tree      callable_workflows        connectable_agents
describe_actions           foundry_knowledge_bases   get_operation_schema
list_connections           read_detail_resource      resolve_dynamic_schema
resolve_parameter_values   search_operations         search_operations_with_schemas
```

### `get_consumption` — 7 actions

```
agent_usage                        agents_and_workflows_breakdown
agents_and_workflows_usage         environment_capacity
environment_insights               workflow_inline_agent_node_usage
workflow_usage
```

### `get_copilot_studio_skills` — no action parameter

Takes `name` and an optional `path`. `name` is one of:

```
agent-authoring   workflow-design   workflow-authoring
workflow-troubleshooting            testing-and-credits
```

All four action-taking tools also accept `parameters` (object) and
`responseMode` (`auto` | `inline` | `resource`).

## Where the wire differs from the documentation

Read against
[Connect to Microsoft Copilot Studio with MCP](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/copilot-studio-mcp)
on the same day.

| Documented | Observed |
|---|---|
| A table of five tools | Five **after** environment selection; nine different ones before it, unlisted |
| `get_copilot_studio_skills` with "one of these skills" and four names | Parameter is **`name`**, not `skill`, and the enum holds **five** names |
| Four skills: `agent-authoring`, `workflow-authoring`, `workflow-troubleshooting`, `testing-and-credits` | Those four plus **`workflow-design`**, which the article does not mention |
| "use `discover_resources` with `action=describe_actions`" | That alone is rejected: `parameters.tool` and `parameters.actions` are **both required** |

The article's troubleshooting table does say "Only connection tools appear → Complete sign-in
and environment selection." So the two-halves behavior is documented. What is not documented is
which nine tools you get, or that one of them writes to production.

## The server corrects a bad call

Every malformed call came back with the schema needed to fix it, under
`data.argumentRepair.inputSchema`:

```json
{
  "status": "failed",
  "error": {
    "code": "invalidArguments",
    "message": "Correct the complete tool arguments using data.argumentRepair.inputSchema.
                Arguments do not match the action schema: Value \"describe_actions\" is not
                defined in enum. Path 'action', line 1, position 28.",
    "stage": "validation"
  },
  "data": { "argumentRepair": { "tool": "get_consumption", "inputSchema": { ... } } }
}
```

This is how the action enums above were obtained: by getting the call wrong on purpose and
reading what came back.

## The side-effect contracts

`describe_actions` returns, per action, a description plus `inputSchema`, `outputSchema` and
`inlineOutputSchema`. The call shape is the undocumented one:

```json
{
  "action": "describe_actions",
  "parameters": { "tool": "manage_agents", "actions": ["delete", "publish"] }
}
```

For `manage_agents` / `delete` it returns, verbatim:

> Permanently delete the saved agent identified by agentId. This is destructive and is not an
> unpublish operation. This operates only in the environment in the MCP URL. Obtain user
> approval for consequential effects. Never automatically retry an uncertain write.

The information a client needs in order to ask for the right approval exists, is accurate, and
is explicit about destructiveness. It is one undocumented call away from the tool list.

## The approval surface

Microsoft's documented GitHub Copilot CLI configuration is:

```json
{
  "mcpServers": {
    "copilot-studio-mcp": {
      "type": "local",
      "command": "npx",
      "args": ["-y", "@microsoft/copilot-studio-mcp@latest"],
      "tools": ["*"]
    }
  }
}
```

A client that approves by tool name grants `manage_agents` once and has granted `list` and
`delete` together, because the verb is a parameter value rather than part of the name. The
documentation says to keep client approval controls enabled, and the bridge's instructions say
to preserve client approval for consequential actions. Neither says the approval surface is
coarser than the operations behind it.

`copilot_studio_setup_connection` is in the pre-sign-in nine and creates or repairs real Power
Platform connections and Dataverse references, *"including in Prod."* It is gated behind a
prepared plan plus `confirm: true`, which is a genuinely careful two-phase design.

## It ships a skills library

`get_copilot_studio_skills` with no arguments returns **28 resources** under
`copilotflow://skills/...`: five `SKILL.md` files with YAML front matter, plus `schema.json`,
`models.json`, `examples.json`, connector-operation references, an expression reference, and
example request payloads.

```
agent-authoring/SKILL.md                    workflow-design/SKILL.md
workflow-authoring/SKILL.md                 workflow-troubleshooting/SKILL.md
testing-and-credits/SKILL.md                agent-authoring/schema.json
agent-authoring/models.json                 agent-authoring/examples.json
workflow-authoring/schema.json              workflow-authoring/examples.json
workflow-authoring/resources/connector_operations.md
workflow-authoring/resources/expression-reference.md
workflow-authoring/resources/connector-operations/{communication,files,data-and-services}.md
workflow-authoring/resources/requests/{triggers,agent-callable,ai-nodes}.json
workflow-authoring/resources/examples/{triggers,connector-chain,builtins,control-flow,
  variables,dataverse,agent-inline,classify-aib,classify-agent,invoke-m365}.json
```

Counting the instruction blocks: 6,662 characters at `initialize`, a second
`serverInstructions` block on environment selection, and a 28-file authoring library the client
is directed to read before authoring. The bridge is explicit that this guidance wins:
*"All authoring instructions, terminology, and skill content must come from the connected
Copilot Studio service; do not substitute local guidance or another product's authoring flow."*
