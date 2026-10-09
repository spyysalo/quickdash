"""Assemble Pages from checked static artifacts; never execute PR content."""
import argparse
from datetime import datetime, timezone
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from urllib.parse import urlencode
import zipfile

SITE_FILES = ("index.html", "demo.html", "LICENSE", "js-yaml.LICENSE")
STATE_FILE = ".preview-state.json"
STATE_BRANCH = "pages-content"
# The current dashboard is about 14 MiB. Bound both archive layers before reading.
MAX_BYTES = 100 * 1024 * 1024
BUILD_FIELDS = ("run_id", "run_attempt", "sha", "artifact_id", "run_url")
COMMENT_MARKER = "<!-- quickdash-pages-preview -->"


def read_owners(path=None):
    path = path or Path(__file__).resolve().parents[1] / "OWNERS"
    owners = set()
    for line in Path(path).read_text().splitlines():
        login = line.split("#", 1)[0].strip().lower()
        if login:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?", login):
                raise ValueError("OWNERS must contain one GitHub login per line")
            owners.add(login)
    if not owners:
        raise ValueError("OWNERS must not be empty")
    return owners


def preview_authorization(pr, owners, comments, sha=None):
    sha = sha or pr["head"]["sha"]
    if pr["user"]["login"].lower() in owners:
        return dict(allowed=True, sha=sha, source="owner")
    for comment in comments:
        author = comment.get("user", {}).get("login", "").lower()
        command = re.fullmatch(r"/deploy ([0-9a-f]{40})", (comment.get("body") or "").strip())
        if author in owners and command and command[1] == sha:
            return dict(allowed=True, sha=sha, source="approval", approver=author, comment_id=comment["id"])
    return dict(allowed=False, sha=sha, source="approval_required")


def read_bundle(data):
    """Read the upload-pages-artifact ZIP/TAR without extracting archive paths."""
    try:
        if len(data) > MAX_BYTES:
            raise ValueError("Pages archive exceeds 100 MiB")
        with zipfile.ZipFile(io.BytesIO(data)) as zipped:
            entries = zipped.infolist()
            if len(entries) != 1 or entries[0].filename != "artifact.tar":
                raise ValueError("Expected only artifact.tar in Pages ZIP")
            if entries[0].file_size > MAX_BYTES:
                raise ValueError("Pages TAR exceeds 100 MiB")
            payload = zipped.read(entries[0])
        files = {}
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as tar:
            total = 0
            for member in tar:
                if member.name == "." and member.isdir():
                    continue
                name = member.name[2:] if member.name.startswith("./") else member.name
                if name not in SITE_FILES or name in files or not member.isfile():
                    raise ValueError("Unexpected, duplicate, or non-regular Pages file: " + member.name)
                total += member.size
                if member.size < 0 or total > MAX_BYTES:
                    raise ValueError("Pages files exceed 100 MiB")
                files[name] = tar.extractfile(member).read()
        if set(files) != set(SITE_FILES):
            raise ValueError("Pages artifact is missing required files")
        return files
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as error:
        raise ValueError("Invalid Pages archive") from error


