from django.contrib import admin

from .models import NotificationLog, NotificationPreference

admin.site.register(NotificationPreference)
admin.site.register(NotificationLog)
