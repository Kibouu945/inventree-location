from common.settings import set_global_setting
from plugin.models import PluginConfig

PLUGIN_KEY = "inventree-location"

TOGGLES = [
    "ENABLE_PLUGINS_APP",
    "ENABLE_PLUGINS_URL",
    "ENABLE_PLUGINS_INTERFACE",
    "ENABLE_PLUGINS_NAVIGATION",
    "ENABLE_PLUGINS_SCHEDULE",
    "ENABLE_PLUGINS_EVENTS",
]

plugin, _ = PluginConfig.objects.get_or_create(key=PLUGIN_KEY)

if not plugin.active:
    plugin.active = True
    plugin.save()
    print(f"  plugin '{PLUGIN_KEY}' activé")
else:
    print(f"  plugin '{PLUGIN_KEY}' déjà actif")

for key in TOGGLES:
    set_global_setting(key, True)
    print(f"  {key} = True")

print(
    "\nRedémarrage requis pour que ces réglages prennent effet : "
    "`docker compose restart inventree backend`."
)
