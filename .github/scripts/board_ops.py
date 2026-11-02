"""Apply card requests to a GitHub Projects (v2) board and save a copy of the board.

Used by .github/workflows/smm-vault-board.yml. The requests and the results live in a
private repository; this repository is public, so nothing about the cards is printed:
the log shows only counts and GraphQL error types.

Environment:
  TOKEN          token that can read and write the board (and the issue repository)
  BOARD_OWNER    user that owns the board, e.g. 4BornGithub
  BOARD_NUMBER   board number, e.g. 34
  WORK_DIR       folder with requests.json; board.json, board.md and last-run.json are written here
  ISSUE_REPO     default repository for "convert" (owner/name), optional
  APPLY          "true" to apply requests.json, anything else only reads the board

requests.json is a list of operations. A card is picked by "item" (its project item id,
from board.json) or by "title" (exact, must match one card).

  {"op": "create",  "title": "...", "body": "...", "status": "Todo",
                    "assignees": ["Bhautik-4B"], "fields": {"Priority": "High"}}
  {"op": "edit",    "title": "...", "new_title": "...", "body": "..."}
  {"op": "status",  "title": "...", "status": "In Progress"}
  {"op": "assign",  "title": "...", "assignees": ["Bhautik-4B"]}   (replaces the list)
  {"op": "fields",  "title": "...", "fields": {"Priority": "High", "Estimate": 3}}
  {"op": "comment", "title": "...", "body": "..."}                  (issue cards only)
  {"op": "convert", "title": "...", "repo": "owner/name"}           (draft -> issue)
  {"op": "archive", "title": "..."}

"create" on a title that already exists updates that card instead of adding a second one.
Every operation may also carry "status", "assignees", "fields" and "comment".
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

TOKEN = os.environ["TOKEN"]
OWNER = os.environ["BOARD_OWNER"]
NUMBER = int(os.environ["BOARD_NUMBER"])
WORK = os.environ["WORK_DIR"]
ISSUE_REPO = os.environ.get("ISSUE_REPO", "")
APPLY = os.environ.get("APPLY", "").lower() == "true"


class GqlError(Exception):
    pass


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise GqlError(f"HTTP {e.code}") from None
    if d.get("errors"):
        # Messages can quote card text: kept for the private results file only.
        raise GqlError("; ".join(f"{e.get('type', 'ERROR')}: {e.get('message', '')}" for e in d["errors"]))
    return d["data"]


def norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


# ---------------------------------------------------------------- board
ITEM_FIELDS = """
  id type updatedAt isArchived
  fieldValues(first: 30) { nodes {
    ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
    ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
    ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { name } } }
    ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
    ... on ProjectV2ItemFieldIterationValue { title field { ... on ProjectV2FieldCommon { name } } }
  } }
  content {
    ... on DraftIssue { id title body assignees(first: 10) { nodes { login } } }
    ... on Issue { id title body number state url repository { nameWithOwner } assignees(first: 10) { nodes { login } } }
    ... on PullRequest { id title body number state url repository { nameWithOwner } assignees(first: 10) { nodes { login } } }
  }
