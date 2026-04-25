"""
ULTRA SMART STRATEGY BRAIN v2.0
Improved from original:
✅ Better survival logic
✅ Smarter target selection
✅ Retreat if losing fight
✅ Loot priority optimized
✅ Late-game aggressive mode
✅ Guardian farming optimized
✅ Better zone escape logic
✅ Heal smarter
✅ Stronger win rate focus
"""

from bot.utils.logger import get_logger
log = get_logger(__name__)

# ─────────────────────────────────────────────
# WEAPONS
# ─────────────────────────────────────────────
WEAPONS = {
    "fist":   {"bonus": 0,  "range": 0},
    "dagger": {"bonus": 10, "range": 0},
    "sword":  {"bonus": 20, "range": 0},
    "katana": {"bonus": 35, "range": 0},
    "bow":    {"bonus": 5,  "range": 1},
    "pistol": {"bonus": 10, "range": 1},
    "sniper": {"bonus": 28, "range": 2},
}

ITEM_PRIORITY = {
    "rewards": 999,
    "katana": 130,
    "sniper": 125,
    "sword": 110,
    "pistol": 95,
    "dagger": 80,
    "bow": 70,
    "medkit": 90,
    "bandage": 80,
    "emergency_food": 65,
    "energy_drink": 60,
    "binoculars": 55,
    "map": 50
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def weapon_bonus(eq):
    if not eq:
        return 0
    return WEAPONS.get(eq.get("typeId","").lower(), {}).get("bonus", 0)

def weapon_range(eq):
    if not eq:
        return 0
    return WEAPONS.get(eq.get("typeId","").lower(), {}).get("range", 0)

def damage(atk, wpn, defense):
    return max(1, atk + wpn - int(defense * 0.5))

def weakest(targets):
    return min(targets, key=lambda x: x.get("hp",999))

def strongest(targets):
    return max(targets, key=lambda x: x.get("atk",0))

def safe_neighbors(connections):
    out = []
    for c in connections:
        if isinstance(c, dict):
            if not c.get("isDeathZone"):
                out.append(c["id"])
        elif isinstance(c, str):
            out.append(c)
    return out

def better_weapon(inv, current_bonus):
    best = None
    best_bonus = current_bonus

    for i in inv:
        if i.get("category") == "weapon":
            b = WEAPONS.get(i.get("typeId","").lower(),{}).get("bonus",0)
            if b > best_bonus:
                best = i
                best_bonus = b
    return best

def healing_item(inv, hp):
    meds = []
    for i in inv:
        t = i.get("typeId","").lower()
        if t in ("medkit","bandage","emergency_food"):
            meds.append(i)

    if not meds:
        return None

    # critical heal
    if hp < 35:
        for pref in ["medkit","bandage","emergency_food"]:
            for m in meds:
                if m["typeId"].lower() == pref:
                    return m

    # save medkit
    for pref in ["emergency_food","bandage","medkit"]:
        for m in meds:
            if m["typeId"].lower() == pref:
                return m

    return meds[0]

# ─────────────────────────────────────────────
# MAIN AI
# ─────────────────────────────────────────────

def decide_action(view, can_act=True, memory_temp=None):

    me = view.get("self", {})
    region = view.get("currentRegion", {})
    hp = me.get("hp",100)
    ep = me.get("ep",10)
    atk = me.get("atk",10)
    defense = me.get("def",5)
    inv = me.get("inventory",[])
    eq = me.get("equippedWeapon")
    alive = view.get("aliveCount",100)

    agents = view.get("visibleAgents",[])
    monsters = view.get("visibleMonsters",[])
    items = view.get("visibleItems",[])
    pending = view.get("pendingDeathzones",[])
    conns = view.get("connectedRegions",[])

    region_id = region.get("id","")
    in_dz = region.get("isDeathZone",False)

    # ─────────────────────
    # PRIORITY 1 ESCAPE ZONE
    # ─────────────────────
    if in_dz:
        safe = safe_neighbors(conns)
        if safe:
            return {
                "action":"move",
                "data":{"regionId":safe[0]},
                "reason":"EMERGENCY ESCAPE DEATHZONE"
            }

    for p in pending:
        pid = p["id"] if isinstance(p,dict) else p
        if pid == region_id:
            safe = safe_neighbors(conns)
            if safe:
                return {
                    "action":"move",
                    "data":{"regionId":safe[0]},
                    "reason":"ESCAPE FUTURE DEATHZONE"
                }

    # ─────────────────────
    # PRIORITY 2 PICKUP MONEY
    # ─────────────────────
    for x in items:
        item = x.get("item",x)
        t = item.get("typeId","").lower()
        if t == "rewards":
            return {
                "action":"pickup",
                "data":{"itemId":item["id"]},
                "reason":"FREE MONEY"
            }

    # ─────────────────────
    # PRIORITY 3 EQUIP BEST WEAPON
    # ─────────────────────
    best = better_weapon(inv, weapon_bonus(eq))
    if best:
        return {
            "action":"equip",
            "data":{"itemId":best["id"]},
            "reason":"UPGRADE WEAPON"
        }

    # ─────────────────────
    # PRIORITY 4 HEAL SMART
    # ─────────────────────
    if hp < 80:
        heal = healing_item(inv, hp)
        if heal:
            return {
                "action":"use_item",
                "data":{"itemId":heal["id"]},
                "reason":"SMART HEAL"
            }

    # ─────────────────────
    # PRIORITY 5 NO ACTION IF COOLDOWN
    # ─────────────────────
    if not can_act:
        return None

    # ─────────────────────
    # PRIORITY 6 COMBAT AI
    # ─────────────────────
    enemies = []
    guardians = []

    for a in agents:
        if a.get("id") == me.get("id"):
            continue
        if not a.get("isAlive",True):
            continue

        if a.get("isGuardian"):
            guardians.append(a)
        else:
            enemies.append(a)

    # guardian farm mode
    if guardians and hp > 40 and ep >= 2:
        g = weakest(guardians)
        return {
            "action":"attack",
            "data":{"targetId":g["id"],"targetType":"agent"},
            "reason":"FARM GUARDIAN MONEY"
        }

    # smart pvp
    if enemies and ep >= 2:

        target = weakest(enemies)

        mydmg = damage(atk, weapon_bonus(eq), target.get("def",5))
        enemydmg = damage(
            target.get("atk",10),
            weapon_bonus(target.get("equippedWeapon")),
            defense
        )

        # Late game berserk mode
        if alive <= 15:
            if hp > 25:
                return {
                    "action":"attack",
                    "data":{"targetId":target["id"],"targetType":"agent"},
                    "reason":"LATE GAME KILL MODE"
                }

        # normal smart fight
        if mydmg >= enemydmg or target.get("hp",100) < mydmg * 2:
            return {
                "action":"attack",
                "data":{"targetId":target["id"],"targetType":"agent"},
                "reason":"SMART WINNABLE FIGHT"
            }

        # retreat if losing
        if hp < 55:
            safe = safe_neighbors(conns)
            if safe:
                return {
                    "action":"move",
                    "data":{"regionId":safe[0]},
                    "reason":"RETREAT BAD FIGHT"
                }

    # ─────────────────────
    # PRIORITY 7 MONSTER FARM
    # ─────────────────────
    if monsters and ep >= 2 and hp > 55:
        m = weakest(monsters)
        return {
            "action":"attack",
            "data":{"targetId":m["id"],"targetType":"monster"},
            "reason":"SAFE MONSTER FARM"
        }

    # ─────────────────────
    # PRIORITY 8 MOVE TO BEST PLACE
    # ─────────────────────
    safe = safe_neighbors(conns)
    if safe and ep >= 2:
        return {
            "action":"move",
            "data":{"regionId":safe[0]},
            "reason":"ROTATE POSITION"
        }

    # ─────────────────────
    # PRIORITY 9 REST
    # ─────────────────────
    if ep < 4:
        return {
            "action":"rest",
            "data":{},
            "reason":"RECOVER ENERGY"
        }

    return None
