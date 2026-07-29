from django.urls import path

from . import views

app_name = "vault"

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("load-more/", views.load_more_view, name="load_more"),
    path("save/", views.save_text_view, name="save_text"),
    path("upload/", views.upload_file_view, name="upload_file"),
    path("search/", views.search_view, name="search"),
    path("favorites/", views.favorites_view, name="favorites"),
    path("trash/", views.trash_view, name="trash"),
    path("trash/empty/", views.empty_trash_view, name="empty_trash"),
    path("settings/", views.settings_view, name="settings"),
    path("item/<int:pk>/", views.item_detail_view, name="item_detail"),
    path("item/<int:pk>/edit/", views.item_edit_view, name="item_edit"),
    path("item/<int:pk>/favorite/", views.item_favorite_view, name="item_favorite"),
    path("item/<int:pk>/delete/", views.item_delete_view, name="item_delete"),
    path("item/<int:pk>/restore/", views.item_restore_view, name="item_restore"),
    path(
        "item/<int:pk>/permanent-delete/",
        views.item_permanent_delete_view,
        name="item_permanent_delete",
    ),
    path("item/<int:pk>/download/", views.item_download_view, name="item_download"),
    path("item/<int:pk>/raw/", views.item_raw_view, name="item_raw"),
]