class GitHub:
    def __init__(self, repository, default_branch, owners=None):
        self.repository = repository
        self.default_branch = default_branch
        self.owners = read_owners() if owners is None else owners

    def get(self, path):
        endpoint = f"repos/{self.repository}" + ("/" + path if path else "")
        return json.loads(subprocess.check_output(["gh", "api", endpoint]))

    def write(self, method, path, data):
        subprocess.run(["gh", "api", "--method", method, f"repos/{self.repository}/{path}",
                        "--input", "-", "--silent"], input=json.dumps(data), text=True, check=True)

    def pulls(self):
        results = []
        page = 1
        while True:
            batch = self.get(f"pulls?state=open&per_page=100&page={page}")
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1

    def comments(self, number):
        results = []
        page = 1
        while True:
            batch = self.get(f"issues/{number}/comments?per_page=100&page={page}")
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1

    def authorization(self, pr, sha=None):
        # GitHub comments are the approval record. Reconciliation reads them all
        # so coalesced Actions events cannot drop an owner's command.
        comments = [] if pr["user"]["login"].lower() in self.owners else self.comments(pr["number"])
        return preview_authorization(pr, self.owners, comments, sha)

    def latest_build(self, pr=None):
        filters = dict(status="success", per_page=100)
        if pr is None:
            filters["branch"] = self.default_branch
            repo_id = self.get("")["id"]
            events = ("push", "workflow_dispatch")
        else:
            if pr["head"]["repo"] is None:
                return None
            filters["head_sha"] = pr["head"]["sha"]
            repo_id = pr["head"]["repo"]["id"]
            events = ("pull_request",)
        candidates = []
        for event in events:
            query = urlencode(dict(filters, event=event))
            runs = self.get("actions/workflows/pages.yml/runs?" + query)["workflow_runs"]
            for run in runs:
                if (run["event"] != event or run["conclusion"] != "success"
                        or (run.get("head_repository") or {}).get("id") != repo_id):
                    continue
                if pr is not None:
                    if run["head_sha"] != pr["head"]["sha"] or run["head_branch"] != pr["head"]["ref"]:
                        continue
                elif run["head_branch"] != self.default_branch:
                    continue
                # workflow_run.pull_requests can be empty for forks and its head SHA
                # can change after a later push. The run's own head_sha is immutable.
                candidates.append(run)
        if not candidates:
            return None
        run = max(candidates, key=lambda item: (item["id"], item.get("run_attempt", 1)))
        artifacts = self.get(f"actions/runs/{run['id']}/artifacts?per_page=100")["artifacts"]
        artifacts = [a for a in artifacts if a["name"] == "github-pages" and not a["expired"]]
        if not artifacts:
            return None  # Keep the previously published snapshot when artifacts expire.
        if len(artifacts) != 1 or artifacts[0]["size_in_bytes"] > MAX_BYTES:
            raise ValueError("Invalid Pages artifact inventory")
        return dict(run_id=run["id"], run_attempt=run.get("run_attempt", 1), sha=run["head_sha"],
                    artifact_id=artifacts[0]["id"], run_url=run["html_url"])

    def download(self, candidate):
        return subprocess.check_output(["gh", "api",
            f"repos/{self.repository}/actions/artifacts/{candidate['artifact_id']}/zip"])


def install(site, candidate, source):
    files = read_bundle(source.download(candidate))
    site.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (site / name).write_bytes(data)
    return {key: candidate[key] for key in BUILD_FIELDS}


def same_build(previous, candidate):
    return previous and all(previous[key] == candidate[key] for key in BUILD_FIELDS)


