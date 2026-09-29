"""Creates or updates the single AgentProbe PR comment, identified by a hidden marker
(format_comment.MARKER) so re-runs edit the same comment instead of piling up new ones.

Stdlib only (urllib), talking to the GitHub REST API directly: this is the one HTTP call the
composite action needs, and it must never hold a GitHub token beyond this process's env.

Fork PRs get a read-only GITHUB_TOKEN and can't create or update comments (GitHub restricts
this on purpose so an untrusted PR can't post as the repo). That shows up here as a 403/404,
which is not a failure of the run itself: the CLI's exit code, propagated by a separate action
step, is what gates the required check. This script only ever logs a warning and exits 0.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API = "https://api.github.com"


def _request(
    url: str, token: str, *, method: str = "GET", body: dict[str, Any] | None = None
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    if not url.startswith(API):
        raise ValueError(f"refusing to call a non-GitHub-API URL: {url}")
    request = urllib.request.Request(  # noqa: S310 -- url is checked to start with API (https://) above
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- see above
        return json.loads(response.read())


MAX_COMMENT_PAGES = 20  # 2,000 comments; a hard stop so a misbehaving API can't loop forever


def _find_marked_comment(repo: str, pr_number: int, token: str, marker: str) -> int | None:
    for page in range(1, MAX_COMMENT_PAGES + 1):
        url = f"{API}/repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}"
        comments = _request(url, token)
        if not isinstance(comments, list) or not comments:
            return None
        for comment in comments:
            if str(comment.get("body", "")).startswith(marker):
                return int(comment["id"])
        if len(comments) < 100:  # short page: no next page to fetch
            return None
    return None


def upsert_comment(repo: str, pr_number: int, token: str, body: str, *, marker: str) -> None:
    existing_id = _find_marked_comment(repo, pr_number, token, marker)
    if existing_id is not None:
        _request(
            f"{API}/repos/{repo}/issues/comments/{existing_id}",
            token,
            method="PATCH",
            body={"body": body},
        )
    else:
        _request(
            f"{API}/repos/{repo}/issues/{pr_number}/comments",
            token,
            method="POST",
            body={"body": body},
        )


def _pr_number_from_event() -> int | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.isfile(event_path):
        return None
    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)
    number = (event.get("pull_request") or {}).get("number")
    return int(number) if number is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comment-file", required=True)
    parser.add_argument("--marker", default="<!-- agentprobe-report -->")
    parser.add_argument("--pr-number", type=int, default=None)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args(argv)

    pr_number = args.pr_number or _pr_number_from_event()
    if pr_number is None:
        print("::notice::not a pull request event; skipping the PR comment")
        return 0
    if not args.token or not args.repo:
        print("::warning::no GITHUB_TOKEN/GITHUB_REPOSITORY; skipping the PR comment")
        return 0

    with open(args.comment_file, encoding="utf-8") as f:
        body = f.read()

    try:
        upsert_comment(args.repo, pr_number, args.token, body, marker=args.marker)
    except urllib.error.HTTPError as exc:
        # A fork PR's GITHUB_TOKEN is read-only (403/404 here); degrade gracefully (ADR 0032):
        # the required check still fails on regression via the CLI's own exit code.
        print(f"::warning::couldn't post the PR comment (HTTP {exc.code}): {exc.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
