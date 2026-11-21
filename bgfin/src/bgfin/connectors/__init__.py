"""Source connectors, one per institution."""

from .ameco import AmecoConnector
from .bis import BisConnector
from .ecb import EcbConnector
from .eurostat import EurostatConnector
from .imf import ImfConnector
from .nsi import NsiConnector
from .worldbank import WorldBankConnector

REGISTRY = {c.code: c for c in (EurostatConnector, EcbConnector, ImfConnector, WorldBankConnector,
                                 BisConnector, AmecoConnector, NsiConnector)}
