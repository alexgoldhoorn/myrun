import re

from myrun import precommit


def test_forbidden_files():
    for path in ("data/strava.db", "x/wellness.parquet", "races.csv", "run.fit", "route.GPX",
                 "config.yaml"):
        assert precommit.forbidden_file(path), path
    for path in ("config.example.yaml", "myrun/config.py", "README.md", "tests/fixture.py"):
        assert not precommit.forbidden_file(path), path


def test_scan_text_reports_line_and_pattern_numbers_only():
    patterns = [re.compile("secret-town", re.I), re.compile(r"192\.168\.")]
    text = "fine\nlives in Secret-Town\nhost 10.0.0.5\n"
    assert precommit.scan_text(text, patterns) == [(2, 1), (3, 2)]
    assert precommit.scan_text("nothing here\n", patterns) == []


def test_load_patterns(tmp_path):
    assert precommit.load_patterns(tmp_path / "absent.txt") is None
    path = tmp_path / "deny.txt"
    path.write_text("# comment\n\nsecret-town\n192\\.168\\.\n")
    patterns = precommit.load_patterns(path)
    assert len(patterns) == 2 and patterns[0].search("SECRET-TOWN")
