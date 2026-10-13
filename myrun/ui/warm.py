"""Start Streamlit with a background warm-up, so the first visitor does not wait.

    python -m myrun.ui.warm run app/Dashboard.py --server.port 8501 ...

takes the same arguments as `streamlit`. A daemon thread in the same process fills the
result cache (see common.COMPUTE) and refills it every few minutes: after the input files
change in the morning, and for the results that expire on a timer. Figures are still
built on first view; they depend on choices made on the page.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

from myrun.config import Config, load_config
from myrun.ui import common

INTERVAL_S = 240        # under common.CACHE_TTL_S; each cycle recomputes the timed results
# The calls the pages make with their default choices: (name, *arguments).
WARM = (("input_states",), ("plan",), ("wellness",), ("races",), ("hr_settings",), ("headline",),
        ("weekly_load", 12), ("weekly_runs", 12), ("plan_vs_actual",), ("efficiency",),
        ("volume", "month"), ("best_efforts",), ("vo2max_trend",), ("intensity_weekly", 12),
        ("shoes",), ("training_days", 12), ("race_readiness",))

log = logging.getLogger("myrun.warm")


def warm(cfg: Config, refresh: bool = False) -> dict[str, list[str]]:
    """Fill the cache for every default page call. Never raises: failures are reported.

    With refresh, the timed results are dropped first and so computed again. Their expiry
    counts from when they were stored, not last read: without this they would run out
    between two cycles and the next visitor would pay for them."""
    warmed, failed = [], []
    if refresh:
        common.drop_clocked()
    steps = [("activities", lambda: common.load_activities(cfg))]
    steps += [(call[0], lambda call=call: common.cached(call[0], cfg, *call[1:])) for call in WARM]
    steps.append(("splits", lambda: common.load_splits(cfg)))
    for name, step in steps:
        try:
            step()
            warmed.append(name)
        except Exception as exc:  # a page shows its own error; the warm-up only notes it
            log.warning("warm-up of %s failed: %s", name, exc)
            failed.append(name)
    return {"warmed": warmed, "failed": failed}


def loop(load=load_config, stop: threading.Event | None = None,
         interval_s: float = INTERVAL_S) -> None:
    """Warm now and every interval_s seconds until stop is set."""
    stop = stop or threading.Event()
    last_key = None
    _wait_for_server(stop)
    while not stop.is_set():
        try:
            cfg = load()
            report = warm(cfg, refresh=True)
            key = common._key(cfg)
            if key != last_key:                      # say so once per change, not per cycle
                log.warning("cache warmed (%d results, %d failed)", len(report["warmed"]),
                            len(report["failed"]))
                last_key = key
        except Exception as exc:
            log.warning("warm-up skipped: %s", exc)
        stop.wait(interval_s)


def _wait_for_server(stop: threading.Event, tries: int = 60) -> None:
    """Under `streamlit run`, hold the first warm-up until the server's runtime exists, so the
    cache is created the way a page creates it. Elsewhere (tests, a notebook) do not wait."""
    if "streamlit.web.bootstrap" not in sys.modules and not _launching.is_set():
        return
    from streamlit import runtime

    for _ in range(tries):
        if runtime.exists() or stop.wait(0.5):
            return


_launching = threading.Event()


def streamlit_argv(argv: list[str]) -> list[str]:
    return ["streamlit", *argv[1:]]


def main() -> None:
    # Cached functions called outside a page run log a warning per call; it is expected here.
    logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(
        logging.ERROR)
    logging.getLogger("streamlit.runtime.caching.cache_data_api").setLevel(logging.ERROR)
    if os.environ.get("MYRUN_CACHE_LOG"):       # show every cache miss and which thread paid
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(threadName)s %(message)s"))
        for name in ("myrun.cache", "myrun.warm"):
            logging.getLogger(name).addHandler(handler)
            logging.getLogger(name).setLevel(logging.DEBUG)
    _launching.set()
    threading.Thread(target=loop, name="myrun-warm", daemon=True).start()
    from streamlit.web.cli import main as streamlit_main

    sys.argv = streamlit_argv(sys.argv)
    streamlit_main()


if __name__ == "__main__":
    main()
