"""Admin site configuration for the InvenTreeLocation plugin."""

from django.contrib import admin

from .models import ExampleModel, Reservation


@admin.register(ExampleModel)
class ExampleModelAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "counter",
    )
    list_filter = ("user",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("id", "part", "qty", "status", "start", "end")
    list_filter = ("status", "part")
    search_fields = ("part__name",)
    ordering = ("start", "end")
