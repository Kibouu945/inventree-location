"""Retire le compteur de stock parallèle du plugin.

Le stock physique appartient à InvenTree (`StockItem`) : `RentableItem` ne
garde que ce qu'InvenTree ne sait pas dire (louable, consommable, virtuel,
caution, valeur de remplacement, seuils d'alerte). Cf.
`conflicts.get_part_total_stock`.

⚠️ Les quantités saisies dans ce champ ne sont pas reprises automatiquement :
c'est la mise en stock InvenTree (`StockItem`) qui fait désormais foi. Un parc
déclaré ici sans exemplaire en stock apparaîtra à 0 tant qu'il n'est pas
inventorié côté InvenTree.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0009_rentableitem_seuil_alerte_haut"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="rentableitem",
            name="stock_total",
        ),
    ]
