from django.urls import path

from . import views

app_name = "enhancer"

urlpatterns = [
    # Pages
    path("", views.home, name="home"),
    path("result/<uuid:job_id>/", views.result, name="result"),
    path("history/", views.history, name="history"),
    path("about/", views.about, name="about"),
    path("job/<uuid:job_id>/delete/", views.delete_job, name="delete"),
    path("job/<uuid:job_id>/download/", views.download, name="download"),
    path("job/<uuid:job_id>/download/original/", views.download_original, name="download_original"),
    # JSON API
    path("api/upload/", views.api_upload, name="api_upload"),
    path("api/jobs/", views.api_jobs, name="api_jobs"),
    path("api/jobs/<uuid:job_id>/", views.api_status, name="api_status"),
    path("health/", views.health, name="health"),
]
