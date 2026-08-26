# ---------------------------------------------------------------------------
# Durée de vie de la session navigateur (OPS-01).
#
# Ce fragment est concaténé à la fin de `InvenTree/settings.py` au moment du
# build de l'image (voir Dockerfile). Il n'est donc PAS un module importable :
# il s'exécute dans la portée de settings.py, où `get_setting` et
# `get_boolean_setting` sont déjà définis.
#
# Pourquoi : InvenTree n'expose aucun réglage pour SESSION_COOKIE_AGE, on hérite
# donc du défaut de Django, soit 14 jours fermes depuis le login. Trop long pour
# une instance publique qui sert de démo client. On rend les deux réglages
# lisibles depuis l'environnement (ou config.yaml), en gardant les valeurs de
# Django par défaut : sans variable d'environnement, le comportement est
# strictement inchangé.
#
#   INVENTREE_SESSION_COOKIE_AGE            durée en secondes (défaut 1209600 = 14 j)
#   INVENTREE_SESSION_SAVE_EVERY_REQUEST    True = durée glissante, le compteur
#                                           repart à chaque requête, donc on est
#                                           déconnecté après X d'inactivité et
#                                           jamais en pleine utilisation. Coût :
#                                           une écriture dans django_session par
#                                           requête authentifiée.
# ---------------------------------------------------------------------------

SESSION_COOKIE_AGE = get_setting(  # noqa: F821
    "INVENTREE_SESSION_COOKIE_AGE", "cookie.age", 1209600, typecast=int
)

SESSION_SAVE_EVERY_REQUEST = get_boolean_setting(  # noqa: F821
    "INVENTREE_SESSION_SAVE_EVERY_REQUEST", "cookie.save_every_request", False
)
