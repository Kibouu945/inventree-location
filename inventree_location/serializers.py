"""API serializers for the InvenTreeLocation plugin."""

from rest_framework import serializers


class ExampleSerializer(serializers.Serializer):
    """Example serializer for the InvenTreeLocation plugin."""

    class Meta:
        """Meta options for this serializer."""

        fields = [
            "random_text",
            "part_count",
            "today",
        ]

    random_text = serializers.CharField(
        max_length=100,
        required=True,
        label="Random Text",
        help_text="A text field containing randomly generated data.",
    )

    part_count = serializers.IntegerField(
        label="Number of Parts",
        help_text="Total number of parts in the InvenTree database.",
    )

    today = serializers.DateField(
        required=False,
        label="Today",
        help_text="The current date.",
    )


class CatalogPartSerializer(serializers.Serializer):
    """Serializer used to expose InvenTree parts in the rental catalog."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    IPN = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    active = serializers.BooleanField(read_only=True)
    category = serializers.IntegerField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    rentable = serializers.SerializerMethodField()

    def get_rentable(self, obj):
        """Temporary rentable flag.

        SCRUM-43 will introduce a dedicated rentable/non-rentable flag.
        Until then, active parts are considered rentable.
        """
        return bool(getattr(obj, "active", False))