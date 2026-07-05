from django.contrib import admin

from .models import ColumnMetadata, Dataset, LineageEdge, LineageNode, SchemaVersion

admin.site.register(Dataset)
admin.site.register(SchemaVersion)
admin.site.register(ColumnMetadata)
admin.site.register(LineageNode)
admin.site.register(LineageEdge)
