# Version épinglée, pas `stable`. Le CDC V06 l'exige (« la version InvenTree
# cible doit être épinglée ; chaque mise à jour d'InvenTree devra être testée
# contre le plugin »), et le 02/09/2026 a montré pourquoi : la prod avait été
# construite en 1.5.2 pendant que le poste de dev gardait une couche en 1.3.3.
# Un plantage du widget Organisation, reproductible en 1.5.2, était donc
# invisible en local. Monter de version est désormais un geste explicite :
# changer ce tag, relancer la suite et repasser au navigateur.
FROM inventree/inventree:1.5.2

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

# Bloque la retraduction automatique de l'interface par le navigateur : le
# script dit pourquoi, et échoue si le gabarit d'InvenTree a bougé.
RUN python3 /home/inventree/plugin/docker/bloquer_traduction_auto.py

# Met le catalogue de traductions du plugin en tête de LOCALE_PATHS, pour
# corriger les chaînes du cœur mal traduites (cf. locale/fr/LC_MESSAGES).
RUN cat /home/inventree/plugin/docker/locale_settings.py \
        >> /home/inventree/src/backend/InvenTree/InvenTree/settings.py
