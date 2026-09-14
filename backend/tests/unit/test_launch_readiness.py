import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.metrics import metrics_registry


@pytest.mark.parametrize("value", ["productionn", "preview", "", None])
def test_unknown_environment_cannot_silently_enable_development_paths(value):
    with pytest.raises(ValidationError):
        Settings(environment=value, _env_file=None)


@pytest.mark.asyncio
async def test_metrics_do_not_store_arbitrary_paths_or_http_methods(client):
    before = set(metrics_registry.request_counts)
    for i in range(12):
        response = await client.request(f"ATTACK{i}", f"/nonexistent-{i}")
        assert response.status_code == 404
    added = set(metrics_registry.request_counts) - before
    assert added <= {("OTHER", "unmatched", "404")}
    assert not any("nonexistent-" in key[1] for key in metrics_registry.request_counts)


@pytest.mark.asyncio
async def test_metrics_use_route_template_for_private_profile_ids(client):
    for user_id in ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"]:
        response = await client.get(f"/v1/users/{user_id}/public")
        assert response.status_code in (401, 403)
        assert not any(user_id in key[1] for key in metrics_registry.request_counts)
    assert any(key[1] == "/v1/users/{user_id}/public" for key in metrics_registry.request_counts)
