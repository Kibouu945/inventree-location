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

    TITLE = "InvenTree Location"
    NAME = "InvenTreeLocation"
    SLUG = "inventree-location"
    DESCRIPTION = "Module de gestion des locations événementielles pour InvenTree"
    VERSION = PLUGIN_VERSION

    AUTHOR = "groupe-6"
    WEBSITE = "https://github.com/Kibouu945/inventree-location"
    LICENSE = "MIT"

    ADMIN_SOURCE = "Settings.js:renderPluginSettings"

    SETTINGS = {
        "CUSTOM_VALUE": {
            "name": "Custom Value",
            "description": "A custom value",
            "validator": int,
            "default": 42,
        }
    }

    def wants_process_event(self, event: str) -> bool:
        """Return True if the plugin wants to process the given event."""

        return event == "part_part.created"

    def process_event(self, event: str, *args, **kwargs) -> None:
        """Process the provided event."""

        print("Processing custom event:", event)
        print("Arguments:", args)
        print("Keyword arguments:", kwargs)

    def setup_urls(self):
        """Configure custom URL endpoints for this plugin."""

        from django.urls import path

        from .backoffice import (
            BackOfficeRoleListView,
            BackOfficeUserDetailView,
            BackOfficeUserListCreateView,
        )
        from .part_backoffice import (
            PartBackOfficeDetailView,
            PartBackOfficeListCreateView,
        )
        from .views import (
            BonRamassageView,
            CatalogPartDetailView,
            CatalogPartListView,
            ConflictsListView,
            ExampleView,
            GeocodeAddressView,
            LieuDetailView,
            LieuListCreateView,
            PrestationListView,
            RamassageListView,
            RentableFlagBulkUpdateView,
            RentablePartDetailView,
            ReservationConflictCheckView,
            ReservationDetailView,
            ReservationListCreateView,
            ReservationTransitionView,
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
                "reservations/<int:pk>/conflicts/",
                ReservationConflictCheckView.as_view(),
                name="reservation-conflict-check",
            ),
            path(
                "ramassages/",
                RamassageListView.as_view(),
                name="ramassage-list",
            ),
            path(
                "ramassages/<int:pk>/bon/",
                BonRamassageView.as_view(),
                name="ramassage-bon",
            ),
            path(
                "backoffice/users/",
                BackOfficeUserListCreateView.as_view(),
                name="backoffice-user-list-create",
            ),
            path(
                "backoffice/users/<int:pk>/",
                BackOfficeUserDetailView.as_view(),
                name="backoffice-user-detail",
            ),
            path(
                "backoffice/parts/",
                PartBackOfficeListCreateView.as_view(),
                name="backoffice-part-list-create",
            ),
            path(
                "backoffice/parts/<int:pk>/",
                PartBackOfficeDetailView.as_view(),
                name="backoffice-part-detail",
            ),
            path(
                "backoffice/roles/",
                BackOfficeRoleListView.as_view(),
                name="backoffice-role-list",
            ),
            path("conflicts/", ConflictsListView.as_view(), name="conflict-list"),
            path(
                "prestations/",
                PrestationListView.as_view(),
                name="prestation-list",
            ),
            path(
                "users/",
                UserListView.as_view(),
                name="user-list",
            ),
        ]

    def get_ui_panels(self, request, context: dict, **kwargs):
        """Return custom panels for the InvenTree user interface."""

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
        """Return custom dashboard items for the InvenTree user interface."""

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
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        if visible("inventree-location-ramassages"):
            items.append({
                "key": "inventree-location-ramassages",
                "title": "Mes ramassages",
                "description": "Liste des ramassages à effectuer après les prestations",
                "icon": "ti:truck-delivery:outline",
                "source": self.plugin_static_file(
                    "Ramassages.js:renderInvenTreeLocationRamassages"
                ),
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

        if visible("inventree-location-backoffice-users"):
            items.append({
                "key": "inventree-location-backoffice-users",
                "title": "Back-office utilisateurs",
                "description": "Créer, éditer, activer et affecter les rôles utilisateurs",
                "icon": "ti:users-group:outline",
                "source": self.plugin_static_file(
                    "BackOfficeUsers.js:renderInvenTreeLocationBackOfficeUsers"
                ),
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        if visible("inventree-location-backoffice-parts"):
            items.append({
                "key": "inventree-location-backoffice-parts",
                "title": "Back-office Parts",
                "description": "Créer, éditer, activer et déclarer les Parts louables",
                "icon": "ti:packages:outline",
                "source": self.plugin_static_file(
                    "BackOfficeParts.js:renderInvenTreeLocationBackOfficeParts"
                ),
                "options": {
                    "width": 12,
                    "height": 8,
                },
                "context": {
                    "settings": self.get_settings_dict(),
                },
            })

        return items

    def get_ui_spotlight_actions(self, request, context, **kwargs):
        """Return custom spotlight actions."""

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