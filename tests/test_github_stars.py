"""Offline regression tests for public owned and Contributor star totals."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_github_stars.py"
SPEC = importlib.util.spec_from_file_location("update_github_stars", MODULE_PATH)
stars = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stars)

USERNAME = "JustlfC03"
OWNED_URL = f"/users/{USERNAME}/repos?type=owner&per_page=100"
SEARCH_URL = "/search/commits?" + urlencode({
    "q": f"author:{USERNAME} -user:{USERNAME} is:public", "per_page": 100,
})


def repository(repo_id, full_name, count, private=False, fork=False):
    return {
        "id": repo_id,
        "full_name": full_name,
        "owner": {"login": full_name.split("/")[0]},
        "html_url": "https://github.com/" + full_name,
        "stargazers_count": count,
        "private": private,
        "fork": fork,
    }


def search_results(*names, incomplete=False, total=None):
    return {
        "items": [{"repository": {"full_name": name}} for name in names],
        "total_count": len(names) if total is None else total,
        "incomplete_results": incomplete,
    }


class FakeGitHub(stars.GitHub):
    """Exercise real pagination/discovery with strict, network-free responses."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, missing_ok=False):
        self.calls.append((path, missing_ok))
        if path not in self.responses:
            raise AssertionError(f"Unexpected API request: {path}")
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response


class CollectorTests(unittest.TestCase):
    def test_all_owned_search_and_contributor_pages_are_counted(self):
        owned_one = repository(1, "JustlfC03/one", 3)
        owned_fork = repository(2, "JustlfC03/fork", 7, fork=True)
        external_one = repository(3, "team/first", 11)
        external_two = repository(4, "team/second", 13)
        api = FakeGitHub({
            OWNED_URL: ([owned_one], "https://api.github.com/owned-page-2"),
            "https://api.github.com/owned-page-2": ([owned_fork], None),
            SEARCH_URL: (search_results("team/first", total=2), "https://api.github.com/search-page-2"),
            "https://api.github.com/search-page-2": (search_results("team/second", total=2), None),
            "/repos/JustlfC03/one": (owned_one, None),
            "/repos/JustlfC03/fork": (owned_fork, None),
            "/repos/team/first": (external_one, None),
            "/repos/team/second": (external_two, None),
            "/repos/team/first/contributors?per_page=100": (
                [{"login": "someone-else"}], "https://api.github.com/contributors-page-2"
            ),
            "https://api.github.com/contributors-page-2": ([{"login": "justlfc03"}], None),
            "/repos/team/second/contributors?per_page=100": ([{"login": USERNAME}], None),
        })

        result = stars.collect(api, USERNAME, set())

        self.assertEqual(result["total_stars"], 34)
        self.assertEqual(result["owned_stars"], 10)
        self.assertEqual(result["contributed_stars"], 24)
        self.assertEqual(result["owned_repositories"], 2)
        self.assertEqual(result["contributed_repositories"], 2)
        self.assertEqual({repo["id"] for repo in result["repositories"]}, {1, 2, 3, 4})

    def test_transferred_or_renamed_repository_is_counted_once_by_id(self):
        canonical = repository(42, "JustlfC03/current-name", 19)
        api = FakeGitHub({
            OWNED_URL: ([canonical], None),
            SEARCH_URL: (search_results("old-owner/previous-name"), None),
            "/repos/JustlfC03/current-name": (canonical, None),
            "/repos/old-owner/previous-name": (canonical, None),
        })

        result = stars.collect(api, USERNAME, {"old-owner/previous-name"})

        self.assertEqual(result["total_stars"], 19)
        self.assertEqual(result["owned_repositories"], 1)
        self.assertEqual(result["contributed_repositories"], 0)
        self.assertEqual([repo["full_name"] for repo in result["repositories"]], ["JustlfC03/current-name"])

    def test_homepage_link_requires_membership_and_private_repos_are_excluded(self):
        public_member = repository(1, "team/member", 5)
        linked_only = repository(2, "team/reference", 1000)
        private_repo = repository(3, "team/private", 2000, private=True)
        private_owned = repository(4, "JustlfC03/private", 4000, private=True)
        api = FakeGitHub({
            OWNED_URL: ([private_owned], None),
            SEARCH_URL: (search_results(), None),
            "/repos/team/member": (public_member, None),
            "/repos/team/reference": (linked_only, None),
            "/repos/team/private": (private_repo, None),
            "/repos/JustlfC03/private": (private_owned, None),
            "/repos/team/member/contributors?per_page=100": ([{"login": USERNAME}], None),
            "/repos/team/reference/contributors?per_page=100": (
                [{"login": "someone-else"}, {"login": None}, {"name": USERNAME}], None
            ),
        })
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "about.md"
            source.write_text(
                "[Project](https://github.com/team/member.git)\n"
                "[Reference](https://github.com/team/reference)\n"
                "[Private](https://github.com/team/private)\n",
                encoding="utf-8",
            )
            candidates = stars.extra_candidates(source, Path(directory) / "missing.json", USERNAME)
            result = stars.collect(api, USERNAME, candidates)

        self.assertEqual(result["total_stars"], 5)
        self.assertEqual([repo["full_name"] for repo in result["repositories"]], ["team/member"])
        self.assertFalse(any("private/contributors" in path for path, _ in api.calls))

    def test_previously_contributed_repository_is_rechecked_before_counting(self):
        old_repo = repository(8, "team/old", 90)
        api = FakeGitHub({
            OWNED_URL: ([], None),
            SEARCH_URL: (search_results(), None),
            "/repos/team/old": (old_repo, None),
            "/repos/team/old/contributors?per_page=100": ([{"login": "another-user"}], None),
        })
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous.json"
            previous.write_text(json.dumps({
                "username": USERNAME,
                "repositories": [{"full_name": "team/old", "relationship": "contributed"}],
            }), encoding="utf-8")
            candidates = stars.extra_candidates(Path(directory) / "missing.md", previous, USERNAME)
            result = stars.collect(api, USERNAME, candidates)

        self.assertEqual(candidates, {"team/old"})
        self.assertEqual(result["total_stars"], 0)


