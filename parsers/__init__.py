# parsers/__init__.py
from .insert_coin import InsertCoinParser
from .artsholic import ArtsholicParser
from .fangamer import FangamerParser
from .glitch_gear import GlitchGearParser

# Master registry of active storefront scraper plugins
ACTIVE_PARSERS = [
    InsertCoinParser(),
    ArtsholicParser(),
    FangamerParser(),
    GlitchGearParser()
]