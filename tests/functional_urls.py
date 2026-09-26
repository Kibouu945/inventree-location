"""URLConf de test fonctionnel."""

from django.urls import include, path

from inventree_location.views import (
    CatalogPartListView,
    DeliveryAccepterView,
    DeliveryEtatView,
    DeliveryListView,
    ExampleView,
    GeocodeAddressView,
    LieuDetailView,
    LieuListCreateView,
    RentableFlagBulkUpdateView,
    RentablePartDetailView,
    ReservationDetailView,
    ReservationCalendarView,
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
    path(
        "reservations/calendar/",
        ReservationCalendarView.as_view(),
        name="reservation-calendar",
    ),
    path("deliveries/", DeliveryListView.as_view(), name="delivery-list"),
    path(
        "deliveries/<int:pk>/accepter/",
        DeliveryAccepterView.as_view(),
        name="delivery-accepter",
    ),
    path(
        "deliveries/<int:pk>/etat/",
        DeliveryEtatView.as_view(),
        name="delivery-etat",
    ),
]

urlpatterns = [
    path("plugin/inventree-location/", include(plugin_patterns)),
]
