"""Module de gestion des locations événementielles pour InvenTree"""

from plugin import InvenTreePlugin

from plugin.mixins import (
    AppMixin,
    EventMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
)

from . import PLUGIN_VERSION, roles


class InvenTreeLocation(
    AppMixin, EventMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin, InvenTreePlugin
):
    """InvenTreeLocation - custom InvenTree plugin."""

    # Plugin metadata
    TITLE = "InvenTree Location"
    NAME = "InvenTreeLocation"
    SLUG = "inventree-location"
    DESCRIPTION = "Module de gestion des locations événementielles pour InvenTree"
    VERSION = PLUGIN_VERSION

    # Additional project information
    AUTHOR = "groupe-6"
    WEBSITE = "https://github.com/Kibouu945/inventree-location"
    LICENSE = "MIT"

    # Optionally specify supported InvenTree versions
    # MIN_VERSION = '0.18.0'
    # MAX_VERSION = '2.0.0'

    # Render custom UI elements to the plugin settings page
    ADMIN_SOURCE = "Settings.js:renderPluginSettings"

    # Plugin settings (from SettingsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/settings/
    SETTINGS = {
        "CUSTOM_VALUE": {
            "name": "Custom Value",
            "description": "A custom value",
            "validator": int,
            "default": 42,
        }
    }

    # Respond to InvenTree events (from EventMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/event/
    def wants_process_event(self, event: str) -> bool:
        """Return True if the plugin wants to process the given event."""
        return event == "part_part.created"

    def process_event(self, event: str, *args, **kwargs) -> None:
        """Process the provided event."""
        print("Processing custom event:", event)
        print("Arguments:", args)
        print("Keyword arguments:", kwargs)

    # Custom URL endpoints (from UrlsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/urls/
    def setup_urls(self):
        """Configure custom URL endpoints for this plugin."""
        from django.urls import path

        from .views import (
            CatalogPartDetailView,
            CatalogPartListView,
            ConflictsListView,
            ExampleView,
            GeocodeAddressView,
            GroupeListView,
            LieuDetailView,
            LieuListCreateView,
            ManifestationDetailView,
            ManifestationListCreateView,
            PrestationDetailView,
            PrestationListCreateView,
            PrestationStockPreviewView,
            PrestationStockView,
            RentableFlagBulkUpdateView,
            RentablePartDetailView,
            ReservationCheckinView,
            ReservationConflictCheckView,
            ReservationDetailView,
            ReservationListCreateView,
            ReservationTransitionView,
            StockAlertListView,
            UserListView,
        )

        return [
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
                "catalog/<int:pk>/",
                CatalogPartDetailView.as_view(),
                name="catalog-part-detail",
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
                "reservations/<int:pk>/transition/",
                ReservationTransitionView.as_view(),
                name="reservation-transition",
            ),
            path(
                "reservations/<int:pk>/checkin/",
                ReservationCheckinView.as_view(),
                name="reservation-checkin",
            ),
            path("conflicts/", ConflictsListView.as_view(), name="conflict-list"),
            path(
                "reservations/<int:pk>/conflicts/",
                ReservationConflictCheckView.as_view(),
                name="reservation-conflict-check",
            ),
            path(
                "manifestations/",
                ManifestationListCreateView.as_view(),
                name="manifestation-list-create",
            ),
            path(
                "manifestations/<int:pk>/",
                ManifestationDetailView.as_view(),
                name="manifestation-detail",
            ),
            path(
                "prestations/",
                PrestationListCreateView.as_view(),
                name="prestation-list-create",
            ),
            path(
                "prestations/stock-preview/",
                PrestationStockPreviewView.as_view(),
                name="prestation-stock-preview",
            ),
            path(
                "prestations/<int:pk>/",
                PrestationDetailView.as_view(),
                name="prestation-detail",
            ),
            path(
                "prestations/<int:pk>/stock/",
                PrestationStockView.as_view(),
                name="prestation-stock",
            ),
            path(
                "groupes/",
                GroupeListView.as_view(),
                name="groupe-list",
            ),
            path(
                "users/",
                UserListView.as_view(),
                name="user-list",
            ),
            path(
                "alerts/stock/",
                StockAlertListView.as_view(),
                name="stock-alert-list",
            ),
        ]

    # User interface elements (from UserInterfaceMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/ui/

    def get_ui_panels(self, request, context: dict, **kwargs):
        """Return a list of custom panels to be rendered in the InvenTree user interface."""

        panels = []

        if context.get("target_model") == "part":
            panels.append({
                "key": "inventree-location-panel",
                "title": "InvenTree Location",
                "description": "Custom panel description",
                "icon": "ti:mood-smile:outline",
                "source": self.plugin_static_file(
                    "Panel.js:renderInvenTreeLocationPanel"
                ),
                "context": {
                    "settings": self.get_settings_dict(),
                    "foo": "bar",
                },
            })

            panels.append({
                "key": "inventree-location-part-detail",
                "title": "Fiche location",
                "description": "Fiche détail location de l'article",
                "icon": "ti:file-description:outline",
                "source": self.plugin_static_file(
                    "PartDetail.js:renderInvenTreeLocationPartDetail"
                ),
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        return panels

    def get_ui_dashboard_items(self, request, context: dict, **kwargs):
        """Return a list of custom dashboard items to be rendered in the InvenTree user interface."""

        # Filtrage RBAC métier basé sur les 7 groupes (cf. roles.py)
        visible_keys = roles.visible_dashboard_widget_keys(request.user)

        if not visible_keys:
            return []

        def visible(key):
            return key in visible_keys

        items = []

        if visible("inventree-location-catalog"):
            items.append({
                "key": "inventree-location-catalog",
                "title": "Catalogue du matériel",
                "description": "Liste filtrable du matériel louable",
                "icon": "ti:list-search:outline",
                "source": self.plugin_static_file(
                    "Catalog.js:renderInvenTreeLocationCatalog"
                ),
                # Seul widget à ne pas déclarer sa taille, il retombait sur la
                # boîte par défaut : un tableau de 5 colonnes y tenait dans une
                # colonne, illisible. Même gabarit que les autres écrans.
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        if visible("inventree-location-organisation"):
            items.append({
                "key": "inventree-location-organisation",
                "title": "Organisation",
                "description": ("Gestion des manifestations, prestations et lieux"),
                "icon": "ti:calendar-cog:outline",
                "source": self.plugin_static_file(
                    "Organisation.js:renderInvenTreeLocationOrganisation"
                ),
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        if visible("inventree-location-reservations"):
            items.append({
                "key": "inventree-location-reservations",
                "title": "Réservations",
                "description": "Création et suivi des réservations de matériel",
                "icon": "ti:calendar-event:outline",
                "source": self.plugin_static_file(
                    "Reservations.js:renderInvenTreeLocationReservations"
                ),
                # Liste dense (filtres + tableau + modale)
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        if visible("inventree-location-conflicts"):
            conflicts_count = 0

            try:
                from .conflicts import count_current_conflicts

                conflicts_count = count_current_conflicts()
            except Exception:
                conflicts_count = 0

            items.append({
                "key": "inventree-location-conflicts",
                "title": f"Conflits actuels ({conflicts_count})",
                "description": "Liste des réservations actuellement en conflit",
                "icon": "ti:alert-triangle:outline",
                "source": self.plugin_static_file(
                    "Conflicts.js:renderInvenTreeLocationConflicts"
                ),
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        if visible("inventree-location-stock-alerts"):
            items.append({
                "key": "inventree-location-stock-alerts",
                "title": "Alertes stock",
                "description": "Seuils bas/hauts et tension projetée",
                "icon": "ti:bell-ringing:outline",
                "source": self.plugin_static_file(
                    "Dashboard.js:renderInvenTreeLocationDashboardItem"
                ),
                "options": {
                    "width": 12,
                    "height": 6,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        return items

    def get_ui_spotlight_actions(self, request, context, **kwargs):
        """Return a list of custom spotlight actions to be made available."""
        return [
            {
                "key": "sample-spotlight-action",
                "title": "Hello Action",
                "description": "Hello from InvenTreeLocation",
                "icon": "ti:heart-handshake:outline",
                "source": self.plugin_static_file(
                    "Spotlight.js:InvenTreeLocationSpotlightAction"
                ),
            }
        ]
