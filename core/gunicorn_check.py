import os
import sys


def assert_single_worker():
    """
    Asserts that the application is running under a single Gunicorn worker
    unless a Redis backplane registry URL is configured.
    """
    is_gunicorn = False
    workers = 1

    # 1. Check parent process name or environment
    if "gunicorn" in os.environ.get("SERVER_SOFTWARE", "").lower():
        is_gunicorn = True

    # 2. Check command line arguments for worker specifications
    for i, arg in enumerate(sys.argv):
        if arg in ("-w", "--workers"):
            try:
                workers = int(sys.argv[i + 1])
                is_gunicorn = True
            except (IndexError, ValueError):
                pass
        elif arg.startswith("--workers="):
            try:
                workers = int(arg.split("=", 1)[1])
                is_gunicorn = True
            except ValueError:
                pass

    # 3. Check WEB_CONCURRENCY env var
    web_concurrency = os.environ.get("WEB_CONCURRENCY")
    if web_concurrency:
        try:
            val = int(web_concurrency)
            if val > workers:
                workers = val
                is_gunicorn = True
        except ValueError:
            pass

    # 4. Check actual sibling processes on Linux if under Gunicorn (handles config files)
    if is_gunicorn and workers == 1:
        try:
            import glob

            ppid = os.getppid()
            worker_count = 0
            for stat_path in glob.glob("/proc/*/stat"):
                try:
                    with open(stat_path) as f:
                        parts = f.read().split()
                        if len(parts) > 3 and int(parts[3]) == ppid:
                            worker_count += 1
                except Exception:
                    pass
            if worker_count > workers:
                workers = worker_count
        except Exception:
            pass

    if is_gunicorn and workers > 1:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            raise RuntimeError(
                f"Multi-worker Gunicorn ({workers} workers) detected but REDIS_URL is not set. "
                "The in-memory queue session registry requires a single worker to prevent routing state divergence. "
                "Please configure REDIS_URL or run Gunicorn with 1 worker (-w 1)."
            )
