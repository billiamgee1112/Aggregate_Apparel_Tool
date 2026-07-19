# -*- coding: utf-8 -*-
"""Seeds/updates curated franchise intro write-ups (franchise_content table)
used on /franchises/{slug} landing pages for SEO content.

Idempotent (INSERT OR REPLACE) - safe to re-run any time to update wording
or add new franchises. Currently covers the 18 "popular" franchises (the
top-18-by-product-count list used for the sidebar) plus Games Done Quick,
which is included regardless of catalog size since it's a charity event
rather than a game; more franchises will be added here over time.

Usage (from project root):
    python seed_franchise_content.py
"""
import sqlite3
import database

database.init_db()  # ensure franchise_content table exists

conn = sqlite3.connect("apparel_aggregator.db")
cur = conn.cursor()

# Deliberately avoids "official"/"licensed" framing (not every item in the
# catalog is officially licensed - some sources are independent fan-art
# printers) and avoids em dashes (an easy AI-generated-content tell that a
# lot of readers have negative associations with).
drafts = [
    ("Final Fantasy",
     "Final Fantasy has been one of the most influential RPG franchises in gaming since 1987, "
     "and its apparel lineup reflects three decades of iconic imagery, from Cloud Strife's "
     "Buster Sword to the moogles, chocobos, and crystal motifs fans instantly recognize. Our "
     "catalog pulls Final Fantasy tees, hoodies, and outerwear from Square Enix's own storefront "
     "alongside independent fan-art printers, so you'll find everything from minimalist logo "
     "tees to detailed character graphics for Final Fantasy VII, X, XIV, and beyond. Whether "
     "you're looking for a subtle piece to wear day-to-day or a statement hoodie for your next "
     "gaming meetup, this is a good starting point to compare styles and prices across sources "
     "in one place."),

    ("The Legend of Zelda",
     "The Legend of Zelda has anchored Nintendo's lineup since 1986, and its apparel reflects "
     "that history, from Hyrule's crest and the Triforce to specific callouts for Breath of "
     "the Wild, Tears of the Kingdom, Ocarina of Time, and Majora's Mask. This collection gathers "
     "Zelda tees, hoodies, and accessories from Nintendo's own storefront and independent "
     "fan-focused printers, covering both minimalist symbol designs and detailed artwork pieces. "
     "If you're shopping for a specific game era (classic 2D Zelda vs. the newer open-world "
     "titles) or just want a reliable comparison of what's currently in stock, this page pulls "
     "it all together."),

    ("Super Mario",
     "Super Mario is Nintendo's flagship franchise and one of the most recognizable brands in "
     "gaming, and the apparel reflects that reach, from classic red-cap logo tees to pieces "
     "referencing Mario Kart, Mario Party, and the wider Mushroom Kingdom cast (Luigi, Peach, "
     "Bowser, Yoshi). This collection brings together Mario clothing from Nintendo's own "
     "storefront and independent gaming apparel printers, so you can compare casual everyday "
     "pieces against more detailed, character-specific designs in one place before deciding what "
     "fits your style or who you're shopping for."),

    ("World of Warcraft",
     "World of Warcraft has run since 2004 and built one of gaming's most detailed apparel "
     "catalogs as a result: faction gear (Horde vs. Alliance), class-specific designs, and "
     "references to major expansions and raid content. This collection pulls WoW hoodies, tees, "
     "and outerwear primarily from Blizzard's own storefront. If you're a long-time player looking "
     "for something that nods to a specific expansion or class, or just want faction-pride basics, "
     "this is a convenient way to browse what's currently available."),

    ("Fallout",
     "Fallout's retro-futuristic post-apocalyptic aesthetic (Vault Boy, Pip-Boy interfaces, and "
     "Vault-Tec branding) has become one of gaming's most distinctive visual identities, "
     "especially after the Amazon TV adaptation brought the series to a wider audience. This "
     "collection gathers Fallout apparel from Bethesda's own storefront alongside "
     "fan-focused printers, spanning minimalist Vault-Tec logo tees to more detailed graphics "
     "referencing specific games (Fallout 3, New Vegas, Fallout 4, Fallout 76). Browse here to "
     "compare styles and prices before picking up a piece for your wardrobe or your next watch "
     "party."),

    ("Sonic the Hedgehog",
     "Sonic the Hedgehog has been SEGA's flagship mascot since 1991, and the apparel reflects "
     "the character's whole cast, from Sonic, Tails, and Knuckles to newer favorites introduced "
     "in later games and movies. This collection pulls Sonic tees, hoodies, and outerwear from "
     "SEGA's own storefront alongside independent fan-art printers, covering both classic "
     "pixel-art callbacks and modern character designs. Whether you want something nostalgic or "
     "a piece tied to a more recent release, this page brings the options together in one "
     "place."),

    ("Diablo",
     "Diablo has defined dark fantasy action RPGs since 1996, and its apparel leans into that "
     "tone: class sigils for Barbarian, Sorcerer, Rogue, and more, along with recurring imagery "
     "like Lilith and the Butcher. This collection pulls Diablo hoodies, tees, and outerwear "
     "primarily from Blizzard's own storefront, with a few crossover collaboration pieces mixed "
     "in as well. If you're looking for something that nods to a specific class or just want the "
     "franchise's signature dark aesthetic, this is a convenient way to browse what's currently "
     "available."),

    ("Genshin Impact",
     "Genshin Impact has grown into one of the most popular live-service RPGs since its 2020 "
     "launch, and its apparel reflects the game's wide cast of characters and elemental themes. "
     "This collection gathers Genshin tees, hoodies, and accessories from independent fan-art "
     "printers, spanning character-specific designs, elemental symbol motifs, and more general "
     "franchise pieces. Since the game's roster keeps growing with each update, this collection "
     "tends to grow along with it, so it's worth checking back on from time to time."),

    ("Overwatch 2",
     "Overwatch 2 carries forward Blizzard's team-based hero shooter after its 2022 relaunch, "
     "and the apparel reflects the game's large roster, from hero-specific tees and hoodies to "
     "more general franchise branding. This collection pulls Overwatch gear primarily from "
     "Blizzard's own storefront, covering both classic heroes from the original game and newer "
     "additions. If you're looking for a piece tied to a specific hero you main, or just want "
     "general Overwatch branding, this page brings the current selection together."),

    ("Cyberpunk 2077",
     "Cyberpunk 2077 has become known for its Night City setting and neon-soaked, near-future "
     "aesthetic since its 2020 release, and the apparel follows that same visual identity: "
     "corporate logos, street gang branding, and glitch-style graphics inspired by the game's "
     "world. This collection pulls Cyberpunk apparel from CD Projekt Red's own storefront, "
     "spanning hoodies, jackets, and tees built around that look. It's a solid pick if you want "
     "gaming merch that doesn't read as an obvious logo tee."),

    ("Street Fighter",
     "Street Fighter has been one of the defining names in fighting games since 1987, and its "
     "apparel draws on decades of character history: Ryu, Chun-Li, Ken, and the rest of the "
     "roster, along with classic arcade-era branding and logos. This collection pulls Street "
     "Fighter tees, hoodies, and outerwear from Capcom's own storefront alongside independent "
     "fan-art printers, covering both retro pixel-art callbacks and newer character art. Whether "
     "you're looking for a piece tied to a specific fighter or just want the classic logo, this "
     "page brings the current selection together in one place."),

    ("League of Legends",
     "League of Legends has anchored competitive gaming since 2009, and its apparel reflects "
     "both the game's massive champion roster and its esports scene. This collection gathers "
     "League tees, hoodies, and accessories primarily from Riot Games' own storefront, spanning "
     "champion-specific designs, region-themed pieces (Piltover, Noxus, and others), and general "
     "franchise branding. If you're looking for something tied to a champion you play, or just "
     "want to represent the game more broadly, this is a convenient way to browse what's "
     "available."),

    ("Mortal Kombat",
     "Mortal Kombat has built its identity around brutal fighting game action since 1992, and "
     "the apparel leans into that same tone: Scorpion and Sub-Zero iconography, the series' "
     "dragon emblem, and other callbacks to its fatality-driven reputation. This collection "
     "pulls Mortal Kombat tees, hoodies, and outerwear from a mix of storefronts and independent "
     "fan-art printers, covering both classic character designs and newer entries in the "
     "franchise. It's a good spot to check if you want something with a harder-edged, "
     "horror-adjacent look."),

    ("NieR:Automata",
     "NieR:Automata built a dedicated following after its 2017 release, known for its android "
     "cast (2B, 9S, A2) and a visual style that blends minimalist military design with "
     "melancholy sci-fi themes. This collection gathers NieR apparel from Square Enix's own "
     "storefront alongside independent fan-art printers, spanning character-specific tees and "
     "hoodies to more understated pieces built around the game's symbols and typography. It's a "
     "solid pick for fans looking for something a bit more niche than the mainstream franchises "
     "on this list."),

    ("Hollow Knight",
     "Hollow Knight has become one of the most beloved indie games since its 2017 release, "
     "known for its hand-drawn insect kingdom and moody, atmospheric art style. This collection "
     "gathers Hollow Knight tees, hoodies, and accessories primarily from independent fan-art "
     "printers, since Team Cherry doesn't run a large merch storefront of its own. Expect "
     "minimalist, ink-style character art and symbols pulled straight from the game's aesthetic, "
     "good for fans who want something understated rather than a bold, in-your-face graphic."),

    ("Mass Effect",
     "Mass Effect has been one of BioWare's signature sci-fi RPG series since 2007, and its "
     "apparel centers on a few instantly recognizable symbols: the N7 logo, the Normandy "
     "starship, and faction or species-specific designs from across the trilogy. This "
     "collection pulls Mass Effect tees, hoodies, and outerwear primarily from BioWare's own "
     "storefront, so you'll mostly find pieces built around those established franchise symbols "
     "rather than more obscure references. It's a straightforward pick if you want something "
     "that reads clearly as Mass Effect merch."),

    ("Halo",
     "Halo has been one of Xbox's defining franchises since 2001, and its apparel draws on that "
     "history: Master Chief and Spartan armor, UNSC and Covenant branding, and callbacks to "
     "specific games in the series. This collection pulls Halo tees, hoodies, and outerwear "
     "primarily from Xbox's own storefront, covering both classic series imagery and newer "
     "entries. Whether you want something built around Master Chief specifically or more "
     "general franchise branding, this page brings the current selection together."),

    ("God of War",
     "God of War has spanned both Greek and Norse mythology settings since 2005, and its "
     "apparel reflects that range, from Kratos and the Leviathan Axe to symbols tied to the more "
     "recent Norse-era games. This collection pulls God of War tees, hoodies, and outerwear "
     "from a mix of storefronts and independent fan-art printers, covering imagery from across "
     "the series rather than just the newest release. It's a good pick if you want something "
     "with a darker, mythology-driven look."),

    ("Games Done Quick",
     "Games Done Quick (GDQ) is a bi-annual, week-long twenty-four hour speedrunning marathon that "
     "brings together elite gamers from around the globe to finish video games as fast as humanly possible. "
     "By utilizing frame-perfect mechanical inputs, software glitches, and deep routing strategies, players showcase "
     "everything from retro arcade classics to modern masterpieces. Beyond world-record-setting gameplay, GDQ is an absolute charitable powerhouse. "
     "Since its inception in 2010, the organization has raised over 60 million dollars for globally recognized non-profits. Its flagship winter and "
     "summer events directly benefit life-saving organizations including the Prevent Cancer Foundation and Doctors Without Borders."),

    ("Contra",
     "Contra is a classic run-and-gun video game series that has been popular since the 1980s. "
     "The apparel often features iconic imagery from the games, such as the Konami code, the main characters, and retro 8-bit graphics. "
     "This collection gathers Contra apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("Crash Bandicoot",
     "Crash Bandicoot is a platforming video game series that has been popular since the 1990s. "
     "The apparel often features the titular character, his friends, and iconic elements from the games. "
     "This collection gathers Crash Bandicoot apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

     ("Yakuza",
      "Yakuza is an action-adventure video game series that has been popular since the mid-2000s. "
      "The apparel often features characters, symbols, and iconic elements from the games. "
      "This collection gathers Yakuza apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("Dark Souls",
     "Dark Souls is an action role-playing video game series known for its challenging gameplay and dark fantasy setting. "
     "The apparel often features iconic imagery from the games, such as the bonfire, the Estus Flask, and various character designs. "
     "This collection gathers Dark Souls apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("The Witcher",
     "The Witcher is an action role-playing video game series based on the book series by Andrzej Sapkowski. "
     "The apparel often features characters, symbols, and iconic elements from the games, such as Geralt, the Wolf School emblem, and various monsters. "
     "This collection gathers The Witcher apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),
# Update for 7/24
    ("Halo",
     "Halo is a first-person shooter video game series that has been popular since the early 2000s. "
     "The apparel often features characters, symbols, and iconic elements from the games, such as Master Chief, the UNSC emblem, and various alien species. "
     "This collection gathers Halo apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("Metroid",
     "Metroid is a science fiction action-adventure video game series that has been popular since the 1980s. "
     "The apparel often features characters, symbols, and iconic elements from the games, such as Samus Aran, the Chozo emblem, and various alien species. "
     "This collection gathers Metroid apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("God of War",
     "God of War is an action-adventure video game series that has been popular since the mid-2000s. "
     "The apparel often features characters, symbols, and iconic elements from the games, such as Kratos, the Leviathan Axe, and various mythological creatures. "
     "This collection gathers God of War apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("DOOM",
     "DOOM is a first-person shooter video game series that has been popular since the 1990s. "
     "The apparel often features characters, symbols, and iconic elements from the games, such as the Doom Slayer, demons, and various weapons. "
     "This collection gathers DOOM apparel from a mix of official and fan-made sources, perfect for fans of the franchise."),

    ("Resident Evil",
     "Resident Evil is a survival horror video game series that has been popular since the 1990s. "
     "The apparel often features characters, symbols, and iconic elements from the games, such as Leon S. Kennedy, Jill Valentine, and various zombies. "
     "This collection gathers Resident Evil apparel from a mix of official and fan-made sources, perfect for fans of the franchise.")
]

for name, text in drafts:
    cur.execute(
        "INSERT OR REPLACE INTO franchise_content (franchise_name, intro_text, updated_at) "
        "VALUES (?, ?, CURRENT_TIMESTAMP)",
        (name, text)
    )

conn.commit()
print(f"Inserted/updated {len(drafts)} franchise intro(s).")
conn.close()