"""


def load_project():
    d = gql("""query($login: String!, $number: Int!) { user(login: $login) { projectV2(number: $number) {
        id title shortDescription url closed updatedAt
        fields(first: 50) { nodes {
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField { options { id name } }
        } } } } }""", {"login": OWNER, "number": NUMBER})
    p = (d.get("user") or {}).get("projectV2")
    if not p:
        raise GqlError("board not found or not readable with this token")
    return p


def load_items():
    out, after = [], None
    while True:
        d = gql("""query($login: String!, $number: Int!, $after: String) { user(login: $login) { projectV2(number: $number) {
            items(first: 100, after: $after) { pageInfo { hasNextPage endCursor } nodes { %s } } } } }""" % ITEM_FIELDS,
                {"login": OWNER, "number": NUMBER, "after": after})
        page = d["user"]["projectV2"]["items"]
        out += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return out
        after = page["pageInfo"]["endCursor"]


def flat(n):
    f = {}
    for v in n["fieldValues"]["nodes"]:
        if not v or not v.get("field"):
            continue
        val = next((v[k] for k in ("name", "text", "number", "date", "title") if v.get(k) is not None), None)
        f[v["field"]["name"]] = val
    c = n.get("content") or {}
    return {
        "item": n["id"], "type": n["type"], "updatedAt": n["updatedAt"], "archived": n.get("isArchived", False),
        "title": c.get("title"), "body": c.get("body"), "status": f.get("Status"), "fields": f,
        "assignees": [a["login"] for a in (c.get("assignees") or {}).get("nodes", [])],
        "number": c.get("number"), "state": c.get("state"), "url": c.get("url"),
        "repo": (c.get("repository") or {}).get("nameWithOwner"), "content_id": c.get("id"),
    }


# ---------------------------------------------------------------- operations
class Board:
    def __init__(self):
        self.p = load_project()
        self.fields = {f["name"]: f for f in self.p["fields"]["nodes"] if f and f.get("name")}
        self.items = [flat(n) for n in load_items()]
        self.user_ids = {}
        self.repo_ids = {}

    def status_field(self):
        f = next((f for n, f in self.fields.items() if norm(n) == "status"), None)
        if not f or not f.get("options"):
            raise GqlError("the board has no Status field")
        return f

    def option(self, field, wanted):
        opts, w = field["options"], norm(wanted)
        aliases = {"todo": ["todo", "backlog"], "inprogress": ["inprogress", "progress", "doing"],
                   "progress": ["inprogress", "progress", "doing"], "done": ["done", "completed", "complete", "closed"],
                   "review": ["review", "reviewapproval", "approval"], "hold": ["onhold"]}
        for key in [w] + aliases.get(w, []):
            for o in opts:
                if norm(o["name"]) == key:
                    return o
        # Then a part of a name, but "done" never picks "Done But Not Deployed" by itself.
        for key in [w] + aliases.get(w, []):
            hits = [o for o in opts if key in norm(o["name"]) and ("not" not in norm(o["name"]) or "not" in w)]
            if len(hits) == 1:
                return hits[0]
        raise GqlError(f"no option '{wanted}' in field '{field['name']}' (options: {[o['name'] for o in opts]})")

    def find(self, op):
        if op.get("item"):
            hit = [i for i in self.items if i["item"] == op["item"]]
        elif op.get("title"):
            hit = [i for i in self.items if i["title"] == op["title"] and not i["archived"]]
        else:
            raise GqlError("give 'item' or 'title'")
        if not hit:
            return None
        if len(hit) > 1:
            raise GqlError(f"{len(hit)} cards have this title: use 'item'")
        return hit[0]

    def user_id(self, login):
        if login not in self.user_ids:
            d = gql("query($l: String!) { user(login: $l) { id } }", {"l": login})
            if not d.get("user"):
                raise GqlError(f"user {login} not found")
            self.user_ids[login] = d["user"]["id"]
        return self.user_ids[login]

    def repo_id(self, full):
        if full not in self.repo_ids:
            o, n = full.split("/")
            d = gql("query($o: String!, $n: String!) { repository(owner: $o, name: $n) { id } }", {"o": o, "n": n})
            if not d.get("repository"):
                raise GqlError(f"repository {full} not reachable with this token")
            self.repo_ids[full] = d["repository"]["id"]
        return self.repo_ids[full]

    # -- single changes
    def set_field(self, card, name, value):
        f = next((f for n, f in self.fields.items() if norm(n) == norm(name)), None)
        if not f:
            raise GqlError(f"no field '{name}' on the board")
        if value is None or value == "":
            gql("""mutation($p: ID!, $i: ID!, $f: ID!) { clearProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f}) { clientMutationId } }""",
                {"p": self.p["id"], "i": card["item"], "f": f["id"]})
            return
        if f.get("options") is not None:
            o = self.option(f, value)
            v, value = {"singleSelectOptionId": o["id"]}, o["name"]
        elif f.get("dataType") == "NUMBER":
            v = {"number": float(value)}
        elif f.get("dataType") == "DATE":
            v = {"date": str(value)}
        elif f.get("dataType") == "TEXT":
            v = {"text": str(value)}
        else:
            raise GqlError(f"field '{name}' ({f.get('dataType')}) cannot be set here")
        gql("""mutation($p: ID!, $i: ID!, $f: ID!, $v: ProjectV2FieldValue!) {
              updateProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f, value: $v}) { projectV2Item { id } } }""",
            {"p": self.p["id"], "i": card["item"], "f": f["id"], "v": v})
        card["fields"][f["name"]] = value
        if norm(f["name"]) == "status":
            card["status"] = value

    def edit(self, card, title=None, body=None, assignees=None):
        # Only the keys that are given go into the input: an explicit null could clear a value.
        v = {}
        if title is not None:
            v["title"] = title
        if body is not None:
            v["body"] = body
        if assignees is not None:
            v["assigneeIds"] = [self.user_id(a) for a in assignees]
        if not v:
            return
        if card["type"] == "DRAFT_ISSUE":
            gql("""mutation($in: UpdateProjectV2DraftIssueInput!) { updateProjectV2DraftIssue(input: $in) { draftIssue { id } } }""",
                {"in": dict(v, draftIssueId=card["content_id"])})
        elif card["type"] == "ISSUE":
            gql("""mutation($in: UpdateIssueInput!) { updateIssue(input: $in) { issue { id } } }""",
                {"in": dict(v, id=card["content_id"])})
        elif card["type"] == "PULL_REQUEST":
            if assignees is not None:
                raise GqlError("assignees of a pull request card are not changed here")
            gql("""mutation($in: UpdatePullRequestInput!) { updatePullRequest(input: $in) { pullRequest { id } } }""",
                {"in": dict(v, pullRequestId=card["content_id"])})
        else:
            raise GqlError(f"cannot edit a {card['type']} card")
        if title is not None:
            card["title"] = title
        if body is not None:
            card["body"] = body
        if assignees is not None:
            card["assignees"] = list(assignees)

    def comment(self, card, body):
        if card["type"] not in ("ISSUE", "PULL_REQUEST"):
            raise GqlError("comments need an issue card: convert the draft first")
        gql("mutation($s: ID!, $b: String!) { addComment(input: {subjectId: $s, body: $b}) { clientMutationId } }",
            {"s": card["content_id"], "b": body})

    def create(self, op):
        ids = [self.user_id(a) for a in op.get("assignees", [])]
        d = gql("""mutation($p: ID!, $t: String!, $b: String, $a: [ID!]) {
              addProjectV2DraftIssue(input: {projectId: $p, title: $t, body: $b, assigneeIds: $a}) {
                projectItem { %s } } }""" % ITEM_FIELDS,
                {"p": self.p["id"], "t": op["title"], "b": op.get("body", ""), "a": ids})
        card = flat(d["addProjectV2DraftIssue"]["projectItem"])
        self.items.append(card)
        return card

    def convert(self, card, repo):
        if card["type"] != "DRAFT_ISSUE":
            return card
        if not repo:
            raise GqlError("give 'repo' (owner/name) or set ISSUE_REPO")
        d = gql("""mutation($i: ID!, $r: ID!) { convertProjectV2DraftIssueItemToIssue(input: {itemId: $i, repositoryId: $r}) {
              item { %s } } }""" % ITEM_FIELDS, {"i": card["item"], "r": self.repo_id(repo)})
        new = flat(d["convertProjectV2DraftIssueItemToIssue"]["item"])
        self.items = [new if i["item"] == card["item"] else i for i in self.items]
        if card["assignees"] and not new["assignees"]:
            self.edit(new, assignees=card["assignees"])
        return new

    def archive(self, card):
        gql("mutation($p: ID!, $i: ID!) { archiveProjectV2Item(input: {projectId: $p, itemId: $i}) { item { id } } }",
            {"p": self.p["id"], "i": card["item"]})
        card["archived"] = True

    # -- one request
    def apply(self, op):
        kind = op.get("op")
        card = self.find(op)
        created = False
        if kind == "create":
            if not op.get("title"):
                raise GqlError("create needs a title")
            if card is None:
                card, created = self.create(op), True
        elif card is None:
            raise GqlError("card not found")
        elif kind not in ("edit", "status", "assign", "fields", "comment", "convert", "archive"):
            raise GqlError(f"unknown op '{kind}'")

        if kind == "convert" or op.get("convert"):
            card = self.convert(card, op.get("repo") or ISSUE_REPO)
        if kind == "archive":
            self.archive(card)
            return card, created

        title = op.get("new_title")
        body = op.get("body") if kind in ("edit", "create") and not created else None
        assignees = op.get("assignees") if not created else None
        self.edit(card, title=title, body=body, assignees=assignees)

        if op.get("status"):
            self.set_field(card, self.status_field()["name"], op["status"])
        for name, value in (op.get("fields") or {}).items():
            self.set_field(card, name, value)
        text = op.get("body") if kind == "comment" else op.get("comment")
        if text:
            self.comment(card, text)
        return card, created


# ---------------------------------------------------------------- files
def write_copy(board):
    meta = {k: board.p[k] for k in ("title", "shortDescription", "url", "closed", "updatedAt")}
    meta["fields"] = {f["name"]: [o["name"] for o in f["options"]] if f.get("options") is not None else f.get("dataType")
                      for f in board.fields.values()}
    items = [i for i in board.items if not i["archived"]]
    json.dump({"project": meta, "read_at": now(), "items": items},
              open(os.path.join(WORK, "board.json"), "w"), indent=1, ensure_ascii=False)
    order = (meta["fields"].get("Status") or []) if isinstance(meta["fields"].get("Status"), list) else []
    groups = {}
    for it in items:
        groups.setdefault(it["status"] or "(no status)", []).append(it)
    names = [s for s in order if s in groups] + [s for s in groups if s not in order]
    with open(os.path.join(WORK, "board.md"), "w") as m:
        m.write(f"# {meta['title']}\n\n{meta.get('shortDescription') or ''}\n\n"
                f"Board {meta['url']}, updated {meta['updatedAt']}; {len(items)} cards (read {now()}).\n")
        for s in names:
            m.write(f"\n## {s} ({len(groups[s])})\n\n")
            for it in groups[s]:
                ref = f" ({it['repo']}#{it['number']})" if it.get("number") else " (draft)"
                who = f" - {', '.join(it['assignees'])}" if it["assignees"] else ""
                extra = "; ".join(f"{k}: {v}" for k, v in it["fields"].items()
                                  if k not in ("Status", "Title", "Assignees") and v not in (None, ""))
                m.write(f"- **{it['title'] or '(untitled)'}**{ref}{who}" + (f" - {extra}" if extra else "") +
                        f"  `{it['item']}`\n")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    os.makedirs(WORK, exist_ok=True)
    board = Board()
    print(f"Board read: {len(board.items)} items, {len(board.fields)} fields")
    results = []
    if APPLY:
        path = os.path.join(WORK, "requests.json")
        ops = json.load(open(path)) if os.path.exists(path) else []
        for n, op in enumerate(ops):
            try:
                card, created = board.apply(op)
                results.append({"n": n, "op": op, "ok": True, "created": created, "item": card["item"],
                                "title": card["title"], "status": card["status"], "url": card["url"]})
            except (GqlError, KeyError, ValueError, TypeError) as e:
                results.append({"n": n, "op": op, "ok": False, "error": str(e)})
        ok = sum(r["ok"] for r in results)
        print(f"Requests applied: {ok} of {len(ops)}; failed: {len(ops) - ok}")
    json.dump({"run_at": now(), "applied": APPLY, "results": results},
              open(os.path.join(WORK, "last-run.json"), "w"), indent=1, ensure_ascii=False)
    write_copy(board)
    # 2 = some requests failed (the details are in last-run.json); the files are still saved.
    return 2 if any(not r["ok"] for r in results) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GqlError as e:
        # The message can quote board text: say only what kind of failure it was.
        print("Board access failed:", str(e).split(":")[0])
        sys.exit(1)
