"""Token health monitoring and scheduling."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException

from app.accounts import account_service
from app.accounts.credentials import get_account_credentials
from app.accounts.repository import AccountRepository
from app.config import logger
from app.oauth import fetch_access_token


DEFAULT_INTERVAL_MINUTES = 1440
MIN_INTERVAL_MINUTES = 60


@dataclass(slots=True)
class TokenHealthResult:
    total: int = 0
    success: int = 0
    failures: int = 0
    newly_expired: int = 0


@dataclass(slots=True)
class TokenHealthStatus:
    running: bool = False
    last_started_at: float | None = None
    last_completed_at: float | None = None
    last_result: TokenHealthResult | None = None


class TokenHealthService:
    def __init__(self, repository: AccountRepository) -> None:
        self._repository = repository

    async def run_once(self) -> TokenHealthResult:
        result = TokenHealthResult()
        accounts = self._repository.read_all()
        if not accounts:
            logger.info("Token health check skipped: no accounts available")
            return result

        for email in accounts.keys():
            result.total += 1
            try:
                credentials = get_account_credentials(self._repository, email, accounts=accounts)
            except HTTPException as exc:
                logger.warning("Skipping token check for %s: %s", email, exc.detail)
                continue

            try:
                await fetch_access_token(credentials)
                account_service.record_token_success(email)
                result.success += 1
            except HTTPException as exc:
                status_code = exc.status_code
                account_service.record_token_failure(
                    email,
                    status_code=status_code,
                    error_message=exc.detail,
                    operation="token_health_check"
                )
                if status_code == 401:
                    result.newly_expired += 1
                result.failures += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error checking token for %s: %s", email, exc)
                account_service.record_token_failure(
                    email,
                    error_message=str(exc),
                    operation="token_health_check"
                )
                result.failures += 1

        logger.info(
            "Token health check completed: total=%s success=%s failures=%s newly_expired=%s",
            result.total,
            result.success,
            result.failures,
            result.newly_expired,
        )
        return result


class TokenHealthScheduler:
    def __init__(
        self,
        service: TokenHealthService,
        enabled_provider: Callable[[], bool],
        interval_provider: Callable[[], int],
    ) -> None:
        self._service = service
        self._enabled_provider = enabled_provider
        self._interval_provider = interval_provider
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._trigger_event = asyncio.Event()
        self._status = TokenHealthStatus()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Token health scheduler started")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("Token health scheduler stopped")

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                if not self._enabled_provider():
                    await self._sleep_or_stop(5)
                    continue
                await self._run_once_with_status()
                await self._wait_for_next_run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Token health scheduler crashed: %s", exc, exc_info=True)
        finally:
            self._task = None

    def trigger_immediate(self) -> None:
        self._trigger_event.set()

    def last_run_result(self) -> TokenHealthResult | None:
        return self._status.last_result

    def status(self) -> TokenHealthStatus:
        return self._status

    async def _wait_for_next_run(self) -> None:
        interval_minutes = max(MIN_INTERVAL_MINUTES, self._interval_provider() or DEFAULT_INTERVAL_MINUTES)
        timeout = interval_minutes * 60
        self._trigger_event.clear()
        await self._wait_with_trigger(timeout)

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def _wait_with_trigger(self, timeout: float) -> None:
        try:
            done, _ = await asyncio.wait(
                [
                    asyncio.create_task(self._stop_event.wait()),
                    asyncio.create_task(self._trigger_event.wait()),
                ],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
        except asyncio.TimeoutError:
            return

    async def _run_once_with_status(self) -> None:
        self._status.running = True
        self._status.last_started_at = time.time()
        try:
            result = await self._service.run_once()
            self._status.last_result = result
        finally:
            self._status.running = False
            self._status.last_completed_at = time.time()
