import json
import urllib.error
from unittest.mock import patch

import post_comment


def test_find_marked_comment_returns_none_when_nothing_matches():
    with patch.object(post_comment, "_request", return_value=[{"id": 1, "body": "unrelated"}]):
        assert post_comment._find_marked_comment("o/r", 42, "tok", "<!-- marker -->") is None


def test_find_marked_comment_stops_after_a_bounded_number_of_full_pages():
    # A pathological API that always returns a full, non-matching page (never an empty or
    # short one) must not spin forever: this is the exact shape of bug that caused a real
    # infinite loop and OOM before MAX_COMMENT_PAGES was added.
    calls = []
    full_page = [{"id": i, "body": "unrelated"} for i in range(100)]

    def fake_request(url, token, *, method="GET", body=None):
        calls.append(url)
        return full_page

    with patch.object(post_comment, "_request", side_effect=fake_request):
        result = post_comment._find_marked_comment("o/r", 42, "tok", "<!-- marker -->")

    assert result is None
    assert len(calls) == post_comment.MAX_COMMENT_PAGES


def test_find_marked_comment_matches_by_prefix():
    comments = [
        {"id": 1, "body": "unrelated"},
        {"id": 2, "body": "<!-- marker -->\nhello"},
    ]
    with patch.object(post_comment, "_request", return_value=comments):
        assert post_comment._find_marked_comment("o/r", 42, "tok", "<!-- marker -->") == 2


def test_upsert_comment_patches_when_an_existing_comment_is_found():
    calls = []

    def fake_request(url, token, *, method="GET", body=None):
        calls.append((url, method, body))
        if method == "GET":
            return [{"id": 7, "body": "<!-- marker -->\nold"}]
        return {}

    with patch.object(post_comment, "_request", side_effect=fake_request):
        post_comment.upsert_comment("o/r", 42, "tok", "new body", marker="<!-- marker -->")

    methods = [m for _, m, _ in calls]
    assert "PATCH" in methods
    assert "POST" not in methods
    patch_call = next(c for c in calls if c[1] == "PATCH")
    assert patch_call[0].endswith("/issues/comments/7")
    assert patch_call[2] == {"body": "new body"}


def test_upsert_comment_posts_when_no_existing_comment():
    calls = []

    def fake_request(url, token, *, method="GET", body=None):
        calls.append((url, method, body))
        if method == "GET":
            return []
        return {}

    with patch.object(post_comment, "_request", side_effect=fake_request):
        post_comment.upsert_comment("o/r", 42, "tok", "new body", marker="<!-- marker -->")

    methods = [m for _, m, _ in calls]
    assert methods == ["GET", "POST"]


def test_main_degrades_gracefully_on_a_forked_pr_403(tmp_path):
    comment_file = tmp_path / "comment.md"
    comment_file.write_text("<!-- marker -->\nbody", encoding="utf-8")

    error = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
    with patch.object(post_comment, "upsert_comment", side_effect=error):
        code = post_comment.main(
            [
                "--comment-file",
                str(comment_file),
                "--pr-number",
                "1",
                "--repo",
                "o/r",
                "--token",
                "tok",
            ]
        )
    assert code == 0


def test_main_skips_when_not_a_pull_request_event(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    comment_file = tmp_path / "comment.md"
    comment_file.write_text("body", encoding="utf-8")
    assert (
        post_comment.main(["--comment-file", str(comment_file), "--token", "t", "--repo", "o/r"])
        == 0
    )


def test_pr_number_from_event_reads_the_event_payload(tmp_path, monkeypatch):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"pull_request": {"number": 99}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    assert post_comment._pr_number_from_event() == 99
