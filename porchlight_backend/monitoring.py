"""Optional application performance and error monitoring integrations."""
import logging
import os


logger = logging.getLogger(__name__)


def _enabled(value: str | None) -> bool:
    return (value or '').lower() in {'1', 'true', 'yes', 'on'}


def _sample_rate(name: str, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv(name, str(default)))))
    except ValueError:
        return default


def initialize_new_relic() -> None:
    """Start New Relic before Django so framework transactions are instrumented."""
    if not _enabled(os.getenv('NEW_RELIC_ENABLED')):
        return

    try:
        import newrelic.agent

        newrelic.agent.initialize()
    except Exception:  # pragma: no cover - startup failures are logged, not fatal
        logger.exception('New Relic initialization failed; continuing without APM.')


def initialize_sentry() -> None:
    """Enable Sentry errors, traces, and profiles when a DSN is configured."""
    dsn = os.getenv('SENTRY_DSN')
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv('SENTRY_ENVIRONMENT', os.getenv('DJANGO_ENV', 'development')),
            release=os.getenv('SENTRY_RELEASE') or None,
            integrations=[DjangoIntegration()],
            traces_sample_rate=_sample_rate('SENTRY_TRACES_SAMPLE_RATE', 0.1),
            profiles_sample_rate=_sample_rate('SENTRY_PROFILES_SAMPLE_RATE', 0.0),
            send_default_pii=_enabled(os.getenv('SENTRY_SEND_DEFAULT_PII')),
        )
    except Exception:  # pragma: no cover - startup failures are logged, not fatal
        logger.exception('Sentry initialization failed; continuing without error tracking.')