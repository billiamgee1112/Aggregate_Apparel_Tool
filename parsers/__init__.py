# parsers/__init__.py
from .insert_coin import InsertCoinParser
from .artsholic import ArtsholicParser
from .fangamer import FangamerParser
from .glitch_gear import GlitchGearParser
from .eightysixed import EightysixedParser
from .xbox import XboxGameStudiosParser
from .bethesda import BethesdaParser
from .blizzard import BlizzardParser
from .oceandust import OceanDustParser
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
ACTIVE_PARSERS = [
    InsertCoinParser(),
    ArtsholicParser(),
    FangamerParser(),
    GlitchGearParser(),
    EightysixedParser(),
    XboxGameStudiosParser(),
    BethesdaParser(),
    BlizzardParser(),
    OceanDustParser(),
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