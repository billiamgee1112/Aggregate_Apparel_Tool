# database.py
import sqlite3
import json
from models import GamingClothingItem

DB_NAME = "apparel_aggregator.db"

# Our baseline initial configuration ruleset
DEFAULT_RULESET = [
    # Final Fantasy series
    ("final-fantasy", "Final Fantasy"),
    ("final fantasy", "Final Fantasy"),
    ("aerith", "Final Fantasy"),
    ("cloud-strife", "Final Fantasy"),
    ("tifa", "Final Fantasy"),
    ("sephiroth", "Final Fantasy"),
    
    # League of Legends / LoL
    ("league-of-legends", "League of Legends"),
    ("league of legends", "League of Legends"),
    ("lol", "League of Legends"),
    ("ahri", "League of Legends"),
    ("jinx", "League of Legends"),
    ("yasuo", "League of Legends"),
    
    # Okami
    ("okami", "Okami"),
    ("amaterasu", "Okami"),
    
    # Black Clover
    ("black-clover", "Black Clover"),
    ("black clover", "Black Clover"),
    ("asta", "Black Clover"),

    # BioShock
    ("bioshock", "BioShock"),
    
    # Black Myth: Wukong
    ("black myth wukong", "Black Myth: Wukong"),
    ("black-myth-wukong", "Black Myth: Wukong"),
    ("wukongsweatshirt", "Black Myth: Wukong"),
    ("wukong", "Black Myth: Wukong"),
    
    # Bloodborne
    ("bloodborne", "Bloodborne"),
    
    # Crash Bandicoot
    ("crash bandicoot", "Crash Bandicoot"),
    ("crash-bandicoot", "Crash Bandicoot"),
    
    # Devil May Cry
    ("devil may cry", "Devil May Cry"),
    ("devil-may-cry", "Devil May Cry"),
    ("dante", "Devil May Cry"),
    ("nero", "Devil May Cry"),
    ("vergil", "Devil May Cry"),
    
    # One Piece
    ("one piece", "One Piece"),
    ("one-piece", "One Piece"),
    ("devil fruit", "One Piece"),
    ("luffy", "One Piece"),
    ("zoro", "One Piece"),
    
    # Marvel / Avengers
    ("avengers", "Marvel"),
    ("marvel", "Marvel"),
    ("comics", "Marvel"),
    
    # Disney / Cinderella
    ("cinderella", "Disney"),
    ("disney", "Disney"),

    # Acronyms & Abbreviations
    ("loz", "The Legend of Zelda"),
    ("zelda", "The Legend of Zelda"),
    ("botw", "The Legend of Zelda"),
    ("totk", "The Legend of Zelda"),
    ("link-", "The Legend of Zelda"),
    
    ("ac", "Assassin's Creed"),
    ("valhalla", "Assassin's Creed"),
    ("ezio", "Assassin's Creed"),
    ("altair", "Assassin's Creed"),
    ("assassin's-creed", "Assassin's Creed"),
    ("assassins-creed", "Assassin's Creed"),
    ("assassin's creed", "Assassin's Creed"),
    ("assassins creed", "Assassin's Creed"),
    ("assassin", "Assassin's Creed"),
    ("assassins", "Assassin's Creed"),
    ("ac valhalla", "Assassin's Creed"),
    
    ("re", "Resident Evil"),
    ("resident-evil", "Resident Evil"),
    ("raccoon-", "Resident Evil"),
    ("umbrella-", "Resident Evil"),
    ("s.t.a.r.s.", "Resident Evil"),
    
    ("silent-hill", "Silent Hill"),
    ("pyramid-head", "Silent Hill"),
    ("silent hill", "Silent Hill"),
    ("pyramid head", "Silent Hill"),
    ("silent-hill-2", "Silent Hill"),
    ("silent hill 2", "Silent Hill"),
    ("silent-hill-3", "Silent Hill"),
    ("silent hill 3", "Silent Hill"),
    ("silent-hill-4", "Silent Hill"),
    ("silent hill 4", "Silent Hill"),
    ("silent-hill-5", "Silent Hill"),
    ("silent hill 5", "Silent Hill"),
    
    ("mario", "Super Mario"),
    ("luigi", "Super Mario"),
    ("peach", "Super Mario"),
    ("bowser", "Super Mario"),
    ("yoshi", "Super Mario"),
    ("toad", "Super Mario"),
    ("wario", "Super Mario"),
    ("waluigi", "Super Mario"),
    ("super-mario", "Super Mario"),
    ("super mario", "Super Mario"),
    ("mario-kart", "Super Mario"),
    ("mario kart", "Super Mario"),
    ("mario-party", "Super Mario"),
    ("mario party", "Super Mario"),
    ("mario-odyssey", "Super Mario"),
    ("mario odyssey", "Super Mario"),
    ("mario-bros", "Super Mario"),
    ("mario bros", "Super Mario"),
    ("smash-bros", "Super Mario"),
    ("smash bros", "Super Mario"),
    ("super-smash-bros", "Super Mario"),
    ("super smash bros", "Super Mario"),
    
    ("sonic", "Sonic the Hedgehog"),
    ("tails", "Sonic the Hedgehog"),
    ("eggman", "Sonic the Hedgehog"),
    ("shadow-stripe", "Sonic the Hedgehog"),
    ("knuckles", "Sonic the Hedgehog"),
    ("dr-eggman", "Sonic the Hedgehog"),
    ("dr eggman", "Sonic the Hedgehog"),
    
    ("cyberpunk", "Cyberpunk 2077"),
    ("edgerunners", "Cyberpunk 2077"),
    ("arasaka", "Cyberpunk 2077"),
    ("night-city", "Cyberpunk 2077"),
    ("johnny-silverhand", "Cyberpunk 2077"),
    ("panam", "Cyberpunk 2077"),
    ("jackie-welles", "Cyberpunk 2077"),
    ("rogue-amsterdam", "Cyberpunk 2077"),
    ("riverside", "Cyberpunk 2077"),
    ("misty", "Cyberpunk 2077"),
    ("delamain", "Cyberpunk 2077"),
    ("brad-dourif", "Cyberpunk 2077"),
    ("brad dourif", "Cyberpunk 2077"),
    
    ("dbz", "Dragon Ball Z"),
    ("goku", "Dragon Ball Z"),
    ("vegeta", "Dragon Ball Z"),
    
    ("mortal-kombat", "Mortal Kombat"),
    ("sub-zero", "Mortal Kombat"),
    ("raiden", "Mortal Kombat"),
    ("scorpion", "Mortal Kombat"),
    ("liu-kang", "Mortal Kombat"),
    ("johnny-cage", "Mortal Kombat"),
    ("sonya-blade", "Mortal Kombat"),
    ("kitana", "Mortal Kombat"),
    ("mileena", "Mortal Kombat"),
    ("shang-tsung", "Mortal Kombat"),
    ("shao-khan", "Mortal Kombat"),
    ("noob-saibot", "Mortal Kombat"),
    
    ("elden-ring", "Elden Ring"),
    ("tarnished", "Elden Ring"),
    ("malenia", "Elden Ring"),
    ("radahn", "Elden Ring"),
    ("margit", "Elden Ring"),
    ("godrick", "Elden Ring"),
    ("ranni", "Elden Ring"),
    ("renna", "Elden Ring"),
    ("melina", "Elden Ring"),
    
    ("dark-souls", "Dark Souls"),
    ("artorias", "Dark Souls"),
    ("solaire", "Dark Souls"),
    ("ornstein", "Dark Souls"),
    ("gwynevere", "Dark Souls"),
    ("gwyndolin", "Dark Souls"),
    ("gwyn", "Dark Souls"),
    ("seath", "Dark Souls"),
    ("manus", "Dark Souls"),
    ("priscilla", "Dark Souls"),
    ("farron", "Dark Souls"),
    ("firelink", "Dark Souls"),
    
    ("fallout", "Fallout"),
    ("vault-tec", "Fallout"),
    ("nuka-cola", "Fallout"),
    ("power-armor", "Fallout"),
    
    ("curby", "Kirby"),
    ("kirby", "Kirby"),
    ("meta-knight", "Kirby"),
    ("king-dedede", "Kirby"),
    ("waddle-dee", "Kirby"),
    ("waddle-dos", "Kirby"),
    ("waddle-dash", "Kirby"),
    
    ("witcher", "The Witcher"),
    ("geralt", "The Witcher"),
    ("cirilla", "The Witcher"),
    ("ciri", "The Witcher"),
    ("yen", "The Witcher"),
    ("triss", "The Witcher"),
    ("wild-hunt", "The Witcher"),
    ("kaer-morhen", "The Witcher"),
    ("roach", "The Witcher"),
    ("silver-sword", "The Witcher"),

    ("like-a-dragon", "Yakuza"),
    ("like a dragon", "Yakuza"),
    ("like-a-dragon-7", "Yakuza"),
    ("like a dragon 7", "Yakuza"),
    ("like a dragon infinite wealth", "Yakuza"),
    ("like-a-dragon-infinite-wealth", "Yakuza"),
    ("yakuza", "Yakuza"),
    ("kazuma", "Yakuza"),
    ("kiryu", "Yakuza"),
    ("majima", "Yakuza"),
    ("ishin", "Yakuza"),
    ("ryu-ga-gotoku", "Yakuza"),
    ("ryu ga gotoku", "Yakuza"),
    ("ryu ga gotoku ishin", "Yakuza"),
    ("ryu-ga-gotoku ishin", "Yakuza"),
    ("ichi", "Yakuza"),
    ("ichiban", "Yakuza"),
    ("ichiban kasuga", "Yakuza"),
    
    ("halo", "Halo"),
    ("master-chief", "Halo"),
    
    ("destiny", "Destiny"),
    ("minecraft", "Minecraft"),
    ("hollow-knight", "Hollow Knight"),
    ("hollow knight", "Hollow Knight"),
    ("nier", "NieR:Automata"),
    ("2b", "NieR:Automata"),
    ("genshin", "Genshin Impact"),
    ("azur-lane", "Azur Lane"),
    ("street-fighter", "Street Fighter"),
    ("chun-li", "Street Fighter"),
    ("mega-man", "Mega Man"),
    ("borderlands", "Borderlands"),

    # ----- Mass Effect -----
    ("mass effect", "Mass Effect"),
    ("mass-effect", "Mass Effect"),
    ("n7", "Mass Effect"),
    ("normandy", "Mass Effect"),
    ("commander shepard", "Mass Effect"),
    ("garrus", "Mass Effect"),
    ("tali", "Mass Effect"),
    ("liara", "Mass Effect"),
    ("citadel", "Mass Effect"),
    ("reaper", "Mass Effect"),
    ("cerberus", "Mass Effect"),
    ("saren", "Mass Effect"),
    ("shepard", "Mass Effect"),
    ("mass effect 2", "Mass Effect"),
    ("mass effect 3", "Mass Effect"),

    # ----- Glitch Gear core catalog (Valve + popular indies) -----
    ("portal", "Portal"),
    ("aperture", "Portal"),
    ("glados", "Portal"),
    ("half-life", "Half-Life"),
    ("half life", "Half-Life"),
    ("gordon freeman", "Half-Life"),
    ("team fortress", "Team Fortress 2"),
    ("tf2", "Team Fortress 2"),
    ("counter-strike", "Counter-Strike"),
    ("counter strike", "Counter-Strike"),
    ("left 4 dead", "Left 4 Dead"),
    ("dota", "Dota 2"),
    ("undertale", "Undertale"),
    ("deltarune", "Deltarune"),
    ("celeste", "Celeste"),
    ("cuphead", "Cuphead"),
    ("shovel knight", "Shovel Knight"),
    ("stardew", "Stardew Valley"),
    ("stardew valley", "Stardew Valley"),
    ("hades", "Hades"),
    ("among us", "Among Us"),
    ("fall guys", "Fall Guys"),

    # Added 2026-07-04: these franchise names were completely absent from the
    # ruleset, so clean_franchise_tag() had zero chance of matching them and
    # Artsholic/Insert Coin products fell through to the naive leading-word
    # title tokenizer, which grabbed the character's own name (e.g. "Gabimaru")
    # instead of the real franchise mentioned later in the SEO-stuffed title
    # (e.g. "Gabimaru Shorts, Hell's Paradise Shorts, ..."). Adding the real
    # franchise name (and known character aliases) lets the keyword-mapping
    # step win before the tokenizer fallback ever runs.
    ("hell's paradise", "Hell's Paradise"),
    ("hells paradise", "Hell's Paradise"),
    ("gabimaru", "Hell's Paradise"),
    ("bleach", "Bleach"),
    ("ichigo kurosaki", "Bleach"),
    ("my hero academia", "My Hero Academia"),
    ("mha", "My Hero Academia"),
    ("katsuki bakugo", "My Hero Academia"),
    ("king of fighters", "King of Fighters"),
    ("kyo kusanagi", "King of Fighters"),
    ("mai shiranui", "King of Fighters"),
    ("demon slayer", "Demon Slayer"),
    ("mitsuri kanroji", "Demon Slayer"),
    ("darkstalkers", "Darkstalkers"),
    ("morrigan aensland", "Darkstalkers"),
    ("jujutsu kaisen", "Jujutsu Kaisen"),
    ("ryomen sukuna", "Jujutsu Kaisen"),
    ("sukuna", "Jujutsu Kaisen"),
    ("suguru geto", "Jujutsu Kaisen"),
    ("toji fushiguro", "Jujutsu Kaisen"),
    ("akira", "Akira"),
    ("tetsuo shima", "Akira"),

    # Added 2026-07-04: normalizing duplicate franchise name variants
    # (different casing/roman-numeral/edition-suffix spellings of the same
    # game were ending up as separate tags) into one canonical form each.
    ("slay the spire", "Slay the Spire"),
    ("helldivers 2", "Helldivers 2"),
    ("helldivers ii", "Helldivers 2"),
    ("oneshot", "OneShot"),
    ("the last of us", "The Last of Us"),
    ("overwatch", "Overwatch 2"),

    # Added 2026-07-04: one-off manual corrections for items with no
    # systemic fix available. "Dragon Ramen" (Artsholic) mentions no
    # franchise anywhere in its scraped text at all, so this is a manual
    # tag based on external knowledge it's a Dragon Ball reference - without
    # this keyword, a re-scrape would keep reverting to the naive
    # title-tokenizer's wrong guess. "Pennywise" (IT the movie/book) isn't a
    # game franchise; "IT" itself is far too short/dangerous to ever use as
    # a keyword, so it's redirected straight to the generic catch-all here
    # instead, which a bare DB update can't do since it gets overwritten by
    # every re-scrape without a keyword backing it.
    ("dragon ramen", "Dragon Ball"),
    ("pennywise", "Gamer Culture"),
]

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 0. Dynamic Franchise Mapping Rules Engine DB table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS franchise_mappings (
            keyword TEXT PRIMARY KEY,
            franchise_name TEXT NOT NULL
        )
    """)
    
    # Seed / top-up static ruleset (idempotent: adds any new default rules each run)
    cursor.executemany(
        "INSERT OR IGNORE INTO franchise_mappings (keyword, franchise_name) VALUES (?, ?)", 
        [(rule[0].lower().strip(), rule[1]) for rule in DEFAULT_RULESET]
    )
    
    # 1. Primary Relational Table with category and active states
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            store_url TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            current_price REAL NOT NULL,
            original_price REAL,
            image_url TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            franchise_tags TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            category TEXT NOT NULL DEFAULT 'other',
            description_snippet TEXT,
            franchise_verified INTEGER DEFAULT 1
        )
    """)

    # Migration: add description_snippet to any pre-existing products table
    # that was created before this column existed (CREATE TABLE IF NOT EXISTS
    # is a no-op on already-existing tables, so this ALTER is required for
    # upgrades). Feeds franchise_discovery.py's LLM-assisted classification
    # step with real product context instead of bare titles.
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(products)").fetchall()}
    if "description_snippet" not in existing_columns:
        cursor.execute("ALTER TABLE products ADD COLUMN description_snippet TEXT")

    # Migration: add franchise_verified to any pre-existing products table.
    # DEFAULT 1 is deliberate: existing rows are treated as already-verified
    # so they aren't all suddenly dumped into franchise_discovery.py's
    # Wikidata-verification queue at once (which is budget-limited per run).
    # Only rows produced going forward by the naive tokenizer/URL-slug
    # fallbacks get accurately marked 0, and are picked up gradually.
    if "franchise_verified" not in existing_columns:
        cursor.execute("ALTER TABLE products ADD COLUMN franchise_verified INTEGER DEFAULT 1")

    
    # 2. Relational Price History Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            store_url TEXT NOT NULL,
            price REAL NOT NULL,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_url) REFERENCES products(store_url) ON DELETE CASCADE
        )
    """)
    
    # Create FTS5 Virtual Table for Search including category
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
            store_url UNINDEXED,
            product_name,
            brand_name,
            franchise_tags,
            category,
            content='products',
            content_rowid='rowid'
        )
    """)
    
    # Sync Triggers to automate FTS synchronizations including category syncing
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS products_after_insert AFTER INSERT ON products BEGIN
            INSERT INTO products_fts(rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES (new.rowid, new.store_url, new.product_name, new.brand_name, new.franchise_tags, new.category);
        END;
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS products_after_delete AFTER DELETE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES('delete', old.rowid, old.store_url, old.product_name, old.brand_name, old.franchise_tags, old.category);
        END;
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS products_after_update AFTER UPDATE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES('delete', old.rowid, old.store_url, old.product_name, old.brand_name, old.franchise_tags, old.category);
            INSERT INTO products_fts(rowid, store_url, product_name, brand_name, franchise_tags, category)
            VALUES(new.rowid, new.store_url, new.product_name, new.brand_name, new.franchise_tags, new.category);
        END;
    """)
    
    # Performance indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON products(current_price);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_url ON price_history(store_url);")
    
    conn.commit()
    conn.close()
    print("Database structures, triggers, and price history indices initialized successfully.")

def save_products_to_db(products: list[GamingClothingItem]):
    """Inserts or updates scraped products, managing active in-stock statuses and price progression history."""
    conn = sqlite3.connect(DB_NAME)
    # Mandates cascade deletions on the price_history table
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    # 1. Before saving new runs, mark existing database products to inactive (is_active = 0)
    cursor.execute("UPDATE products SET is_active = 0")
    conn.commit()
    
    # 2. Insert or update parsed elements, reactivating active products (is_active = 1)
    for product in products:
        # Check if product exists and if the price has shifted
        cursor.execute("SELECT current_price FROM products WHERE store_url = ?", (str(product.store_url),))
        row = cursor.fetchone()
        
        has_changed = False
        if row is None:
            # Brand-new product
            has_changed = True
        elif float(row[0]) != float(product.current_price):
            # Price movement!
            has_changed = True
            
        cursor.execute("""
            INSERT INTO products (
                store_url, product_name, current_price, original_price, image_url, brand_name, franchise_tags, is_active, category, description_snippet, franchise_verified, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(store_url) DO UPDATE SET
                product_name=excluded.product_name,
                current_price=excluded.current_price,
                original_price=excluded.original_price,
                image_url=excluded.image_url,
                brand_name=excluded.brand_name,
                franchise_tags=excluded.franchise_tags,
                category=excluded.category,
                description_snippet=excluded.description_snippet,
                franchise_verified=excluded.franchise_verified,
                is_active=1,
                updated_at=CURRENT_TIMESTAMP
        """, (
            str(product.store_url),
            product.product_name,
            product.current_price,
            product.original_price,
            str(product.image_url),
            product.brand_name,
            json.dumps(product.franchise_tags, ensure_ascii=False),
            product.category,
            product.description_snippet,
            1 if product.franchise_verified else 0
        ))
        
        # Log a price point into price progression history on changes
        if has_changed:
            cursor.execute("""
                INSERT INTO price_history (store_url, price)
                VALUES (?, ?)
            """, (str(product.store_url), product.current_price))
        
    conn.commit()
    
    # 3. Clean Sweep Cleanup:
    # Delete inactive products (Cascade deletes will automatically drop their tracking logs from price_history)
    cursor.execute("DELETE FROM products WHERE is_active = 0")
    deleted_count = cursor.rowcount
    conn.commit()
    
    conn.close()
    print(f"Successfully processed {len(products)} active products.")
    if deleted_count > 0:
        print(f"Clean Sweep: Purged {deleted_count} out-of-stock items no longer seen on storefronts.")