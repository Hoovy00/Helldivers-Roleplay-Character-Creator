"""Build data/item-stats.js from the Helldivers Wiki.

The character builder cannot read the wiki from the browser (the wiki blocks
cross-site requests), so item stats are bundled with the app instead. Run this
script whenever the game adds or rebalances gear:

    py tools/build_item_stats.py

It reads the gear catalogs from index.html, looks each item up on
helldivers.wiki.gg, and rewrites data/item-stats.js. The stratagem list is
taken from the wiki itself (Offensive, Supply and Defensive permits only), so
new stratagems appear in the app after a re-run without editing index.html.

A full run also rebuilds data/enemy-stats.js and data/attachments.js. To refresh just one of those:

    py tools/build_item_stats.py --enemies
    py tools/build_item_stats.py --attachments Entries listed in
data/item-overrides.js are left to the GM and merged on top by the app, so
house-rule edits belong there rather than in the generated file.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://helldivers.wiki.gg/api.php"
USER_AGENT = "FieldRecordBuilder/1.0 (personal Helldivers roleplay character sheet)"

PEN_NAMES = {1: "Unarmored", 2: "Light", 3: "Medium", 4: "Heavy"}

# Catalog names that don't lead straight to the right wiki article.
WIKI_TITLES = {
    "AR-61 Tenderiser": "AR-61 Tenderizer",
    "Guard Dog": "AX/AR-23 Guard Dog",
}


def api(params):
    query = urllib.parse.urlencode({**params, "format": "json"})
    request = urllib.request.Request(API + "?" + query, headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception as error:
            if attempt == 4:
                raise
            # The wiki rate-limits bursts (HTTP 429); back off much longer for those.
            time.sleep((15 if getattr(error, "code", None) == 429 else 2) * (attempt + 1))


# ---------------------------------------------------------------- wikitext ---

def split_top(text, sep="|"):
    """Split on sep, ignoring separators nested inside {{ }} or [[ ]]."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in ("{{", "[["):
            depth += 1
            i += 2
            continue
        if pair in ("}}", "]]"):
            depth = max(0, depth - 1)
            i += 2
            continue
        if text[i] == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def find_template(text, name_pattern):
    """Return the inner text of the first {{Name ...}} whose name matches."""
    for match in re.finditer(r"\{\{\s*(" + name_pattern + r")\s*(?=[|}\n])", text, re.I):
        depth, i = 0, match.start()
        while i < len(text):
            if text.startswith("{{", i):
                depth += 1
                i += 2
            elif text.startswith("}}", i):
                depth -= 1
                i += 2
                if depth == 0:
                    return text[match.start() + 2:i - 2]
            else:
                i += 1
    return None


def template_fields(inner):
    fields = {}
    for part in split_top(inner)[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip().lower()] = value.strip()
    return fields


def penetration_label(level):
    level = int(level)
    name = PEN_NAMES.get(level) or f"Anti-Tank {level - 4}"
    return f"{name} (AP {level})"


def render_template(inner, title):
    parts = [p.strip() for p in split_top(inner)]
    name = parts[0].strip().lower().replace("_", " ")
    args = [render(p, title) for p in parts[1:]]
    positional = [a for a, raw in zip(args, parts[1:]) if "=" not in raw]
    if name == "*":
        return " · "
    if name == "!":
        return "|"
    if name == "pagename":
        return title
    if name == "damage" and len(positional) >= 2:
        kind, value = positional[0], positional[1]
        return value if kind.lower() in value.lower() else f"{value} {kind}"
    if name == "armor" and positional and positional[0].isdigit():
        return penetration_label(positional[0])
    if name == "currency" and len(positional) >= 2:
        return f"{positional[1]} {positional[0]}"
    if name in ("tooltip", "abbr") and positional:
        return positional[0]
    if name == "difficulty" and positional:
        return f"Difficulty {positional[0]}"
    if name in ("stratagem code", "stratagem_code"):
        arrows = {"up": "↑", "down": "↓", "left": "←", "right": "→"}
        return " ".join(arrows.get(a.lower(), a) for a in positional)
    if name in ("status", "effect", "icon", "item") and positional:
        return positional[-1] if len(positional) > 1 and not positional[-1].isdigit() else positional[0]
    return ""


def render(text, title=""):
    """Turn a wikitext fragment into plain text."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    # Expand templates from the innermost outward.
    for _ in range(20):
        new = re.sub(r"\{\{([^{}]*)\}\}", lambda m: render_template(m.group(1), title), text)
        if new == text:
            break
        text = new
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", text)
    text = re.sub(r"<\s*(br|hr)\s*/?>", " / ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = html.unescape(text)
    text = re.sub(r"\s*/\s*(/\s*)+", " / ", text)
    text = re.sub(r"\s*/\s*·\s*", " · ", text)  # "{{*}} Auto<br>{{*}} Semi" lists
    text = re.sub(r"(\s*·\s*)+", " · ", text)
    text = re.sub(r"\s+", " ", text).strip(" /·")
    return text


# ------------------------------------------------------------- extraction ---

WEAPON_FIELDS = [
    ("damage", "Damage"), ("penetration", "Penetration"), ("capacity", "Capacity"),
    ("spare_mags", "Spare Mags"), ("spare_rounds", "Spare Rounds"), ("fire_rate", "Fire Rate"),
    ("reload_time", "Reload Time"), ("firing_modes", "Firing Modes"), ("weapon_type", "Weapon Type"),
    ("weapon_traits", "Traits"),
]
THROWABLE_FIELDS = [
    ("damage", "Damage"), ("penetration", "Penetration"), ("radius", "Radius"), ("fuse", "Fuse"),
    ("capacity", "Capacity"), ("weapon_type", "Type"), ("throwable_traits", "Traits"),
]
STRATAGEM_FIELDS = [
    ("stratagem_type", "Type"), ("traits", "Traits"), ("base_cooldown", "Cooldown"),
    ("stratagem_code", "Code"),
] + [f for f in WEAPON_FIELDS if f[0] not in ("weapon_traits",)]
STRATAGEM_TABLE_FIELDS = [("call_time", "Call-in Time", "s"), ("uses", "Uses", ""), ("rearm_time", "Rearm Time", "s")]

# Most pages use {{Infobox Weapon}} etc., but some use the bare {{Weapon}} form.
# Booster pages keep their real numbers in prose (mixed with video citations and
# strategy notes), so they are summarized here by hand from each wiki article.
# Re-check these against the wiki when a booster is rebalanced. Last checked 2026-10-20.
BOOSTER_EFFECTS = {
    "Armed Resupply Pods": {
        "Turret": "Every Resupply pod mounts an automatic AR-23P Liberator Penetrator",
        "Range": "Fires at enemies within 30 m",
        "Ammo": "140 rounds · 640 rpm",
        "Damage": "65 Ballistic (15 vs. durable)",
        "Penetration": "Medium (AP 3)",
    },
    "Concealed Insertion": {
        "Effect": "Every Hellpod, manned or not, releases a burst of smoke on impact",
        "In the smoke": "Enemies can only spot you within 10 m",
    },
    "Dead Sprint": {
        "Effect": "Keep sprinting at 0 stamina by burning health instead",
        "Health drain": "About 3.6% health per second, for up to 25 s",
        "Safety limit": "Stops at 5% health; cannot kill you",
        "With Vitality Enhancement": "Drain drops to about 1% per second (about 142 s of sprinting)",
    },
    "Experimental Infusion": {
        "While a stim is active": "+10% movement speed and −10% damage taken",
        "Drawback": "+25% aim sway (trembling)",
    },
    "Expert Extraction Pilot": {
        "Extraction arrival": "30% faster (2:00 → 1:24)",
    },
    "Firebomb Hellpods": {
        "Effect": "Every Hellpod bursts into fire on impact; hurts allies too",
        "Damage": "200 Fire within 2 m, falling to 0 at 4 m",
        "Penetration": "Anti-Tank 6",
        "Status": "Sets targets on fire",
    },
    "Flexible Reinforcement Budget": {
        "Reinforcement cooldown": "25% shorter once the budget runs out (2:00 → 1:30)",
    },
    "Hellpod Space Optimization": {
        "Effect": "Deploy and reinforce fully stocked: maximum ammo, grenades and stims",
    },
    "Increased Reinforcement Budget": {
        "Reinforcements": "+1 per Helldiver in the squad (solo: 5 → 6)",
    },
    "Integrated Extinguishers": {
        "Burning": "Fire on you goes out by itself after 1.5 s instead of 3 s, no dive needed",
    },
    "Localization Confusion": {
        "Enemy reinforcements": "About 15% longer cooldown between bug breaches, bot drops and Illuminate ships",
        "Example": "Difficulty 9 solo: about 2:30 → 2:52",
        "No effect on": "Patrols, or the size and arrival time of a reinforcement once called",
    },
    "Motivational Shocks": {
        "Stuns": "Most stuns last half as long (G-23 Stun and Stun Baton about 2.5 s shorter)",
        "Slows": "Tremor and Ice Plant slows last 25% less (10 s → 7.5 s)",
        "No effect on": "Orbital EMS clouds or the acid slow",
    },
    "Muscle Enhancement": {
        "Less slowdown in": "Sandstorms, blizzards, water, snow, mud, foliage, barbed wire, and Terminid acid",
        "No effect on": "Plain sand, slopes, vaulting/climbing, or tremors",
        # The wiki has no base value; patch 1.002.001 only says the bonus was "increased by 40%".
        # The GM rules it as a flat 40% (2026-10-20).
        "Amount": "Terrain slowdown reduced by 40% (table ruling; patch 1.002.001 raised the bonus by 40%, base value unpublished)",
    },
    "Sample Extricator": {
        "Effect": "Large enemies can drop Common samples when killed",
        "Cap": "Up to 10 extra samples per mission",
    },
    "Sample Scanner": {
        "Effect": "15% chance to get double samples on pickup (all rarities)",
    },
    "Stamina Enhancement": {
        "Max stamina": "+22.5%",
        "Stamina regen": "+40%",
    },
    "Stun Pods": {
        "Effect": "Every Hellpod releases an electric burst on impact; hits allies too",
        "Damage": "50 Arc within 2 m, falling to 0 at 4 m",
        "Status": "Massive stun, about 10 s (the longest in the game)",
    },
    "Surplus EAT Allocation": {
        "Effect": "Adds a free EAT-17 Expendable Anti-Tank stratagem",
        "Uses": "2 calls per mission, 2 launchers per pod; cannot be rearmed",
    },
    "UAV Recon Booster": {
        "Radar range": "About +50%",
        "No effect": "On missions with the Atmospheric Spores modifier",
    },
    "Vitality Enhancement": {
        "Damage taken": "−10% from all sources",
        "Injuries": "Lower chance of limb injury",
    },
}

# Loadout slots only take stratagems a Helldiver can bring from these permits.
PERMITS = {"offens": "Offensive", "suppl": "Supply", "defens": "Defensive"}
MISSION_TYPES = {"objective", "ship", "other"}

INFOBOX = r"(?:Infobox[ _][A-Za-z ]+?|Weapon|Armor|Stratagem|Throwable|Booster|Support[ _]Weapon)"


def clean_value(value, title):
    value = render(value, title)
    if not value or value.lower() in ("n/a", "-", "—", "none", "?"):
        return ""
    return value


def armory_description(wikitext, title):
    quote = find_template(wikitext, r"Quote")
    if quote:
        parts = split_top(quote)
        if len(parts) > 1:
            return render(parts[1], title)
    return ""


def extract(kind, title, wikitext):
    box_inner = find_template(wikitext, INFOBOX)
    if not box_inner:
        return None
    box_name = split_top(box_inner)[0].strip().lower()
    fields = template_fields(box_inner)
    stats, extra = {}, {}

    def add(label, raw):
        value = clean_value(raw or "", title)
        if value and label not in stats:
            stats[label] = value

    if kind == "armor":
        if "armor" not in box_name:
            return None
        armor_type = clean_value(fields.get("type", ""), title)
        add("Armor Type", armor_type + " Armor" if armor_type and "armor" not in armor_type.lower() else armor_type)
        add("Armor", fields.get("armor"))
        add("Speed", fields.get("speed"))
        add("Stamina", fields.get("stam_regen") or fields.get("stamina"))
        add("Passive", fields.get("passive"))
    elif kind == "boosters":
        description = clean_value(fields.get("description", ""), title)
        effects = BOOSTER_EFFECTS.get(title)
        if effects is None:
            print(f"  ! {title}: no summarized effects yet; add it to BOOSTER_EFFECTS", file=sys.stderr)
        return {"page": title, "stats": dict(effects or {}), "description": description}
    elif kind == "throwable":
        for key, label in THROWABLE_FIELDS:
            add(label, fields.get(key))
    elif kind == "stratagems":
        permit = clean_value(fields.get("permit_type", ""), title).lower()
        extra["permit"] = next((name for prefix, name in PERMITS.items() if permit.startswith(prefix)), "")
        extra["stratagemType"] = clean_value(fields.get("stratagem_type", ""), title)
        for key, label in STRATAGEM_FIELDS:
            add(label, fields.get(key))
        table = find_template(wikitext, r"Stratagem[ _]Stats[ _]Table")
        if table:
            table_fields = template_fields(table)
            for key, label, unit in STRATAGEM_TABLE_FIELDS:
                value = clean_value(table_fields.get(key, ""), title)
                if value:
                    stats.setdefault(label, value + unit if unit and re.fullmatch(r"[\d.]+", value) else value)
            if table_fields.get("cooldown") and "Cooldown" not in stats:
                stats["Cooldown"] = clean_value(table_fields["cooldown"], title) + "s"
            # The wiki also lists fully upgraded values (all Super Destroyer ship modules).
            upgraded = {}
            for key, out_key in (("cooldown_upgraded", "cooldown"), ("call_time_upgraded", "callIn"), ("uses_upgraded", "uses"), ("rearm_time_upgraded", "rearm")):
                value = clean_value(table_fields.get(key, ""), title)
                number = re.match(r"\d+(?:\.\d+)?", value or "")
                if number:
                    upgraded[out_key] = float(number.group()) if "." in number.group() else int(number.group())
            if upgraded:
                extra["upgraded"] = upgraded
    else:
        for key, label in WEAPON_FIELDS:
            add(label, fields.get(key))

    return {"page": title, "stats": stats, "description": armory_description(wikitext, title), **extra}


# ------------------------------------------------------------ attack data ---
# Each weapon page renders a "Detailed Weapon Statistics" block from the wiki's
# attack-data module: one table per attack (projectile, explosion, status, arc…)
# plus an "Attacks" list on the weapon table that says how they nest. The first
# top-level attack is the weapon's base shot; everything else is an extra effect.

ATTACK_KINDS = ("primary", "secondary", "melee", "throwable", "stratagems")
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}


def cell_text(fragment):
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
    # Game data has float noise such as "3.29999995 m"; show at most two decimals.
    return re.sub(r"\d+\.\d{3,}", lambda m: f"{float(m.group()):.2f}".rstrip("0").rstrip("."), text)


def attack_key(name):
    return re.sub(r"[\s_]+", " ", name).strip().lower()


def pen_text(value):
    return re.sub(r"\bAnti-Tank (VI|IV|V|I{1,3})\b", lambda m: f"Anti-Tank {ROMAN[m.group(1)]}", value)


AMMO_LABELS = {
    "capacity": "capacity", "spare magazines": "spareMags", "spare rounds": "spareRounds",
    "starting magazines": "startMags", "starting rounds": "startRounds",
    "mags from supply": "supplyMags", "rounds from supply": "supplyRounds",
    "mags from ammo box": "boxMags", "rounds from ammo box": "boxRounds",
    "max rounds": "maxRounds", "throwables from supply": "supplyThrowables", "fire rate": "fireRate",
}


def ammo_numbers(rows):
    """Ammo counts from the weapon table (first value wins; non-numeric values such as ∞ are skipped)."""
    ammo = {}
    for label, value in rows:
        key = AMMO_LABELS.get(label.lower())
        number = re.search(r"\d[\d,]*(?:\.\d+)?", value or "")
        if key and key not in ammo and number and "∞" not in value:
            ammo[key] = float(number.group().replace(",", ""))
            if ammo[key].is_integer():
                ammo[key] = int(ammo[key])
    return ammo


def parse_attack_tables(markup):
    """Return (attack list [(depth, name, type)], {key: (type, title, [(section, label, value)])}, weapon rows)."""
    attack_list, tables, weapon_rows = [], {}, []
    for kind, body in re.findall(r'<table class="[^"]*attack-data-table-(\w+)"[^>]*>(.*?)</table>', markup, re.S):
        title, section, rows = "", "", []
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            cells = re.findall(r"<t([hd])[^>]*>(.*?)</t[hd]>", row, re.S)
            if not cells:
                continue
            if cells[0][0] == "h":
                title = title or cell_text(cells[0][1])
                section = cell_text(cells[0][1])
                continue
            label = cell_text(cells[0][1])
            value = cell_text(cells[1][1]) if len(cells) > 1 else ""
            # Weapon pages mark attacks with * nesting; stratagem pages list them unmarked under "Attacks".
            if kind == "weapon" and (label.startswith("*") or section.lower() == "attacks"):
                depth = max(1, len(label) - len(label.lstrip("*")))
                attack_list.append((depth, label.lstrip("* ").strip(), value.lower()))
            elif kind == "weapon":
                weapon_rows.append((label, value))
            else:
                rows.append((section, label, value))
        if kind != "weapon" and title:
            tables.setdefault(attack_key(title), (kind, title, rows))
    return attack_list, tables, weapon_rows


def summarize_attack(rows):
    """Keep the numbers that matter at the table; drop physics and force values."""
    stats, area, pen, damage = {}, {}, {}, {}

    def put(label, value):
        if value and label not in stats:
            stats[label] = value

    for section, label, value in rows:
        sec, low = section.lower(), label.lower()
        if low in ("pellets", "barrels"):
            put("Pellets", value.replace("x ", "×"))
        elif sec == "area of effect" and low in ("inner radius", "outer radius"):
            area[low] = value
        elif low == "aoe duration":
            put("Lingers", value)
        elif low == "shrapnel count":
            put("Shrapnel", "×" + value)
        elif sec == "damage" and low in ("standard", "inner radius"):
            damage["main"] = value
        elif sec == "damage" and low in ("vs. durable", "inner durable"):
            damage["durable"] = value
        elif sec == "penetration" and low in ("direct", "inner ap"):
            pen["main"] = pen_text(value)
        elif sec == "penetration" and low == "outer ap":
            pen["outer"] = pen_text(value)
        elif low == "status":
            put("Status", status_name(value))
        elif low == "second status":
            put("Second status", status_name(value))
        elif low == "status duration":
            put("Duration", value)
        elif low.endswith("range") and "radius" not in low:
            put("Range", value)
        elif low == "chain count":
            put("Chains", value)

    if area:
        inner, outer = area.get("inner radius", ""), area.get("outer radius", "")
        put("Blast radius", f"{inner} full damage, fading out to {outer}" if inner and outer else inner or outer)
    if damage.get("main") and not re.match(r"0(\s|$)", damage["main"]):
        stats = {"Damage": damage["main"], **stats}
        if damage.get("durable") and damage["durable"] != damage["main"]:
            stats["vs. Durable"] = damage["durable"]
        if pen.get("main"):
            stats["Penetration"] = pen["main"] + (f" (inner) / {pen['outer']} (outer)" if pen.get("outer") and pen["outer"] != pen["main"] else "")
    return stats


TYPE_TITLES = {"explosion": "Explosion", "status": "Status", "arc": "Arc", "beam": "Beam",
               "projectile": "Projectile", "damage": "Melee strike", "spray": "Spray"}


def attack_effects(title, wikitext):
    """Return (extra effects, ammo numbers from the weapon table)."""
    calls = re.findall(r"\{\{\s*Attack[ _]Data[^{}]*\}\}", wikitext)
    if not calls:
        return [], {}
    attack_list, tables, weapon_rows = [], {}, []
    for call in calls:
        rendered = api({"action": "parse", "prop": "text", "contentmodel": "wikitext", "text": call, "title": title})
        found_list, found_tables, found_rows = parse_attack_tables(rendered.get("parse", {}).get("text", {}).get("*", ""))
        attack_list += found_list
        weapon_rows += found_rows
        for key, value in found_tables.items():
            tables.setdefault(key, value)
    ammo = ammo_numbers(weapon_rows)
    if not tables:
        return [], ammo
    # Some pages add standalone attack tables (e.g. a mine's fire damage) outside the
    # attack list; treat those as extra effects too.
    listed = {attack_key(name) for _, name, _ in attack_list}
    base = attack_key(attack_list[0][1]) if attack_list else None
    attack_list += [(2, table_title, kind) for key, (kind, table_title, _) in tables.items() if key not in listed]

    # Explosions and shrapnel are referenced by name from the attack that triggers them.
    roles = {}
    for kind, _, rows in tables.values():
        for _, label, value in rows:
            target = attack_key(value)
            if label == "Explosion On Impact":
                roles.setdefault(target, "Impact explosion")
            elif label == "Explode After":
                roles.setdefault(target, "Delayed detonation")
            elif label == "Shrapnel":
                roles.setdefault(target, "Shrapnel")

    effects, seen = [], set()
    for depth, name, kind in attack_list:
        key = attack_key(name)
        if key == base or key in seen or key not in tables:
            continue
        seen.add(key)
        table_kind, table_title, rows = tables[key]
        stats = summarize_attack(rows)
        if not stats:
            continue
        if table_kind == "status":
            label = "Status: " + status_name(table_title)
        elif table_kind == "damage" and key.startswith("dps"):
            element = next((v for s, l, v in rows if l == "Element"), "") or table_title[3:].strip()
            label = f"Damage over time: {element}"
        elif table_kind == "damage":
            # Plain "damage" attacks are bayonets, stomps, flame streams, death explosions…;
            # their own names describe them better than a generic type.
            label = status_name(table_title).title()
        elif key in roles:
            label = roles[key]
        elif depth == 1 and base in tables and tables[base][0] == table_kind:
            label = "Alternate ammo / fire mode"
        else:
            label = TYPE_TITLES.get(table_kind, table_kind.title())
        effects.append({"title": label, "source": table_title, "stats": stats})

    # Statuses applied by an attack but without their own table (e.g. a stun baton's
    # "Stun Large") would otherwise only be visible on the base attack, which is not shown.
    covered = {fx["title"].lower() for fx in effects}
    for kind, table_title, rows in tables.values():
        for _, label, value in rows:
            if label in ("Status", "Second Status") and value:
                name = status_name(value)
                if f"status: {name}".lower() not in covered:
                    covered.add(f"status: {name}".lower())
                    applied = "In the blast area" if kind == "explosion" else "On hit"
                    effects.append({"title": f"Status: {name}", "source": table_title, "stats": {"Applied": applied}})
    return effects, ammo


def status_name(value):
    # Internal status names can be CamelCase ("FlamerSlowed") or use underscores.
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value.replace("_", " ")).strip()


# ---------------------------------------------------------------- vehicles ---
# Vehicle attack data has a hull section (Main Health, Main Armor) followed by one section per weapon
# mount, each with its own fire rate, capacity and attack list. The Anatomy table adds explosive resistance.

# Some ammo counts only appear in a vehicle page's Tactical Information prose, not its stat tables. These
# corrections are applied to the extracted mounts (matched by mount position). Last checked 2026-11-12.
VEHICLE_AMMO_FIXES = {
    "TD-220 Bastion MK XVI": {
        "mounts": {0: {"name": "120mm cannon", "spareRounds": 30, "startRounds": 30,
                       "note": "31 cannon shells in total (wiki Tactical Information)"},
                   1: {"name": "Coaxial HMG (MG-206)", "note": "2,000 rounds (wiki Tactical Information)"}},
    },
    "TD-110 Maelstrom": {
        "mounts": {0: {"name": "Rotary guns", "spareMags": 6, "startMags": 6,
                       "note": "7 belts of 300 rounds, 2,100 in total; reloading early discards the rest of the belt (wiki Tactical Information)"},
                   1: {"name": "Missile pods", "capacity": 20,
                       "note": "2 pods of 10 missiles, 20 in total (wiki Tactical Information)"}},
    },
    "M-103 Supply FRV": {
        "supplyCharges": 8,
        "mounts": {0: {"name": "Automated turret (AR-23P)", "chargeReload": True,
                       "note": "About 120 rounds; reloading it uses one of the vehicle's 8 supply charges (wiki Tactical Information)"}},
    },
    "M-104 Incinerator FRV": {
        "mounts": {0: {"name": "Mounted Cremator", "spareMags": None, "startMags": None,
                       "note": "800 fuel, about 100 seconds of continuous fire (wiki Tactical Information)"}},
    },
    "EXO-49 Emancipator Exosuit": {"mounts": {0: {"note": "100 shots per arm"}, 1: {"note": "100 shots per arm"}}},
    "EXO-51 Lumberer Exosuit": {"mounts": {1: {"note": "500 fuel, about 62 seconds of sustained fire (wiki Tactical Information)"}}},
    "M-102 Gunner FRV": {"mounts": {0: {"note": "4 spare magazines with no way to refill them (wiki Tactical Information)"}}},
}


def apply_vehicle_fixes(title, vehicle):
    fixes = VEHICLE_AMMO_FIXES.get(title)
    if not fixes:
        return vehicle
    if fixes.get("supplyCharges"):
        vehicle["supplyCharges"] = fixes["supplyCharges"]
    for index, fix in fixes.get("mounts", {}).items():
        if index >= len(vehicle.get("weapons", [])):
            print(f"  ! {title}: no mount {index} to correct", file=sys.stderr)
            continue
        weapon = vehicle["weapons"][index]
        ammo = weapon.setdefault("ammo", {})
        for key, value in fix.items():
            if key == "name":
                weapon["name"] = value
            elif key in ("note", "chargeReload"):
                weapon[key] = value
            elif value is None:
                ammo.pop(key, None)
            else:
                ammo[key] = value
    return vehicle


def vehicle_data(title, wikitext):
    calls = re.findall(r"\{\{\s*Attack[ _]Data[^{}]*\}\}", wikitext)
    if not calls:
        return None
    hull, mounts, tables, referenced = {}, [], {}, set()
    for call in calls:
        markup = api({"action": "parse", "prop": "text", "contentmodel": "wikitext", "text": call, "title": title})
        markup = markup.get("parse", {}).get("text", {}).get("*", "")
        for key, value in parse_attack_tables(markup)[1].items():
            tables.setdefault(key, value)
        for body in re.findall(r'<table class="[^"]*attack-data-table-weapon"[^>]*>(.*?)</table>', markup, re.S):
            section = None
            for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
                cells = re.findall(r"<t([hd])[^>]*>(.*?)</t[hd]>", row, re.S)
                if not cells:
                    continue
                if cells[0][0] == "h":
                    heading = cell_text(cells[0][1])
                    if heading.lower() == "attacks":
                        continue
                    # The first heading is the vehicle itself; later ones are weapon mounts.
                    section = None if not hull and section is None and not mounts else {"name": re.sub(r"^SWP\s+", "", heading).title(), "rows": [], "attacks": []}
                    if section is not None:
                        mounts.append(section)
                    continue
                label, value = cell_text(cells[0][1]), cell_text(cells[1][1]) if len(cells) > 1 else ""
                if label.startswith("*"):
                    if section is not None and label.count("*") == 1:
                        section["attacks"].append(label.lstrip("* ").strip())
                    referenced.add(attack_key(label.lstrip("* ").strip()))
                elif section is None:
                    hull.setdefault(label, value)
                else:
                    section["rows"].append((label, value))
    if not hull and not mounts:
        return None

    def attack_summaries(names):
        out = []
        for name in names:
            found = tables.get(attack_key(name))
            if found and "backblast" not in found[1].lower():  # rocket backblast is a few points of noise
                stats = summarize_attack(found[2])
                if stats:
                    out.append({"title": TYPE_TITLES.get(found[0], found[0].title()), "source": found[1], "stats": stats})
        return out

    title_words = {word.lower() for word in re.findall(r"[\w-]+", title)}
    acronyms = {"hmg", "mg", "at", "frv", "ar", "gl", "exo", "aa"}

    def tidy(name):
        return " ".join(word.upper() if word.lower() in acronyms else word for word in name.title().split())

    def mount_name(heading, attack_names):
        # Mount headings repeat the vehicle's name ("Patriot Exosuit Hmg", "Bastion Mk Xviii"): keep what's left,
        # or fall back to the gun's designation ("MG-206") or "Main gun".
        def is_name_part(word):
            low = word.lower()
            return low in title_words or re.fullmatch(r"[ivxlc]+", low) or any(low.startswith(t) and re.fullmatch(r"[ivxlc]+", low[len(t):]) for t in title_words if len(t) > 3)
        words = [word for word in heading.split() if not is_name_part(word)]
        if words:
            return tidy(" ".join(words))
        designation = next((m.group(1) for name in attack_names for m in [re.match(r"([A-Z]+-\d+)", name)] if m), None)
        return designation or "Main gun"

    weapons = []
    for mount in mounts:
        ammo = ammo_numbers(mount["rows"])
        weapon = {"name": mount_name(mount["name"], mount["attacks"]), "attacks": attack_summaries(mount["attacks"])}
        if ammo:
            weapon["ammo"] = ammo
        weapons.append(weapon)
    # Two unnamed mounts: the harder-hitting one is the main gun, the other the secondary gun.
    unnamed = [weapon for weapon in weapons if weapon["name"] == "Main gun"]
    if len(unnamed) > 1:
        top = lambda weapon: max((int(re.match(r"\d+", attack["stats"].get("Damage", "0")).group()) for attack in weapon["attacks"] if re.match(r"\d+", attack["stats"].get("Damage", ""))), default=0)
        for rank, weapon in enumerate(sorted(unnamed, key=top, reverse=True)):
            weapon["name"] = "Main gun" if rank == 0 else ("Secondary gun" if rank == 1 else f"Gun {rank + 1}")
    # Stand-alone attacks (stomps, destruction explosions) not fired by a mount.
    extras = [{"title": tidy(status_name(found[1])), "source": found[1], "stats": summarize_attack(found[2])}
              for key, found in tables.items() if key not in referenced and summarize_attack(found[2])]
    # Explosions triggered by a mount's projectile (e.g. the Bastion shell's blast) belong to that mount.
    for weapon in weapons:
        for attack in list(weapon["attacks"]):
            rows = tables.get(attack_key(attack["source"]), (None, None, []))[2]
            for _, label, value in rows:
                if label in ("Explosion On Impact", "Explode After") and tables.get(attack_key(value)):
                    found = tables[attack_key(value)]
                    weapon["attacks"].append({"title": "Impact explosion" if label == "Explosion On Impact" else "Delayed detonation", "source": found[1], "stats": summarize_attack(found[2])})
                    extras = [extra for extra in extras if attack_key(extra["source"]) != attack_key(value)]
    exdr = re.search(r"part_name\s*=\s*Main\s*\n(?:[^}]*?\n)*?\s*\|\s*exdr\s*=\s*([^\n|]+)", wikitext)
    vehicle = {
        "health": int(re.sub(r"[^\d]", "", hull.get("Main Health", "")) or 0) or None,
        "armor": hull.get("Main Armor") or None,
        "explosiveResist": exdr.group(1).strip() if exdr else None,
        "weapons": weapons,
        "extras": extras,
    }
    return apply_vehicle_fixes(title, {key: value for key, value in vehicle.items() if value})


# ----------------------------------------------------------------- enemies ---
# Every page in the faction categories with an {{Infobox Enemy}}: health, attacks and the Anatomy table.

ENEMY_FACTIONS = ["Terminids", "Automatons", "Illuminate"]
def armor_name(av):
    """Armor values share the penetration scale, so AV 4 needs Heavy (AP 4) penetration to damage it."""
    try:
        av = int(av)
    except (TypeError, ValueError):
        return ""
    if av < 0:
        return "Indestructible"
    name = "Unarmored" if av <= 1 else PEN_NAMES.get(av) or f"Anti-Tank {av - 4}"
    return f"{name} (AV {av})"


def first_number(text):
    match = re.search(r"\d[\d,]*", text or "")
    return int(match.group().replace(",", "")) if match else None


def enemy_attacks(raw):
    """'{{Damage|Melee|35 Slash|notext}} <hr> …' → [{'name': 'Slash', 'damage': 35, 'type': 'Melee', 'text': …}]."""
    attacks = []
    for kind, value in re.findall(r"\{\{\s*Damage\s*\|\s*([^|}]+)\|([^|}]+)", raw or ""):
        value = render(value)
        damage = first_number(value)
        name = re.sub(r"^\s*[\d.,/]+\s*(?:s\b)?", "", value).strip(" -·") or kind.strip()
        attacks.append({"name": name, "damage": damage, "type": kind.strip().title(), "text": value})
    return attacks


def enemy_entry(title, wikitext):
    box = find_template(wikitext, r"Infobox[ _]Enemy")
    if not box:
        return None
    fields = template_fields(box)
    parts = []
    for row in re.findall(r"\{\{\s*Anatomy Row(.*?)\n\s*\}\}", wikitext, re.S):
        row_fields = template_fields("x" + row)
        name = render(row_fields.get("part_name", ""), title).replace(" / ", " ")
        if not name:
            continue
        health_text = render(row_fields.get("health", ""), title)
        parts.append({
            "name": name,
            "health": first_number(health_text) if first_number(health_text) else health_text.split(" ")[0] or None,
            "armor": armor_name(row_fields.get("av")),
            "fatal": render(row_fields.get("fatal", ""), title) or None,
            "toMain": render(row_fields.get("percent_to_main", ""), title) or None,
        })
    main = next((part for part in parts if part["name"].lower() == "main"), None)
    exdr = re.search(r"part_name\s*=\s*Main\s*\n(?:[^}]*?\n)*?\s*\|\s*exdr\s*=\s*([^\n|]+)", wikitext)
    difficulty = first_number(render(fields.get("min_difficulty", ""), title))
    entry = {
        "page": title,
        "faction": render(fields.get("faction", ""), title) or None,
        "health": first_number(render(fields.get("health", ""), title)) or (main and isinstance(main["health"], int) and main["health"]) or None,
        "healthNote": render(fields.get("health", ""), title) or None,
        "armor": main["armor"] if main else None,
        "explosiveResist": (exdr.group(1).strip().rstrip("%") + "%") if exdr and re.match(r"\d", exdr.group(1).strip()) else None,
        "minDifficulty": difficulty,
        "description": render(fields.get("description", ""), title) or armory_description(wikitext, title) or None,
        "attacks": enemy_attacks(fields.get("damage", "")),
        "parts": [part for part in parts if part["name"].lower() != "main"],
    }
    return {key: value for key, value in entry.items() if value not in (None, [], "")}


def build_enemies():
    enemies = {}
    for faction in ENEMY_FACTIONS:
        for title in sorted(category_titles("Category:" + faction)):
            try:
                data = api({"action": "parse", "page": title, "prop": "wikitext", "redirects": 1})
                entry = enemy_entry(data["parse"]["title"], data["parse"]["wikitext"]["*"]) if "parse" in data else None
            except Exception as error:
                print(f"  ! enemy {title}: {error}", file=sys.stderr)
                entry = None
            if entry:
                entry.setdefault("faction", faction)
                enemies[title] = entry
                print(f"  enemy      {title:<40} {entry.get('health', '?')} HP, {len(entry.get('attacks', []))} attacks, {len(entry.get('parts', []))} parts")
            time.sleep(0.4)
    out = ROOT / "data" / "enemy-stats.js"
    out.write_text(
        "// Generated by tools/build_item_stats.py --enemies. Do not edit by hand.\n"
        "window.FIELD_RECORD_ENEMY_STATS = " + json.dumps({"generated": date.today().isoformat(), "source": "Helldivers Wiki (helldivers.wiki.gg), CC BY-SA 4.0", "enemies": dict(sorted(enemies.items()))}, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"\nWrote {len(enemies)} enemies to {out.relative_to(ROOT)}")


# ------------------------------------------------------------- attachments ---
# Each attachment page has an {{Infobox Attachment}} (type, description, effects, weapons that take it) and
# often variant rows (AttachVariant/MagVariant) whose effects differ by weapon family.

ATTACHMENT_STAT_LABELS = {
    "mag_capacity": "Magazine", "max_magazines": "Spare mags", "start_magazines": "Starting mags",
    "full_reload_time": "Reload", "partial_reload_time": "Tactical reload",
    "ergonomics": "Ergonomics", "horizontal_recoil": "Horizontal recoil", "vertical_recoil": "Vertical recoil",
    "horizontal_spread": "Horizontal spread", "vertical_spread": "Vertical spread", "sway": "Sway",
    "optic_range": "Zeroing", "heatsink_overheat": "Heat capacity", "heatsink_cooldown": "Cooldown",
    "heatsink_temp_per_shot": "Heat per shot",
}


def attachment_options(title, wikitext):
    box = find_template(wikitext, r"Infobox[ _]Attachment")
    if not box:
        return None, []
    fields = template_fields(box)
    kind = render(fields.get("type", ""), title)
    description = render(fields.get("description", ""), title)
    variants = []
    rows = [template_fields("x" + row) for row in re.findall(r"\{\{\s*(?:Attach|Mag)Variant/row(.*?)\n\s*\}\}", wikitext, re.S)]
    for row in rows or [fields]:
        merged = {**fields, **row} if not rows else {**{k: v for k, v in fields.items() if k in ATTACHMENT_STAT_LABELS}, **row}
        weapons = [render(name, title).strip() for name in re.split(r",", render(merged.get("available_on", ""), title)) if name.strip()]
        effects = {}
        numbers = {}
        for key, label in ATTACHMENT_STAT_LABELS.items():
            value = render(merged.get(key, ""), title).strip()
            if value:
                effects[label] = value
                number = re.match(r"[+-]?\d+(?:\.\d+)?", value)
                if number and key in ("mag_capacity", "max_magazines", "start_magazines"):
                    numbers[key] = int(float(number.group()))
        variants.append({"weapons": weapons, "effects": effects, "ammo": numbers})
    return {"name": title, "type": kind, "description": description}, variants


def build_attachments():
    """Write data/attachments.js: for each catalog weapon, the attachments it can take, grouped by type."""
    items = json.loads(re.search(r"=\s*(\{.*\});?\s*$", (ROOT / "data" / "item-stats.js").read_text(encoding="utf-8"), re.S).group(1))["items"]
    key = lambda name: re.sub(r"[^a-z0-9]", "", name.lower())
    by_page = {}
    for name, entry in items.items():
        if entry["kind"] in ("primary", "secondary") or (entry["kind"] == "stratagems" and entry.get("ammo")):
            by_page[key(entry.get("page", name))] = name
            by_page.setdefault(key(name), name)
    weapons = {}
    for title in sorted(category_titles("Category:Attachments")):
        if title == "Attachments":
            continue
        try:
            data = api({"action": "parse", "page": title, "prop": "wikitext", "redirects": 1})
            info, variants = attachment_options(title, data["parse"]["wikitext"]["*"]) if "parse" in data else (None, [])
        except Exception as error:
            print(f"  ! attachment {title}: {error}", file=sys.stderr)
            continue
        if not info:
            continue
        for variant in variants:
            for weapon in variant["weapons"]:
                name = by_page.get(key(weapon))
                if name:
                    option = {"name": info["name"], "description": info["description"], "effects": variant["effects"]}
                    if variant["ammo"]:
                        option["ammo"] = variant["ammo"]
                    weapons.setdefault(name, {}).setdefault(info["type"] or "Other", []).append(option)
        print(f"  attachment {title:<32} {info['type']}")
        time.sleep(0.4)
    out = ROOT / "data" / "attachments.js"
    out.write_text(
        "// Generated by tools/build_item_stats.py --attachments. Do not edit by hand.\n"
        "window.FIELD_RECORD_ATTACHMENTS = " + json.dumps({"generated": date.today().isoformat(), "weapons": dict(sorted(weapons.items()))}, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"\nWrote attachments for {len(weapons)} weapons to {out.relative_to(ROOT)}")


def fetch_page(name):
    """Return (title, wikitext) for the best wiki page for a catalog name."""
    data = api({"action": "parse", "page": WIKI_TITLES.get(name, name), "prop": "wikitext", "redirects": 1})
    if "parse" in data:
        return data["parse"]["title"], data["parse"]["wikitext"]["*"]
    search = api({"action": "query", "list": "search", "srsearch": name, "srlimit": 5, "srnamespace": 0})
    for hit in search.get("query", {}).get("search", []):
        data = api({"action": "parse", "page": hit["title"], "prop": "wikitext", "redirects": 1})
        if "parse" in data and re.search(r"\{\{\s*" + INFOBOX + r"\s*[|\n]", data["parse"]["wikitext"]["*"], re.I):
            return data["parse"]["title"], data["parse"]["wikitext"]["*"]
    return None, None


def passive_description(passive):
    data = api({
        "action": "parse", "prop": "text", "contentmodel": "wikitext",
        "text": "{{Armor Passive Info Panel|" + passive + "}}",
    })
    markup = data.get("parse", {}).get("text", {}).get("*", "")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", markup, flags=re.S)
    text = re.sub(r"<\s*(br|/p|/li|/div|/tr)\s*/?>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line and line.lower() != passive.lower() and "parser output" not in line.lower()]
    return " ".join(lines)


def category_titles(category):
    members = api({"action": "query", "list": "categorymembers", "cmtitle": category,
                   "cmlimit": 500, "cmnamespace": 0})
    return {m["title"] for m in members["query"]["categorymembers"]}


def read_catalogs():
    """Gear catalogs come from index.html; stratagems come from the wiki's own list."""
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const catalogs = \{(.*?)\n    \};", source, re.S).group(1)
    catalogs = {}
    for key, body in re.findall(r"(\w+): \[(.*?)\]", block, re.S):
        catalogs[key] = sorted(set(re.findall(r'"([^"]+)"', body)))
    catalogs["stratagems"] = sorted(category_titles("Category:Stratagems"))
    return catalogs


def choosable_stratagem(title, entry, mission_titles):
    """The wiki labels a few mission-only stratagems with a permit, so check several signals."""
    return (entry.get("permit") and title not in mission_titles
            and entry.get("stratagemType", "").lower() not in MISSION_TYPES
            and not title.lower().startswith("april fools"))


def main():
    # `--enemies` rebuilds only data/enemy-stats.js; a plain run rebuilds items and enemies.
    if sys.argv[1:] == ["--enemies"]:
        build_enemies()
        return
    if sys.argv[1:] == ["--attachments"]:
        build_attachments()
        return
    catalogs = read_catalogs()
    mission_titles = category_titles("Category:Mission Stratagems")
    only = set(sys.argv[1:])
    items, missing, passives = {}, [], {}
    for kind, names in catalogs.items():
        for name in names:
            if only and name not in only:
                continue
            try:
                title, wikitext = fetch_page(name)
                entry = extract(kind, title, wikitext) if title else None
            except Exception as error:  # Keep going; report at the end.
                print(f"  ! {name}: {error}", file=sys.stderr)
                entry = None
            if kind == "stratagems":
                if not entry or not choosable_stratagem(name, entry, mission_titles):
                    print(f"  {kind:<10} {name:<40} -- skipped (not a loadout stratagem)")
                    continue
                del entry["stratagemType"]
            if entry and kind in ATTACK_KINDS:
                try:
                    effects, ammo = attack_effects(title, wikitext)
                    if effects:
                        entry["effects"] = effects
                    if kind == "stratagems" and entry["stats"].get("Type") == "Vehicle":
                        vehicle = vehicle_data(title, wikitext)
                        if vehicle:
                            entry["vehicle"] = vehicle
                    support_weapon = kind == "stratagems" and entry["stats"].get("Type") == "Support Weapon"
                    if ammo and (kind in ("primary", "secondary", "throwable") or support_weapon):
                        entry["ammo"] = ammo
                except Exception as error:
                    print(f"  ! {name} attack data: {error}", file=sys.stderr)
            if entry:
                entry["kind"] = kind
                items[name] = entry
                print(f"  {kind:<10} {name:<40} <- {title} ({len(entry['stats'])} stats)")
            else:
                missing.append(f"{kind}: {name}")
                print(f"  {kind:<10} {name:<40} -- NOT FOUND", file=sys.stderr)
            time.sleep(0.4)

    for entry in items.values():
        passive = entry["stats"].get("Passive")
        if passive and passive not in passives:
            try:
                passives[passive] = passive_description(passive)
            except Exception as error:
                print(f"  ! passive {passive}: {error}", file=sys.stderr)
                passives[passive] = ""

    payload = {
        "generated": date.today().isoformat(),
        "source": "Helldivers Wiki (helldivers.wiki.gg), CC BY-SA 4.0",
        "items": dict(sorted(items.items())),
        "passives": dict(sorted(passives.items())),
    }
    out = ROOT / "data" / "item-stats.js"
    out.parent.mkdir(exist_ok=True)
    if only and out.exists():
        previous = json.loads(re.search(r"=\s*(\{.*\});?\s*$", out.read_text(encoding="utf-8"), re.S).group(1))
        previous["items"].update(payload["items"])
        previous["passives"].update(payload["passives"])
        previous["generated"] = payload["generated"]
        payload = previous
    out.write_text(
        "// Generated by tools/build_item_stats.py. Do not edit by hand; put house rules in data/item-overrides.js.\n"
        "window.FIELD_RECORD_ITEM_STATS = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"\nWrote {len(payload['items'])} items and {len(payload['passives'])} passives to {out.relative_to(ROOT)}")
    if missing:
        print(f"{len(missing)} catalog entries were not found on the wiki:")
        for line in missing:
            print("  - " + line)
    # A full run (no item names given) also refreshes the enemy library.
    if not only:
        build_enemies()
        build_attachments()


if __name__ == "__main__":
    main()
