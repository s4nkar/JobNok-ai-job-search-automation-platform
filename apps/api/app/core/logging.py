"""Startup-time observability wiring (Sentry)."""

import sentry_sdk


def setup_logging(settings) -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.2,
            send_default_pii=False,
        )
