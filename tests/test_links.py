import pandas as pd

from myrun import links


def test_links():
    assert links.strava_url("activity-123") == "https://www.strava.com/activities/123"
    assert links.sfs_url("http://host:8085", "activity-123") == (
        "http://host:8085/activities/activity-123")
    assert links.sfs_url(None, "activity-123") is None
    assert links.garmin_url(111.0) == "https://connect.garmin.com/modern/activity/111"
    assert links.garmin_url(float("nan")) is None
    assert links.garmin_url(None) is None
    assert links.garmin_url(pd.NA) is None


def test_races_get_the_garmin_link_of_their_matched_activity():
    races = pd.DataFrame({"name": ["A", "B"], "date": pd.to_datetime(["2026-09-20", "2026-05-01"]),
                          "garmin_url": [None, "https://example.org/own"]})
    acts = pd.DataFrame({"race_name": ["A", "B", None],
                         "date": pd.to_datetime(["2026-09-20", "2026-05-01", "2026-09-21"]),
                         "garmin_activity_id": [111.0, 222.0, 333.0]})
    out = links.fill_race_garmin_urls(races, acts)
    assert out["garmin_url"].tolist() == ["https://connect.garmin.com/modern/activity/111",
                                          "https://example.org/own"]


def test_race_links_are_left_alone_without_garmin_data():
    races = pd.DataFrame({"name": ["A"], "date": pd.to_datetime(["2026-09-20"])})
    acts = pd.DataFrame({"race_name": ["A"], "date": pd.to_datetime(["2026-09-20"])})
    assert "garmin_url" not in links.fill_race_garmin_urls(races, acts)
