"""Module de gestion des locations événementielles pour InvenTree"""

from plugin import InvenTreePlugin

from plugin.mixins import (
    AppMixin,
    EventMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
)

from . import PLUGIN_VERSION


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
            ExampleView,
            GeocodeAddressView,
            LieuDetailView,
            LieuListCreateView,
            ReservationDetailView,
            ReservationListCreateView,
        )

        return [
            path("example/", ExampleView.as_view(), name="example-view"),
            path("lieux/", LieuListCreateView.as_view(), name="lieu-list-create"),
            path("lieux/<int:pk>/", LieuDetailView.as_view(), name="lieu-detail"),
            path("geocode/", GeocodeAddressView.as_view(), name="geocode-address"),
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

    # User interface elements (from UserInterfaceMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/ui/

    # Custom UI panels
    def get_ui_panels(self, request, context: dict, **kwargs):
        """Return a list of custom panels to be rendered in the InvenTree user interface."""

        panels = []

        # Only display this panel for the 'part' target
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

        return panels

    # Custom dashboard items
    def get_ui_dashboard_items(self, request, context: dict, **kwargs):
        """Return a list of custom dashboard items to be rendered in the InvenTree user interface."""

        # Example: only display for 'staff' users
        if not request.user or not request.user.is_staff:
            return []

        items = []

        items.append({
            "key": "inventree-location-dashboard",
            "title": "InvenTree Location Dashboard Item",
            "description": "Custom dashboard item",
            "icon": "ti:dashboard:outline",
            "source": self.plugin_static_file(
                "Dashboard.js:renderInvenTreeLocationDashboardItem"
            ),
            "context": {
                "settings": self.get_settings_dict(),
                "bar": "foo",
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
