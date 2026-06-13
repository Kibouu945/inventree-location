"""API views for the InvenTreeLocation plugin."""

from datetime import date
import random
import string

from django.db.models import Q
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CatalogPartSerializer, ExampleSerializer


class ExampleView(APIView):
    """Example API view for the InvenTreeLocation plugin."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ExampleSerializer

    def get(self, request, *args, **kwargs):
        """Override the GET method to return example data."""

        from part.models import Part

        response_serializer = self.serializer_class(
            data={
                "random_text": "".join(random.choices(string.ascii_letters, k=50)),
                "part_count": Part.objects.count(),
                "today": date.today(),
            }
        )

        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=200)


class CatalogPagination(PageNumberPagination):
    """Pagination for catalog results."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CatalogPartListView(APIView):
    """List InvenTree parts with catalog filters.

    Supported query parameters:
    - search: text search on name, description and IPN
    - category: single category id
    - categories: comma-separated category ids
    - active: true / false
    - rentable: true / false

    Note:
    The rentable filter is temporarily mapped to the native InvenTree
    active flag until SCRUM-43 introduces a dedicated rentable flag.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CatalogPartSerializer
    pagination_class = CatalogPagination

    def get(self, request, *args, **kwargs):
        """Return a filtered and paginated catalog of InvenTree parts."""

        from part.models import Part

        queryset = Part.objects.select_related("category").all().order_by("name")

        search = request.query_params.get("search")
        category = request.query_params.get("category")
        categories = request.query_params.get("categories")
        active = request.query_params.get("active")
        rentable = request.query_params.get("rentable")

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(IPN__icontains=search)
            )

        category_ids = self._parse_category_ids(category, categories)

        if category_ids:
            queryset = queryset.filter(category_id__in=category_ids)

        active_value = self._parse_boolean(active)

        if active_value is not None:
            queryset = queryset.filter(active=active_value)

        rentable_value = self._parse_boolean(rentable)

        if rentable_value is not None:
            queryset = queryset.filter(active=rentable_value)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        serializer = self.serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def _parse_category_ids(self, category, categories):
        """Parse category filters from query parameters."""

        values = []

        if category:
            values.append(category)

        if categories:
            values.extend(categories.split(","))

        category_ids = []

        for value in values:
            value = str(value).strip()

            if value.isdigit():
                category_ids.append(int(value))

        return category_ids

    def _parse_boolean(self, value):
        """Parse boolean query parameter."""

        if value is None:
            return None

        value = str(value).lower().strip()

        if value in ["true", "1", "yes", "y"]:
            return True

        if value in ["false", "0", "no", "n"]:
            return False

        return None