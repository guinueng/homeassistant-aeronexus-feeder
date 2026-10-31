"""Acknowledge an explicit one-shot refresh through our own Supervisor options."""
import json
import logging
import os
from urllib.request import ProxyHandler, Request, build_opener

from relay import DiscoveryError, NoRedirect

LOG = logging.getLogger("aeronexus")
LIMIT = 1024 * 1024


def clear_refresh_request() -> bool:
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if not token:
        LOG.warning("Could not reset refresh_upstream: Supervisor token unavailable; turn the option off manually")
        return False
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())

        def call(path, body=None):
            headers = {"Authorization": f"Bearer {token}"}
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            request = Request("http://supervisor" + path, data=data, headers=headers)
            with opener.open(request, timeout=5) as response:
                raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("Oversize Supervisor response")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("result") != "ok":
                raise ValueError("Supervisor did not accept the request")
            return payload.get("data")

        # Read raw options, preserving !secret references and all other fields.
        # The options endpoint replaces the options dictionary, so a partial
        # dictionary must never be posted here.
        info = call("/addons/self/info")
        options = info.get("options") if isinstance(info, dict) else None
        if not isinstance(options, dict) or "uuid" not in options:
            raise ValueError("Missing own options")
        if options.get("refresh_upstream") is not True:
            return True  # The user has already cleared the request.
        updated = dict(options)
        updated["refresh_upstream"] = False
        call("/addons/self/options", {"options": updated})
        LOG.info("Manual upstream check complete; refresh_upstream reset to off")
        return True
    except (OSError, ValueError, TypeError, DiscoveryError) as exc:
        # Never print request/response bodies: they contain the user's options.
        LOG.warning("Could not reset refresh_upstream (%s); turn the option off manually", type(exc).__name__)
        return False
