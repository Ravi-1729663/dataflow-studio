from django.contrib import admin

from .models import DeadLetterRecord, Pipeline, PipelineRun

admin.site.register(Pipeline)
admin.site.register(PipelineRun)
admin.site.register(DeadLetterRecord)
