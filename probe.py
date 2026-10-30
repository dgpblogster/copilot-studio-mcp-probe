#!/usr/bin/env python3
"""Probe the Microsoft Copilot Studio MCP server and print what it actually advertises.

Read-only. It signs you in, lets you pick an environment, captures the tool catalog
before and after that selection, and reads per-action contracts. It refuses to call
any action that writes.

    python probe.py                 # interactive, writes capture.json
    python probe.py --no-sign-in    # bootstrap catalog only, no browser, no account

Requires Python 3.9+ and Node.js >= 22.18.0 on PATH (the server ships as an npm
package and the client launches it with npx).
"""
import argparse, json, os, queue, shutil, subprocess, sys, threading, time

PACKAGE = "@microsoft/copilot-studio-mcp@latest"

# Any action whose name starts with one of these is a write. The probe will not
# call them, and neither should a client without explicit per-action approval.
WRITE_PREFIXES = ("create", "update", "delete", "publish", "set_", "start_",
                  "generate_", "test", "validate")


class Server:
    """The smallest MCP stdio client that can hold a conversation."""

    def __init__(self, cmd):
        self.p = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self.q, self.err, self._n = queue.Queue(), [], 0
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read_out(self):
        for line in self.p.stdout:
            line = line.strip()
            if line:
                try:
                    self.q.put(json.loads(line))
                except ValueError:
                    self.err.append("non-JSON on stdout: " + line[:200])

    def _read_err(self):
        for line in self.p.stderr:
            self.err.append(line.rstrip())

    def send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self._n += 1
            msg["id"] = self._n
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        return None if notify else self._n

    def call(self, method, params=None, timeout=300):
        rid = self.send(method, params)
        end, held = time.time() + timeout, []
        while time.time() < end:
            try:
                m = self.q.get(timeout=1)
            except queue.Empty:
                if self.p.poll() is not None:
                    raise RuntimeError("server exited rc=%s\n%s"
                                       % (self.p.returncode, "\n".join(self.err[-30:])))
                continue
            if m.get("id") == rid:
                for h in held:
                    self.q.put(h)
                return m
            held.append(m)
        raise TimeoutError("no reply to %s in %ss" % (method, timeout))

    def tool(self, name, arguments=None, timeout=300):
        r = self.call("tools/call", {"name": name, "arguments": arguments or {}}, timeout)
        res = r.get("result") or {}
        text = "\n".join(c["text"] for c in res.get("content", []) if c.get("type") == "text")
        return {"text": text, "isError": res.get("isError"), "error": r.get("error")}

    def close(self):
        try:
            self.p.terminate()
        except OSError:
            pass


