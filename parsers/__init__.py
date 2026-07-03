# parsers/__init__.py
from .insert_coin import InsertCoinParser
from .artsholic import ArtsholicParser
from .fangamer import FangamerParser
from .glitch_gear import GlitchGearParser
from .eightysixed import EightysixedParser
from .xbox import XboxGameStudiosParser
from .bethesda import BethesdaParser
from .blizzard import BlizzardParser

# Master registry of active storefront scraper plugins
ACTIVE_PARSERS = [
    InsertCoinParser(),
    ArtsholicParser(),
    FangamerParser(),
    GlitchGearParser(),
    EightysixedParser(),
    XboxGameStudiosParser(),
    BethesdaParser(),
    BlizzardParser()
]