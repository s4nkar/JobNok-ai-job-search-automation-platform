"""Startup-time observability wiring (stdlib logging + Sentry)."""

import logging

import sentry_sdk


def setup_logging(settings) -> None:
    # Without this, Python's logging module has no configured handler at
    # all - the stdlib falls back to its "handler of last resort", which
    # only emits WARNING and above. Every logger.info() call anywhere in the
    # app (discovery/resolution/sync progress, the backfill worker's own
    # summary lines, etc.) was silently dropped before reaching
    # docker compose logs - confirmed live: only .warning()/.exception()
    # calls were ever actually visible, despite plenty of .info() calls
    # throughout startup_hunt/startup_scout.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.2,
            send_default_pii=False,
        )
