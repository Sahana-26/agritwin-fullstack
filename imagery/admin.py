from django.contrib import admin
from .models import AnalysisRecord


@admin.register(AnalysisRecord)
class AnalysisRecordAdmin(admin.ModelAdmin):
    list_display = (
        "record_key",
        "run_id",
        "analysis_type",
        "mode",
        "year",
        "season",
        "start_date",
        "end_date",
        "status",
        "source_sensor",
        "fallback_used",
        "confidence",
    )
    list_filter = (
        "analysis_type",
        "mode",
        "season",
        "status",
        "source_sensor",
        "fallback_used",
    )
    search_fields = ("record_key", "run_id", "analysis_type")