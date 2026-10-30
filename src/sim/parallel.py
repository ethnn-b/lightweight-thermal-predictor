"""parallel.py: run many independent HotSpot jobs at once.

HotSpot is single-threaded, so independent runs are spread over processes. Jobs are plain
(function, kwargs) pairs; results come back in input order.
"""
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor

# HotSpot runs are memory-bandwidth bound: on our laptops throughput stops growing at about
# 8 parallel runs (experiments/P0-4_infrastructure), so that is the default.
WORKERS = int(os.environ.get("LTP_WORKERS", min(8, os.cpu_count() or 1)))


def _call(job):
    fn, kwargs = job
    return fn(**kwargs)


def pmap(fn, kwargs_list, workers=WORKERS):
    jobs = [(fn, kw) for kw in kwargs_list]
    if workers <= 1 or len(jobs) == 1:
        return [_call(j) for j in jobs]
    # fork: workers inherit loaded modules (Python 3.14 defaults to the slower forkserver)
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
        return list(ex.map(_call, jobs, chunksize=1))
