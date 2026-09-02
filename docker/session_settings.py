# ---------------------------------------------------------------------------
# Durée de vie de la session navigateur
# ---------------------------------------------------------------------------

SESSION_COOKIE_AGE = get_setting(  # noqa: F821
    "INVENTREE_SESSION_COOKIE_AGE", "cookie.age", 1209600, typecast=int
)

SESSION_SAVE_EVERY_REQUEST = get_boolean_setting(  # noqa: F821
    "INVENTREE_SESSION_SAVE_EVERY_REQUEST", "cookie.save_every_request", False
)
