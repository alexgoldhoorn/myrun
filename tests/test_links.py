from myrun import links


def test_links():
    assert links.strava_url("activity-123") == "https://www.strava.com/activities/123"
    assert links.sfs_url("http://host:8085", "activity-123") == (
        "http://host:8085/activities/activity-123")
    assert links.sfs_url(None, "activity-123") is None
    assert links.garmin_url(111.0) == "https://connect.garmin.com/modern/activity/111"
    assert links.garmin_url(float("nan")) is None
    assert links.garmin_url(None) is None
