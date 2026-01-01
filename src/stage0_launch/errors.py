"""Stage 0 error classes (001 D11: the three failure kinds fail fast with a specific reason and never emit a run_config from a broken state)."""


class Stage0Error(Exception):
    """Base class for Stage 0 failures."""


class ProfileError(Stage0Error):
    """Invalid app_profile (schema validation failed / file unreadable / credential environment variable missing)."""


class BrowserError(Stage0Error):
    """The browser environment could not be set up."""


class AuthError(Stage0Error):
    """Authentication verification failed (the login flow failed or the probe returned non-2xx)."""
