"""BIS Data Portal, SDMX 2.1 REST. https://stats.bis.org/api-doc/v1/"""

from __future__ import annotations

from .sdmx import SdmxConnector


class BisConnector(SdmxConnector):
    code = "bis"

    def url(self, dataset, key):
        return f"{self.cfg.api_base}/data/{dataset}/{key}/all"
