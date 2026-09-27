from django.urls import path
from .views import (
    DocumentListCreateView, DocumentDetailView, DocumentInsightsView,
    WorkspaceListCreateView, WorkspaceDetailView,
)

urlpatterns = [
    path("documents/", DocumentListCreateView.as_view(), name="document-list-create"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<int:pk>/insights/", DocumentInsightsView.as_view(), name="document-insights"),
    path("workspaces/", WorkspaceListCreateView.as_view(), name="workspace-list-create"),
    path("workspaces/<int:pk>/", WorkspaceDetailView.as_view(), name="workspace-detail"),
]
