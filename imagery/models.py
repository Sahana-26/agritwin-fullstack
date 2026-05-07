import uuid
from django.db import models
from django.contrib.gis.db import models as gis_models


class AnalysisRecord(models.Model):
    MODE_CHOICES = [
        ("historical", "Historical"),
        ("future", "Future"),
    ]
    SOURCE_CHOICES = [
        ("S2", "Sentinel-2"),
        ("S1_FALLBACK", "Sentinel-1 fallback"),
        ("S2_WITH_S1_SUPPORT", "Sentinel-2 with Sentinel-1 support"),
        ("UNAVAILABLE", "Unavailable"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("ready", "Ready"),
        ("failed", "Failed"),
        ("empty", "Empty"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # same run_id repeated across summary + all layer rows
    run_id = models.UUIDField(db_index=True)
    record_key = models.CharField(max_length=150, db_index=True)

    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    year = models.IntegerField(null=True, blank=True)
    season = models.CharField(max_length=30, null=True, blank=True)
    window_index = models.IntegerField(null=True, blank=True)
    window_label = models.CharField(max_length=50, null=True, blank=True)

    start_date = models.DateField()
    end_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    source_sensor = models.CharField(max_length=30, choices=SOURCE_CHOICES, default="UNAVAILABLE")
    source_collection = models.CharField(max_length=100, blank=True, default="")
    fallback_used = models.BooleanField(default=False)
    cloud_threshold = models.FloatField(default=90.0)
    mean_cloud_cover = models.FloatField(null=True, blank=True)
    valid_pixel_fraction = models.FloatField(null=True, blank=True)
    confidence = models.CharField(max_length=40, blank=True, default="")
    selected_item_ids = models.JSONField(default=list, blank=True)

    # run-level objects duplicated into every row
    summary_cards = models.JSONField(default=dict, blank=True)
    run_stats = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    mean_ndvi = models.FloatField(null=True, blank=True)
    mean_ndmi = models.FloatField(null=True, blank=True)
    mean_awei = models.FloatField(null=True, blank=True)

    # layer-level section
    analysis_type = models.CharField(max_length=60, db_index=True)  # summary, ndvi, ndmi, waterlite, ...
    rast = gis_models.RasterField(null=True, blank=True)
    extent = gis_models.PolygonField(srid=4326, null=True, blank=True)
    srid = models.IntegerField(default=4326)
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    band_count = models.IntegerField(default=1)
    nodata = models.FloatField(null=True, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    style_config = models.JSONField(default=dict, blank=True)
    stats = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["mode", "start_date", "record_key", "analysis_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["run_id", "analysis_type"],
                name="uniq_analysisrecord_run_analysis_type",
            )
        ]
        indexes = [
            models.Index(fields=["run_id"]),
            models.Index(fields=["record_key"]),
            models.Index(fields=["mode", "year", "season"]),
            models.Index(fields=["status"]),
            models.Index(fields=["analysis_type"]),
        ]

    def __str__(self):
        return f"{self.record_key} | {self.analysis_type} | {self.status}"