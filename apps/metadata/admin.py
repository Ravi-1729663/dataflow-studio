from django.contrib import admin

from .models import (
    ColumnAnomaly,
    ColumnMetadata,
    ColumnStats,
    Dataset,
    LineageEdge,
    LineageNode,
    SchemaVersion,
)

admin.site.register(Dataset)
admin.site.register(SchemaVersion)
admin.site.register(ColumnMetadata)
admin.site.register(ColumnStats)
admin.site.register(ColumnAnomaly)
admin.site.register(LineageNode)
admin.site.register(LineageEdge)
