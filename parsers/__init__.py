# parsers/__init__.py
from .insert_coin import InsertCoinParser
from .artsholic import ArtsholicParser
from .fangamer import FangamerParser
from .glitch_gear import GlitchGearParser
from .eightysixed import EightysixedParser
from .xbox import XboxGameStudiosParser
from .bethesda import BethesdaParser
from .blizzard import BlizzardParser
from .drkn import DrknParser
from .culture_kings import CultureKingsParser
from .sega import SegaParser
from .square_enix import SquareEnixParser
from .ign import IgnParser
from .sanshee import SansheeParser
from .atari import AtariParser
from .theyetee import TheYeteeParser
from .bioware import BioWareParser
from .cdprojektred import CdProjektRedParser

# Master registry of active storefront scraper plugins
# NOTE: OceanDust is deliberately NOT included here - their site added a
# Cloudflare bot-challenge in front of products.json that the automated
# scraper can't reliably get past (see parsers/oceandust.py for details).
# It's kept in the products database via periodic manual import instead
# (see import_oceandust_manual.py) - the OceanDustParser class itself is
# still used by that script, just not run automatically every scrape.
ACTIVE_PARSERS = [
    InsertCoinParser(),
    ArtsholicParser(),
    FangamerParser(),
    GlitchGearParser(),
    EightysixedParser(),
    XboxGameStudiosParser(),
    BethesdaParser(),
    BlizzardParser(),
    DrknParser(),
    CultureKingsParser(),
    SegaParser(),
    SquareEnixParser(),
    IgnParser(),
    SansheeParser(),
    AtariParser(),
    TheYeteeParser(),
    BioWareParser(),
    CdProjektRedParser()
]