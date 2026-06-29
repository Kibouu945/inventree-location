"""URLConf de test fonctionnel.

Monte les endpoints du plugin sous le même préfixe qu'en production
(`/plugin/inventree-location/`) afin d'exercer la chaîne complète
routage -> authentification -> permission -> vue -> serializer -> base.

Le préfixe et la liste reflètent `InventreeLocationPlugin.setup_urls`
(cf. inventree_location/core.py). Le module `core` n'étant pas importable
hors d'InvenTree, on reconstruit les patterns à partir des vues.
"""

from django.urls import include, path

from inventree_location.views import (
    CatalogPartListView,
    ExampleView,
    GeocodeAddressView,
    LieuDetailView,
    LieuListCreateView,
    RentableFlagBulkUpdateView,
    RentablePartDetailView,
    ReservationDetailView,
    ReservationListCreateView,
)

plugin_patterns = [
    path("example/", ExampleView.as_view(), name="example-view"),
    path("lieux/", LieuListCreateView.as_view(), name="lieu-list-create"),
    path("lieux/<int:pk>/", LieuDetailView.as_view(), name="lieu-detail"),
    path("geocode/", GeocodeAddressView.as_view(), name="geocode-address"),
    path("catalog/", CatalogPartListView.as_view(), name="catalog-part-list"),
    path(
        "catalog/rentable/",
        RentableFlagBulkUpdateView.as_view(),
        name="catalog-rentable-bulk-update",
    ),
    path(
        "catalog/<int:pk>/rentable/",
        RentablePartDetailView.as_view(),
        name="catalog-part-rentable-detail",
    ),
    path(
        "reservations/",
        ReservationListCreateView.as_view(),
        name="reservation-list",
    ),
    path(
        "reservations/<int:pk>/",
        ReservationDetailView.as_view(),
        name="reservation-detail",
    ),
]

urlpatterns = [
    path("plugin/inventree-location/", include(plugin_patterns)),
]
