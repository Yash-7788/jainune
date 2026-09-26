import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def test_pinned_supabase_client_signs_avatar_replacements_for_upsert():
    from app.services.media_processor import generate_supabase_upload_signed_url

    storage = MagicMock()
    storage.create_signed_upload_url.side_effect = TypeError(
        "create_signed_upload_url() got an unexpected keyword argument 'options'"
    )
    client = MagicMock()
    client.storage.from_.return_value = storage

    response = MagicMock()
    response.json.return_value = {
        "url": "/object/upload/sign/avatars/user123/avatar.webp?token=abc"
    }
    http = MagicMock()
    http.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=http)
    context.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.media_processor._get_supabase", return_value=client),
        patch("app.services.media_processor.httpx.AsyncClient", return_value=context),
        patch("app.services.media_processor.settings") as settings,
    ):
        settings.supabase_url = "https://project.supabase.co"
        settings.supabase_service_role_key = "service-secret"
        settings.supabase_storage_bucket = "avatars"
        settings.media_cdn_url = ""
        result = asyncio.run(generate_supabase_upload_signed_url("user123"))

    assert result["signed_url"] == (
        "https://project.supabase.co/storage/v1/object/upload/sign/"
        "avatars/user123/avatar.webp?token=abc"
    )
    assert http.post.await_args.kwargs["headers"]["x-upsert"] == "true"
    assert storage.create_signed_upload_url.call_args.kwargs["options"] == {"upsert": "true"}
