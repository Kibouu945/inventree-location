FROM inventree/inventree:stable

# Copy plugin source into the container
COPY . /home/inventree/plugin/

# Install the plugin in editable mode so InvenTree discovers it via entry points
RUN pip install -e /home/inventree/plugin/
