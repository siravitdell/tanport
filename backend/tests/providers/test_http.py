from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from app.providers.base import (
    ProviderAccessDeniedError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.providers.http import ProviderHttp
from app.ratelimit import RateLimiter

URL = "https://api.example.com/v1/quote"
SECRET = "sk-super-secret-key"


class SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@pytest.fixture
def sleep() -> SleepRecorder:
    return SleepRecorder()


@pytest.fixture
async def http(sleep: SleepRecorder) -> ProviderHttp:
    return ProviderHttp("example", httpx.AsyncClient(), retries=2, backoff_s=1, sleep=sleep)


@respx.mock
async def test_returns_json(http: ProviderHttp) -> None:
    route = respx.get(URL).respond(json={"c": 611.72})
    assert await http.get_json(URL, params={"symbol": "VOO", "token": SECRET}) == {"c": 611.72}
    assert route.calls.last.request.url.params["symbol"] == "VOO"


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_access_denied_is_not_retried_and_hides_key(http: ProviderHttp, status: int) -> None:
    route = respx.get(URL).respond(status, json={"error": "You don't have access"})
    with pytest.raises(ProviderAccessDeniedError) as info:
        await http.get_json(URL, params={"token": SECRET})
    assert route.call_count == 1
    assert SECRET not in str(info.value)
    assert "/v1/quote" in str(info.value)


@respx.mock
async def test_retries_server_errors_with_backoff(http: ProviderHttp, sleep: SleepRecorder) -> None:
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(502), httpx.Response(503), httpx.Response(200, json=[1])]
    )
    assert await http.get_json(URL) == [1]
    assert route.call_count == 3
    assert sleep.delays == [1, 2]


@respx.mock
async def test_gives_up_after_retries(http: ProviderHttp) -> None:
    respx.get(URL).respond(500)
    with pytest.raises(ProviderUnavailableError, match="3 attempts"):
        await http.get_json(URL, params={"token": SECRET})


@respx.mock
async def test_transport_errors_are_retried_without_leaking_url(http: ProviderHttp) -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectError(f"failed {URL}?token={SECRET}"))
    with pytest.raises(ProviderUnavailableError) as info:
        await http.get_json(URL, params={"token": SECRET})
    assert route.call_count == 3
    assert SECRET not in str(info.value)
    assert "ConnectError" in str(info.value)


@respx.mock
async def test_429_maps_to_rate_limited(http: ProviderHttp) -> None:
    respx.get(URL).respond(429, headers={"Retry-After": "30"})
    with pytest.raises(ProviderRateLimitedError) as info:
        await http.get_json(URL)
    assert info.value.retry_after_s == 30


@respx.mock
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404), "HTTP 404"),
        (httpx.Response(200, text="<html>oops</html>"), "invalid JSON"),
    ],
)
async def test_unusable_responses(
    http: ProviderHttp, response: httpx.Response, message: str
) -> None:
    respx.get(URL).mock(return_value=response)
    with pytest.raises(ProviderResponseError, match=message):
        await http.get_json(URL)


@respx.mock
async def test_local_limiter_blocks_before_calling(redis: Redis, sleep: SleepRecorder) -> None:
    route = respx.get(URL).respond(json={})
    limiter = RateLimiter(redis, "provider:example", limit=1, window_s=3600)
    http = ProviderHttp("example", httpx.AsyncClient(), limiter, limiter_max_wait_s=1, sleep=sleep)
    await http.get_json(URL)
    with pytest.raises(ProviderRateLimitedError) as info:
        await http.get_json(URL)
    assert route.call_count == 1
    assert info.value.retry_after_s is not None
    assert info.value.retry_after_s > 3000


@respx.mock
async def test_client_error_includes_body_with_sent_values_masked(http: ProviderHttp) -> None:
    respx.get(URL).respond(400, json={"message": f"Exceed limit period. token={SECRET} is fine"})
    with pytest.raises(ProviderResponseError) as info:
        await http.get_json(URL, params={"token": SECRET})
    message = str(info.value)
    assert "Exceed limit period" in message
    assert SECRET not in message
    assert "***" in message


@respx.mock
async def test_extra_limits_are_checked_first(redis: Redis, sleep: SleepRecorder) -> None:
    """A burst limit that refuses must not consume a slot of the daily quota."""
    route = respx.get(URL).respond(json={})
    daily = RateLimiter(redis, "daily", limit=5, window_s=86_400)
    burst = RateLimiter(redis, "burst", limit=1, window_s=3600)
    http = ProviderHttp(
        "example",
        httpx.AsyncClient(),
        daily,
        limiter_max_wait_s=0,
        extra_limits=[(burst, 0)],
        sleep=sleep,
    )
    await http.get_json(URL)
    with pytest.raises(ProviderRateLimitedError, match="burst"):
        await http.get_json(URL)
    assert route.call_count == 1
    assert (await redis.zcard("ratelimit:daily")) == 1
