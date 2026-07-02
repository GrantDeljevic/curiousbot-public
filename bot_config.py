import os

GOOGLE_SERVICE_ACCOUNT_JSON_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
GOOGLE_SERVICE_FILE_ENV = "GOOGLE_SERVICE_FILE"


def env_int(name, default=None):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value.strip())


def env_ints(name, default=()):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return tuple(default)
    return tuple(int(part.strip()) for part in value.replace(";", ",").split(",") if part.strip())


def env_strings(name, default=()):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return tuple(default)
    return tuple(part.strip() for part in value.replace(";", ",").split(",") if part.strip())


def require_env(name):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Set the {name} environment variable")
    return value


def google_client():
    import pygsheets

    if os.getenv(GOOGLE_SERVICE_ACCOUNT_JSON_ENV):
        return pygsheets.authorize(service_account_env_var=GOOGLE_SERVICE_ACCOUNT_JSON_ENV)

    service_file = os.getenv(GOOGLE_SERVICE_FILE_ENV)
    if service_file:
        return pygsheets.authorize(service_account_file=service_file)

    raise RuntimeError(
        f"Set {GOOGLE_SERVICE_ACCOUNT_JSON_ENV} or {GOOGLE_SERVICE_FILE_ENV} for Google Sheets access"
    )
