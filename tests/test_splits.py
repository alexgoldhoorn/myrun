import importlib
import os

import pandas as pd
import pytest

from myrun.splits import CACHE_NAME, split_metrics, splits
from tests.fixture import STEADY

splits_mod = importlib.import_module("myrun.splits")  # the package exports a function of the same name


def test_split_metrics_assigns_samples_by_distance():
    s = pd.DataFrame({"distance_m": [0, 500, 999, 1000, 1500, 2500],
                      "hr": [100, 110, 120, 150, 0, 170],
                      "cadence_spm": [160, 160, 160, 170, 170, 180]})
    out = split_metrics(s, [1000, 1000]).set_index("split")
    assert out.loc[1, "avg_hr"] == pytest.approx(110.0)
    assert out.loc[2, "avg_hr"] == pytest.approx(150.0)      # the zero-HR sample is ignored
    assert out.loc[2, "avg_cadence_spm"] == pytest.approx(170.0)
    assert list(out.index) == [1, 2]                         # 2500 m is past the last split


def test_splits_metric_only_partial_dropped(cfg):
    df = splits(cfg=cfg)
    assert df["activity_id"].unique().tolist() == [STEADY]
    assert df["split"].tolist() == [1, 2, 3, 4, 5, 6, 7]     # the 200 m split 8 is dropped
    assert (df["distance_m"] == 1000).all()


def test_split_values(cfg):
    df = splits(cfg=cfg).set_index("split")
    assert df["grade_class"].tolist() == ["climb", "descent", "flat", "flat", "flat", "flat", "flat"]
    assert df.loc[1, "pace_min_km"] == pytest.approx(333 / 60)
    assert df.loc[1, "gap_min_km"] == pytest.approx(333 / 60)
    assert df.loc[1, "avg_hr"] == pytest.approx(140.0)
    assert df.loc[4, "avg_hr"] == pytest.approx((200 * 140 + 134 * 147) / 334)
    assert df.loc[7, "avg_hr"] == pytest.approx(147.0)
    assert df.loc[1, "avg_cadence_spm"] == pytest.approx(170.0)
    assert df.loc[1, "surface"] == "road"
    assert df.loc[1, "temp_c"] == 12.0
    assert df.loc[1, "hour"] == 7.5


def test_cache_is_written_and_reused(cfg, monkeypatch):
    first = splits(cfg=cfg)
    assert (cfg.cache_dir / CACHE_NAME).is_file()

    def boom(*args, **kwargs):
        raise AssertionError("streams were decoded again although the cache is complete")

    monkeypatch.setattr(splits_mod, "activity_streams", boom)
    pd.testing.assert_frame_equal(first, splits(cfg=cfg))


def test_corrupt_cache_is_rebuilt(cfg):
    cfg.cache_dir.mkdir(parents=True)
    (cfg.cache_dir / CACHE_NAME).write_bytes(b"this is not parquet")
    df = splits(cfg=cfg).set_index("split")
    assert df.loc[1, "avg_hr"] == pytest.approx(140.0)
    assert pd.read_parquet(cfg.cache_dir / CACHE_NAME)["activity_id"].eq(STEADY).any()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_cache_dir_still_returns_rows(cfg):
    cfg.cache_dir.mkdir(parents=True)
    cfg.cache_dir.chmod(0o500)
    try:
        df = splits(cfg=cfg).set_index("split")
        assert df.loc[7, "avg_hr"] == pytest.approx(147.0)
    finally:
        cfg.cache_dir.chmod(0o700)
