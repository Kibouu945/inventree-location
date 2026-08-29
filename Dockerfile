FROM inventree/inventree:stable

# Copy plugin source into the container
COPY . /home/inventree/plugin/

# Install the plugin in editable mode so InvenTree discovers it via entry points
RUN pip install -e /home/inventree/plugin/

# Rend SESSION_COOKIE_AGE / SESSION_SAVE_EVERY_REQUEST pilotables par
# l'environnement : InvenTree ne les expose pas et le défaut Django (14 jours
# fermes) est trop long pour l'instance publique. Le chemin de settings.py est
# en dur volontairement — si une version future d'InvenTree le déplace, le build
# échoue ici au lieu de livrer une prod où le réglage est ignoré en silence.
RUN test -f /home/inventree/src/backend/InvenTree/InvenTree/settings.py \
    && cat /home/inventree/plugin/docker/session_settings.py \
        >> /home/inventree/src/backend/InvenTree/InvenTree/settings.py