def reconcile(site, source):
    """Reconcile every open PR so coalesced Actions events cannot lose updates."""
    site.mkdir(parents=True, exist_ok=True)
    state_path = site / STATE_FILE
    state = json.loads(state_path.read_text()) if state_path.exists() else {"main": None, "previews": {}}
    main = source.latest_build()
    previous = state["main"]
    if main and (not previous or (main["run_id"], main["run_attempt"]) >= (previous["run_id"], previous["run_attempt"])):
        if not same_build(previous, main):
            state["main"] = install(site, main, source)
    if not state["main"] or not all((site / name).is_file() for name in SITE_FILES):
        raise ValueError("A successful main build artifact is required before publishing previews")

    pulls = source.pulls()
    open_numbers = {str(pr["number"]) for pr in pulls}
    retired = set(state.get("retired_previews", [])) - open_numbers
    preview_dir = site / "pr-preview"
    preview_dir.mkdir(exist_ok=True)
    for number in list(state["previews"]):
        if number not in open_numbers:
            shutil.rmtree(preview_dir / ("pr-" + number))
            del state["previews"][number]
            retired.add(number)
    # Persist cleanup until post-deployment reporting succeeds, including retries
    # and coalesced close events. A reopened PR no longer needs a closed notice.
    state["retired_previews"] = sorted(retired)
    state["preview_access"] = {}
    warnings = []
    for pr in pulls:
        number = str(pr["number"])
        access = source.authorization(pr)
        state["preview_access"][number] = access
        previous = state["previews"].get(number)
        if previous and not source.authorization(pr, previous["sha"])["allowed"]:
            shutil.rmtree(preview_dir / ("pr-" + number))
            del state["previews"][number]
        if not access["allowed"]:
            continue
        try:
            candidate = source.latest_build(pr)
            if candidate and not same_build(state["previews"].get(number), candidate):
                state["previews"][number] = install(preview_dir / ("pr-" + number), candidate, source)
        except ValueError as error:
            # A malformed PR bundle must not prevent production/other PRs publishing.
            warnings.append(f"PR #{number}: {error}")

    rows = []
    for pr in sorted(pulls, key=lambda item: item["number"]):
        number = str(pr["number"])
        preview = state["previews"].get(number)
        title = html.escape(pr["title"])
        label = f'<a href="{html.escape(pr["html_url"], quote=True)}">#{number}: {title}</a>'
        if preview:
            status = "Current" if preview["sha"] == pr["head"]["sha"] else "Previous successful build"
            link = f'<a href="pr-{number}/index.html">Open preview</a>'
            provenance = f'<a href="{html.escape(preview["run_url"], quote=True)}">{preview["sha"][:12]}</a>'
        else:
            status = "Awaiting successful build" if state["preview_access"][number]["allowed"] else "Awaiting owner approval"
            link, provenance = "—", "—"
        rows.append(f"<tr><td>{label}</td><td>{link}</td><td>{status}</td><td>{provenance}</td></tr>")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Quickdash PR previews</title><style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.8rem;border-bottom:1px solid #ccc}</style>
