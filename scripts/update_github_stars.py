#!/usr/bin/env python3
"""Refresh public owned/contributor repository stars without exposing a token.

Commit search discovers candidates across all time, but GitHub caps each search
at 1,000 results. An incomplete or larger search fails rather than publishing a
silently truncated total. Homepage links and previous contributions supplement
search; every external repository must list the user in its contributors API.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


class UpdateError(Exception):
    """The previous snapshot must be retained when a scan fails."""


class GitHub:
    def __init__(self):
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "homepage-github-star-collector",
        }
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            self.headers["Authorization"] = "Bearer " + token

    def get(self, path, missing_ok=False):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise UpdateError("Refusing an unexpected API pagination URL")
        try:
            with urlopen(Request(url, headers=self.headers), timeout=30) as response:
                body = response.read()
                data = json.loads(body) if body else []
                next_link = re.search(r'<([^>]+)>;\s*rel="next"', response.headers.get("Link", ""))
                return data, next_link.group(1) if next_link else None
        except HTTPError as error:
            if missing_ok and error.code == 404:
                return None, None
            raise UpdateError(f"GitHub returned HTTP {error.code} for {url}") from error
        except (URLError, TimeoutError) as error:
            raise UpdateError(f"GitHub request failed for {url}: {error}") from error

    def pages(self, path, missing_ok=False):
        while path:
            data, path = self.get(path, missing_ok=missing_ok)
            if data is None:
                return
            if not isinstance(data, list):
                raise UpdateError("Expected a repository or contributor list from GitHub")
            yield from data

    def commit_candidates(self, username):
        path = "/search/commits?" + urlencode({
            "q": f"author:{username} -user:{username} is:public", "per_page": 100,
        })
        candidates = set()
        while path:
            data, path = self.get(path)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise UpdateError("Expected commit search results from GitHub")
            if data.get("incomplete_results") is not False:
                raise UpdateError("GitHub commit search is incomplete; previous snapshot retained")
            if data["total_count"] > 1000:
                raise UpdateError(
                    "GitHub commit search exceeds its 1,000-result limit; "
                    "previous snapshot retained. Split the search before retrying."
                )
            candidates.update(item["repository"]["full_name"] for item in data["items"])
        return candidates


def extra_candidates(source_path, previous_path, username):
    candidates = set()
    if source_path.exists():
        text = source_path.read_text(encoding="utf-8")
        for owner, repository in re.findall(
            r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text
        ):
            if repository.endswith(".git"):
                repository = repository[:-4]
            candidates.add(f"{owner}/{repository}")
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        if previous.get("username", "").casefold() != username.casefold():
            raise UpdateError("Previous snapshot belongs to a different GitHub username")
        candidates.update(
            repo["full_name"] for repo in previous["repositories"]
            if repo["relationship"] == "contributed"
        )
    return candidates


def collect(api, username, candidates):
    owned = list(api.pages(f"/users/{quote(username, safe='')}/repos?type=owner&per_page=100"))
    owned_metadata = {repo["full_name"].casefold(): repo for repo in owned}
    candidates.update(repo["full_name"] for repo in owned)
    candidates.update(api.commit_candidates(username))
    repositories = {}
    for full_name in sorted(candidates, key=str.casefold):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
            raise UpdateError(f"Invalid repository name: {full_name!r}")
        path = "/repos/" + full_name
        repo = owned_metadata.get(full_name.casefold())
        if repo is None:
            repo, _ = api.get(path, missing_ok=True)
        if repo is None or repo["private"]:
            continue
        relationship = "owned" if repo["owner"]["login"].casefold() == username.casefold() else "contributed"
        if relationship == "contributed":
            contributors = api.pages(path + "/contributors?per_page=100", missing_ok=True)
            if not any((person.get("login") or "").casefold() == username.casefold() for person in contributors):
                continue
        repositories[repo["id"]] = {
            "id": repo["id"],
            "full_name": repo["full_name"],
            "url": repo["html_url"],
            "stars": repo["stargazers_count"],
            "relationship": relationship,
        }
    ordered = sorted(repositories.values(), key=lambda repo: repo["full_name"].casefold())
    owned = [repo for repo in ordered if repo["relationship"] == "owned"]
    contributed = [repo for repo in ordered if repo["relationship"] == "contributed"]
    return {
        "schemaVersion": 1,
        "username": username,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "total_stars": sum(repo["stars"] for repo in ordered),
        "owned_stars": sum(repo["stars"] for repo in owned),
        "contributed_stars": sum(repo["stars"] for repo in contributed),
        "owned_repositories": len(owned),
        "contributed_repositories": len(contributed),
        "repositories": ordered,
    }


def atomic_write(output, snapshot):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="JustlfC03")
    parser.add_argument("--output", type=Path, default=Path("_data/github_stars.json"))
    parser.add_argument("--previous", type=Path, help="Previous snapshot; defaults to --output")
    parser.add_argument("--candidate-source", type=Path, default=Path("_pages/about.md"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", args.username):
        parser.error("--username must be a GitHub login")
    try:
        candidates = extra_candidates(args.candidate_source, args.previous or args.output, args.username)
        snapshot = collect(GitHub(), args.username, candidates)
        atomic_write(args.output, snapshot)
    except (UpdateError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"GitHub stars update failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Saved {snapshot['total_stars']} stars "
        f"({snapshot['owned_stars']} owned + {snapshot['contributed_stars']} contributed) "
        f"across {len(snapshot['repositories'])} repositories to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
