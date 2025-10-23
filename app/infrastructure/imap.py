from __future__ import annotations

import imaplib
import socket
import threading
from queue import Empty, Queue

from app.config import CONNECTION_TIMEOUT, IMAP_PORT, IMAP_SERVER, MAX_CONNECTIONS, SOCKET_TIMEOUT, logger


class IMAPConnectionPool:
    def __init__(self, max_connections: int = MAX_CONNECTIONS) -> None:
        self.max_connections = max_connections
        self.connections: dict[str, Queue[imaplib.IMAP4_SSL]] = {}
        self.connection_count: dict[str, int] = {}
        self.lock = threading.Lock()
        logger.info("Initialized IMAP connection pool with max_connections=%s", max_connections)

    def _create_connection(self, email: str, access_token: str) -> imaplib.IMAP4_SSL:
        try:
            socket.setdefaulttimeout(SOCKET_TIMEOUT)
            client = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            client.sock.settimeout(CONNECTION_TIMEOUT)
            auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")
            client.authenticate("XOAUTH2", lambda _: auth_string)
            logger.info("Successfully created IMAP connection for %s", email)
            return client
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create IMAP connection for %s: %s", email, exc)
            raise

    def get_connection(self, email: str, access_token: str) -> imaplib.IMAP4_SSL:
        with self.lock:
            if email not in self.connections:
                self.connections[email] = Queue(maxsize=self.max_connections)
                self.connection_count[email] = 0

            queue = self.connections[email]

            try:
                connection = queue.get_nowait()
                try:
                    connection.noop()
                    logger.debug("Reused existing IMAP connection for %s", email)
                    return connection
                except Exception:  # noqa: BLE001
                    self.connection_count[email] -= 1
            except Empty:
                pass

            if self.connection_count[email] < self.max_connections:
                connection = self._create_connection(email, access_token)
                self.connection_count[email] += 1
                return connection

            logger.warning("Max connections (%s) reached for %s, waiting...", self.max_connections, email)
            try:
                return queue.get(timeout=30)
            except Exception as exc:  # noqa: BLE001
                logger.error("Timeout waiting for connection for %s: %s", email, exc)
                raise

    def return_connection(self, email: str, connection: imaplib.IMAP4_SSL) -> None:
        if email not in self.connections:
            logger.warning("Attempting to return connection for unknown email: %s", email)
            return
        try:
            connection.noop()
            self.connections[email].put_nowait(connection)
            logger.debug("Successfully returned IMAP connection for %s", email)
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                if email in self.connection_count:
                    self.connection_count[email] = max(0, self.connection_count[email] - 1)
            logger.debug("Discarded invalid connection for %s: %s", email, exc)

    def close_all_connections(self, email: str | None = None) -> None:
        with self.lock:
            if email:
                if email in self.connections:
                    closed = 0
                    queue = self.connections[email]
                    while not queue.empty():
                        try:
                            conn = queue.get_nowait()
                            conn.logout()
                            closed += 1
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("Error closing connection: %s", exc)
                    self.connection_count[email] = 0
                    logger.info("Closed %s connections for %s", closed, email)
                return

            total_closed = 0
            for email_key in list(self.connections.keys()):
                count_before = self.connection_count.get(email_key, 0)
                self.close_all_connections(email_key)
                total_closed += count_before
            logger.info("Closed total %s connections for all accounts", total_closed)


imap_pool = IMAPConnectionPool()

__all__ = ["IMAPConnectionPool", "imap_pool"]
