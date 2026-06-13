"""Custom model definitions for the InvenTreeLocation plugin.

This file is where you can define any custom database models.

- Any models defined here will require database migrations to be created.
- Don't forget to register your models in the admin interface if needed!
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class ExampleModel(models.Model):
    """An example model for the InvenTreeLocation plugin."""

    class Meta:
        """Meta options for the model."""

        app_label = "inventree_location"
        verbose_name = _("Example Model")
        verbose_name_plural = _("Example Models")

    user = models.OneToOneField(
        User,
        unique=True,
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="example_model",
        help_text=_("The user associated with this example model"),
    )

    counter = models.IntegerField(
        default=0,
        verbose_name=_("Counter"),
        help_text=_("A simple counter for the example model"),
    )


class Reservation(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_CONFIRMED = "confirmée"
    STATUS_DELIVERED = "livrée"
    STATUS_RETURNED = "retournée"

    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Brouillon")),
        (STATUS_CONFIRMED, _("Confirmée")),
        (STATUS_DELIVERED, _("Livrée")),
        (STATUS_RETURNED, _("Retournée")),
    ]

    class Meta:
        app_label = "inventree_location"
        verbose_name = _("Reservation")
        verbose_name_plural = _("Reservations")
        ordering = ["start", "end"]

    part = models.ForeignKey(
        "part.Part",
        on_delete=models.CASCADE,
        related_name="location_reservations",
        verbose_name=_("Part"),
    )

    qty = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Quantité"),
        help_text=_("Quantité d'éléments réservés pendant la période."),
    )

    start = models.DateField(
        verbose_name=_("Date de début"),
        help_text=_("Date de début de la réservation."),
    )

    end = models.DateField(
        verbose_name=_("Date de fin"),
        help_text=_("Date de fin de la réservation."),
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name=_("Statut"),
        help_text=_("Statut de la réservation."),
    )

    def __str__(self):
        return f"Reservation #{self.pk} - {self.part} ({self.start} → {self.end})"