def as_json(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def describe(tools):
    rows = []
    for t in tools:
        schema = t.get("inputSchema") or {}
        props = schema.get("properties") or {}
        actions = (props.get("action") or {}).get("enum") or []
        rows.append({
            "name": t["name"],
            "actions": actions,
            "inputs": sorted(props.keys()),
            "required": schema.get("required") or [],
            "description": (t.get("description") or "").strip(),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sign-in", action="store_true",
                    help="capture the bootstrap catalog only; no browser, no account")
    ap.add_argument("--out", default="capture.json")
    args = ap.parse_args()

    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        sys.exit("npx not found. Install Node.js >= 22.18.0 and retry.")

    s = Server([npx, "-y", PACKAGE])
    cap = {"package": PACKAGE, "capturedUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    init = s.call("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "copilot-studio-mcp-probe", "version": "1.0"},
    }).get("result", {})
    s.send("notifications/initialized", {}, notify=True)

    cap["serverInfo"] = init.get("serverInfo")
    cap["capabilities"] = init.get("capabilities")
    cap["instructions"] = init.get("instructions")
    print("server       :", json.dumps(init.get("serverInfo")))
    print("capabilities :", json.dumps(init.get("capabilities")))
    print("instructions : %d characters shipped to your client at initialize"
          % len(init.get("instructions") or ""))

    before = s.call("tools/list", {}).get("result", {}).get("tools", [])
    cap["toolsBeforeSignIn"] = describe(before)
    print("\n%d tools BEFORE sign-in:" % len(before))
    for t in before:
        print("  -", t["name"])

    status = as_json(s.tool("copilot_studio_status")["text"]) or {}
    cap["statusBeforeSignIn"] = status
    print("\nstatus: ring=%s signedIn=%s credentialsPersisted=%s"
          % (status.get("ring"), status.get("signedIn"), status.get("credentialsPersisted")))

    if args.no_sign_in:
        json.dump(cap, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print("\nwrote", args.out)
        s.close()
        return

    print("\nOpening Microsoft work-account sign-in. Review the consent screen.")
    s.tool("copilot_studio_connect", timeout=900)

    envs = as_json(s.tool("copilot_studio_list_environments")["text"]) or {}
    items = envs.get("environments", [])
    if not items:
        sys.exit("No environments returned for this account.")
    print("\nEnvironments:")
    for i, e in enumerate(items, 1):
        print("  %d) %s  [%s, %s]" % (i, e["displayName"], e["type"], e["location"]))
    pick = input("\nChoose (number), or Enter for the first Developer one: ").strip()
    if pick:
        env = items[int(pick) - 1]
    else:
        env = next((e for e in items if e["type"] == "Developer"), items[0])
    print("Selecting:", env["displayName"])

    sel = as_json(s.tool("copilot_studio_select_environment",
                         {"environment": env["id"]}, timeout=600)["text"]) or {}
    cap["onlineTools"] = sel.get("onlineTools")
    cap["serverInstructions"] = sel.get("serverInstructions")
    cap["environmentType"] = env["type"]
    print("onlineTools        :", sel.get("onlineTools"))
    print("serverInstructions : %d characters from the connected service"
          % len(sel.get("serverInstructions") or ""))

    time.sleep(2)
    after = s.call("tools/list", {}).get("result", {}).get("tools", [])
    cap["toolsAfterSelection"] = describe(after)
    total = sum(len(r["actions"]) for r in cap["toolsAfterSelection"])
    print("\n%d tools AFTER selection, %d actions behind them:" % (len(after), total))
    for r in cap["toolsAfterSelection"]:
        if r["actions"]:
            writes = [a for a in r["actions"] if a.startswith(WRITE_PREFIXES)]
            print("  - %-28s %2d actions  (%d write: %s)"
                  % (r["name"], len(r["actions"]), len(writes), ", ".join(writes) or "none"))
        else:
            print("  - %-28s  no action parameter" % r["name"])

    # The side-effect contracts. This call shape is what the server requires:
    # parameters.tool and parameters.actions are both mandatory.
    names = {t["name"] for t in after}
    cap["describeActions"] = {}
    for tool in ("manage_agents", "manage_workflows"):
        if tool not in names:
            continue
        row = next(r for r in cap["toolsAfterSelection"] if r["name"] == tool)
        writes = [a for a in row["actions"] if a.startswith(WRITE_PREFIXES)]
        got = s.tool("discover_resources", {
            "action": "describe_actions",
            "parameters": {"tool": tool, "actions": writes},
        })
        cap["describeActions"][tool] = as_json(got["text"]) or got["text"]

    print("\nSide-effect descriptions for the write actions:")
    for tool, payload in cap["describeActions"].items():
        for a in ((payload or {}).get("data") or {}).get("actions", []):
            print("  [%s %s] %s" % (tool, a["action"], a["description"][:150]))

    skills = as_json(s.tool("get_copilot_studio_skills")["text"])
    cap["skillResources"] = skills
    if isinstance(skills, list):
        print("\nSkill resources served: %d" % len(skills))

    json.dump(cap, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\nwrote", args.out)
    print("Signing out (the session token lives only in this process).")
    s.tool("copilot_studio_disconnect")
    s.close()


if __name__ == "__main__":
    main()
