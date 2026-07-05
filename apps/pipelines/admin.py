from django.contrib import admin

from .models import Pipeline, PipelineRun

admin.site.register(Pipeline)
admin.site.register(PipelineRun)