<h1>Quickdash PR previews</h1><p><a href="../index.html">Main dashboard</a></p>
<p>Previews require an author listed in OWNERS or an owner's approval of the exact commit, and a successful build.
A previous approved build may be shown while a newer commit is awaiting approval, pending, or failing.
The commit link identifies the build being served. Closed PRs are removed.</p>
<table><thead><tr><th>Pull request</th><th>Preview</th><th>Status</th><th>Built commit</th></tr></thead><tbody>'''
    (preview_dir / "index.html").write_text(page + "".join(rows) + "</tbody></table></html>\n")
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    for warning in warnings:
        print(warning)
    return state


def report_checks(state, api, base_url):
    """Attach the deployed URL to the PR's commit as a check."""
    for pr in api.pulls():
        number = str(pr["number"])
        preview = state["previews"].get(number)
        if not preview or preview["sha"] != pr["head"]["sha"] or not api.authorization(pr)["allowed"]:
            continue
        url = f"{base_url.rstrip('/')}/pr-preview/pr-{number}/"
        external_id = "quickdash-preview-" + number
        existing = api.get(f"commits/{preview['sha']}/check-runs?check_name=Pages%20preview&filter=latest&per_page=100")["check_runs"]
        existing = next((c for c in existing if c.get("external_id") == external_id), None)
        payload = dict(name="Pages preview", external_id=external_id, status="completed", conclusion="success",
                       completed_at=datetime.now(timezone.utc).isoformat(),
                       details_url=url, output=dict(title=f"Preview for PR #{number}",
                       summary=f"[Open preview]({url}) · [Source build]({preview['run_url']})\n\nBuilt commit: `{preview['sha']}`. This URL follows the latest successful build and is removed when the PR closes."))
        if existing:
            api.write("PATCH", f"check-runs/{existing['id']}", payload)
        else:
            api.write("POST", "check-runs", dict(payload, head_sha=preview["sha"]))


def update_comment(api, number, body, create=True):
    existing = next((comment for comment in api.comments(number)
                     if comment.get("user", {}).get("login") == "github-actions[bot]"
                     and comment["user"].get("type") == "Bot"
                     and (comment.get("body") or "").startswith(COMMENT_MARKER)), None)
    if existing:
        if existing["body"] != body:
            api.write("PATCH", f"issues/comments/{existing['id']}", {"body": body})
    elif create:
        api.write("POST", f"issues/{number}/comments", {"body": body})


def report_comments(state, api, base_url):
    """Keep one discoverable preview link in each PR conversation."""
    open_prs = {str(pr["number"]): pr for pr in api.pulls()}
    for number, pr in open_prs.items():
        preview = state["previews"].get(number)
        access = api.authorization(pr)
        body = f"{COMMENT_MARKER}\n"
        if preview:
            url = f"{base_url.rstrip('/')}/pr-preview/pr-{number}/"
            body += (f"**🚀 [Open preview]({url})**\n\n"
                     f"Built from `{preview['sha'][:12]}` · [Build details]({preview['run_url']})\n\n")
            if preview["sha"] != pr["head"]["sha"]:
                body += "This preview is from a previous successful build; it does not include the latest PR commit.\n\n"
        if not access["allowed"]:
            owners_url = f"https://github.com/{api.repository}/blob/{api.default_branch}/OWNERS"
            body += (f"**Owner approval required for this commit.**\n\n"
                     f"Did not auto-deploy because the PR author is not listed in [OWNERS]({owners_url}). "
                     "An OWNER can approve this commit by copying this command into a new comment:\n\n"
                     f"```text\n/deploy {pr['head']['sha']}\n```\n\n"
                     "Checks must pass before deployment. Later commits need a new approval. "
                     "To enable automatic previews for this author, add them to OWNERS through a reviewed change on the default branch.")
        elif not preview:
            if access["source"] != "approval":
                continue
            body += "**Preview approved; waiting for a successful build.**"
        else:
            body += "This link updates after successful, authorized builds. The preview is removed when this PR closes."
        update_comment(api, number, body)
        if preview and preview["sha"] == access["sha"] and access.get("source") == "approval":
            api.write("POST", f"issues/comments/{access['comment_id']}/reactions", {"content": "rocket"})
    for number in state.get("retired_previews", []):
        if number not in open_prs:
            update_comment(api, number, f"{COMMENT_MARKER}\n**Preview closed**\n\n"
                           "This PR is closed and its preview has been removed.", create=False)
    state["retired_previews"] = []


def git(*args, **kwargs):
    return subprocess.run(["git", *args], check=True, **kwargs)


def prepare_worktree(site):
    branch = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", STATE_BRANCH],
                            capture_output=True, text=True)
    if branch.returncode == 0:
        git("fetch", "origin", f"refs/heads/{STATE_BRANCH}:refs/remotes/origin/{STATE_BRANCH}")
        git("worktree", "add", "--detach", str(site), "origin/" + STATE_BRANCH)
    elif branch.returncode == 2:
        git("worktree", "add", "--detach", str(site), "HEAD")
        git("-C", str(site), "switch", "--orphan", STATE_BRANCH)
    else:
        raise RuntimeError("Could not read Pages state branch: " + branch.stderr)


def save_worktree(site):
    git("-C", str(site), "add", "--all")
    changed = subprocess.check_output(["git", "-C", str(site), "status", "--porcelain"])
    if changed:
        git("-C", str(site), "-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m", "Update dashboard and PR previews")
        git("-C", str(site), "push", "origin", f"HEAD:refs/heads/{STATE_BRANCH}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("assemble", "report", "inspect"))
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"), required=not os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    api = GitHub(args.repository, args.default_branch)
    if args.command == "report":
        state_path = args.site / STATE_FILE
        state = json.loads(state_path.read_text())
        report_checks(state, api, args.base_url)
        report_comments(state, api, args.base_url)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        save_worktree(args.site)
    else:
        if args.command == "assemble":
            prepare_worktree(args.site)
        state = reconcile(args.site, api)
        if args.command == "assemble":
            save_worktree(args.site)
        print(json.dumps(state, indent=2))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as output:
                output.write(f"[PR preview index]({args.base_url.rstrip('/')}/pr-preview/)\n\n")
                for number, preview in sorted(state["previews"].items()):
                    output.write(f"- [PR #{number}]({args.base_url.rstrip('/')}/pr-preview/pr-{number}/) — `{preview['sha'][:12]}`\n")


if __name__ == "__main__":
    main()