class SnapshotSafetyTests(unittest.TestCase):
    def test_incomplete_search_limit_and_api_failures_preserve_previous_bytes(self):
        failures = {
            "incomplete_search": (search_results(incomplete=True), None),
            "search_limit": (search_results(total=1001), None),
            "api_failure": stars.UpdateError("GitHub returned HTTP 403"),
            "malformed_search": ({"items": [], "incomplete_results": False}, None),
        }
        for name, search_response in failures.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "github-stars.json"
                previous_bytes = b'{"username":"JustlfC03", "total_stars":123, "repositories":[]}\n'
                output.write_bytes(previous_bytes)
                api = FakeGitHub({OWNED_URL: ([], None), SEARCH_URL: search_response})
                argv = [
                    str(MODULE_PATH), "--username", USERNAME,
                    "--output", str(output), "--candidate-source", str(Path(directory) / "absent.md"),
                ]
                errors = io.StringIO()
                with mock.patch.object(stars, "GitHub", return_value=api), \
                        mock.patch("sys.argv", argv), contextlib.redirect_stderr(errors):
                    result = stars.main()

                self.assertEqual(result, 1)
                self.assertEqual(output.read_bytes(), previous_bytes)
                self.assertIn("GitHub stars update failed", errors.getvalue())
                self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["github-stars.json"])

    def test_failure_after_partial_collection_does_not_publish_partial_total(self):
        owned = repository(1, "JustlfC03/first", 10)
        api = FakeGitHub({
            OWNED_URL: ([owned], None),
            SEARCH_URL: (search_results("z-team/unavailable"), None),
            "/repos/JustlfC03/first": (owned, None),
            "/repos/z-team/unavailable": stars.UpdateError("GitHub request failed"),
        })
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-stars.json"
            original = b'{"username":"JustlfC03","repositories":[],"total_stars":88}\n'
            output.write_bytes(original)
            argv = [str(MODULE_PATH), "--output", str(output), "--candidate-source", str(Path(directory) / "absent.md")]
            with mock.patch.object(stars, "GitHub", return_value=api), \
                    mock.patch("sys.argv", argv), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(stars.main(), 1)
            self.assertEqual(output.read_bytes(), original)

    def test_success_replaces_previous_snapshot_with_complete_json(self):
        owned = repository(1, "JustlfC03/repo", 17)
        api = FakeGitHub({
            OWNED_URL: ([owned], None),
            SEARCH_URL: (search_results(), None),
            "/repos/JustlfC03/repo": (owned, None),
        })
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-stars.json"
            output.write_text('{"username":"JustlfC03","repositories":[]}', encoding="utf-8")
            argv = [str(MODULE_PATH), "--output", str(output), "--candidate-source", str(Path(directory) / "absent.md")]
            with mock.patch.object(stars, "GitHub", return_value=api), \
                    mock.patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(stars.main(), 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["total_stars"], 17)
            self.assertEqual(result["owned_stars"], 17)
            self.assertEqual(result["contributed_stars"], 0)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["github-stars.json"])


if __name__ == "__main__":
    unittest.main()
