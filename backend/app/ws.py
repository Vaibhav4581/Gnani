"""WebSocket connections for volunteer, kitchen, NGO and dashboard pages."""
import logging
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger(__name__)


class Hub:
    """Who is connected, and sending JSON to them. A person may have several tabs open."""

    def __init__(self) -> None:
        self._volunteers: dict[int, set[WebSocket]] = defaultdict(set)
        self._kitchens: dict[int, set[WebSocket]] = defaultdict(set)
        self._ngos: dict[int, set[WebSocket]] = defaultdict(set)
        self._dashboards: set[WebSocket] = set()

    def add_volunteer(self, volunteer_id: int, ws: WebSocket) -> None:
        self._volunteers[volunteer_id].add(ws)

    def remove_volunteer(self, volunteer_id: int, ws: WebSocket) -> None:
        self._volunteers[volunteer_id].discard(ws)

    def add_kitchen(self, kitchen_id: int, ws: WebSocket) -> None:
        self._kitchens[kitchen_id].add(ws)

    def remove_kitchen(self, kitchen_id: int, ws: WebSocket) -> None:
        self._kitchens[kitchen_id].discard(ws)

    def add_ngo(self, ngo_id: int, ws: WebSocket) -> None:
        self._ngos[ngo_id].add(ws)

    def remove_ngo(self, ngo_id: int, ws: WebSocket) -> None:
        self._ngos[ngo_id].discard(ws)

    def add_dashboard(self, ws: WebSocket) -> None:
        self._dashboards.add(ws)

    def remove_dashboard(self, ws: WebSocket) -> None:
        self._dashboards.discard(ws)

    def has_dashboards(self) -> bool:
        return bool(self._dashboards)

    def is_online(self, volunteer_id: int) -> bool:
        return bool(self._volunteers.get(volunteer_id))

    def online_volunteers(self) -> set[int]:
        """Volunteers on duty: at least one page open."""
        return {vid for vid, sockets in self._volunteers.items() if sockets}

    async def to_volunteer(self, volunteer_id: int, message: dict) -> bool:
        return await self._send(self._volunteers.get(volunteer_id, set()), message)

    async def to_kitchen(self, kitchen_id: int, message: dict) -> bool:
        return await self._send(self._kitchens.get(kitchen_id, set()), message)

    async def to_ngo(self, ngo_id: int, message: dict) -> bool:
        return await self._send(self._ngos.get(ngo_id, set()), message)

    async def to_dashboards(self, message: dict) -> bool:
        return await self._send(self._dashboards, message)

    async def to_all_volunteers(self, message: dict) -> None:
        for sockets in self._volunteers.values():
            await self._send(sockets, message)

    async def to_all_ngos(self, message: dict) -> None:
        for sockets in self._ngos.values():
            await self._send(sockets, message)

    async def to_all_kitchens(self, message: dict) -> None:
        for sockets in self._kitchens.values():
            await self._send(sockets, message)

    @staticmethod
    async def _send(sockets: set[WebSocket], message: dict) -> bool:
        delivered = False
        for ws in list(sockets):
            try:
                await ws.send_json(message)
                delivered = True
            except Exception:  # closed mid-send; the page's disconnect handler cleans up
                log.debug("dropping dead socket", exc_info=True)
                sockets.discard(ws)
        return delivered
