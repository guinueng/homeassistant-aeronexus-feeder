"""Ask Supervisor to stop this app deliberately, avoiding watchdog restarts."""
import json
import logging
import os
from urllib.request import ProxyHandler, Request, build_opener

from relay import DiscoveryError, NoRedirect

LOG = logging.getLogger("aeronexus")


def request_app_stop() -> bool:
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if not token:
        LOG.warning("Supervisor token unavailable; relay remains stopped without reconnecting. Restart the app manually after resolving the UUID conflict")
        return False
    try:
        request = Request("http://supervisor/addons/self/stop", data=b"{}", method="POST",
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Oversize response")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("result") != "ok":
            raise ValueError("Stop not accepted")
        return True
    except (OSError, ValueError, TypeError, DiscoveryError) as exc:
        # Never include a token, response body, or user options in this log.
        LOG.warning("Supervisor stop request did not complete (%s); relay remains stopped without reconnecting. Restart the app manually after resolving the UUID conflict", type(exc).__name__)
        return False
