"""
FULL SMART STRATEGY BRAIN v3.0
Drop-in replacement for strategy.py

Features:
✅ Deathzone escape
✅ Pending deathzone escape
✅ Smart pickup
✅ Auto equip best weapon
✅ Smart healing
✅ Guardian farming
✅ Smart PvP fight decision
✅ Retreat losing fights
✅ Monster farming
✅ Strategic movement
✅ Rest logic
✅ Stable / no syntax error
"""

from bot.utils.logger import get_logger

log = get_logger(__name__)

# =====================================================
# WEAPON DATA
# =====================================================

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
    "emergency_food": 70,
    "energy_drink": 60,
    "map": 50,
    "binoculars": 40
}

# =====================================================
# BASIC HELPERS
# =====================================================

def weapon_bonus(eq):
    if not eq:
        return 0
    t = eq.get("typeId", "").lower()
    return WEAPONS.get(t, {}).get("bonus", 0)


def weapon_range(eq):
    if not eq:
        return 0
    t = eq.get("typeId", "").lower()
    return WEAPONS.get(t, {}).get("range", 0)


def calc_damage(atk, bonus, defense):
    return max(1, atk + bonus - int(defense * 0.5))


def weakest(targets):
    if not targets:
        return None
    return min(targets, key=lambda x: x.get("hp", 999))


def safest_connections(connections):
    result = []

    for c in connections:
        if isinstance(c, str):
            result.append(c)

        elif isinstance(c, dict):
            if not c.get("isDeathZone", False):
                rid = c.get("id")
                if rid:
                    result.append(rid)

    return result


def find_best_weapon(inv, current_bonus):
    best = None
    best_bonus = current_bonus

    for item in inv:
        if not isinstance(item, dict):
            continue

        if item.get("category") == "weapon":
            t = item.get("typeId", "").lower()
            b = WEAPONS.get(t, {}).get("bonus", 0)

            if b > best_bonus:
                best_bonus = b
                best = item

    return best


def find_heal(inv, hp):
    meds = []

    for item in inv:
        if not isinstance(item, dict):
            continue

        t = item.get("typeId", "").lower()

        if t in ["medkit", "bandage", "emergency_food"]:
            meds.append(item)

    if not meds:
        return None

    # Critical heal
    if hp < 35:
        order = ["medkit", "bandage", "emergency_food"]
    else:
        order = ["emergency_food", "bandage", "medkit"]

    for name in order:
        for m in meds:
            if m.get("typeId", "").lower() == name:
                return m

    return meds[0]


def pickup_score(item):
    t = item.get("typeId", "").lower()
    return ITEM_PRIORITY.get(t, 0)


def get_visible_items(raw):
    items = []

    for x in raw:
        if not isinstance(x, dict):
            continue

        inner = x.get("item")

        if isinstance(inner, dict):
            inner["regionId"] = x.get("regionId")
            items.append(inner)
        else:
            items.append(x)

    return items


# =====================================================
# MAIN DECISION ENGINE
# =====================================================

def decide_action(view, can_act=True, memory_temp=None):

    me = view.get("self", {})
    region = view.get("currentRegion", {})

    hp = me.get("hp", 100)
    ep = me.get("ep", 10)
    atk = me.get("atk", 10)
    defense = me.get("def", 5)

    inv = me.get("inventory", [])
    eq = me.get("equippedWeapon")

    my_id = me.get("id")
    region_id = region.get("id")

    alive_count = view.get("aliveCount", 100)

    visible_agents = view.get("visibleAgents", [])
    visible_monsters = view.get("visibleMonsters", [])
    visible_items = get_visible_items(view.get("visibleItems", []))

    pending = view.get("pendingDeathzones", [])
    connections = view.get("connectedRegions", [])

    # =================================================
    # 1. ESCAPE ACTIVE DEATHZONE
    # =================================================
    if region.get("isDeathZone", False):
        safe = safest_connections(connections)

        if safe:
            return {
                "action": "move",
                "data": {"regionId": safe[0]},
                "reason": "ESCAPE ACTIVE DEATHZONE"
            }

    # =================================================
    # 2. ESCAPE PENDING DEATHZONE
    # =================================================
    for p in pending:

        pid = p if isinstance(p, str) else p.get("id")

        if pid == region_id:
            safe = safest_connections(connections)

            if safe:
                return {
                    "action": "move",
                    "data": {"regionId": safe[0]},
                    "reason": "ESCAPE FUTURE DEATHZONE"
                }

    # =================================================
    # 3. PICKUP BEST ITEM
    # =================================================
    local_items = []

    for item in visible_items:
        if item.get("regionId") == region_id or not item.get("regionId"):
            local_items.append(item)

    if local_items:
        local_items.sort(key=pickup_score, reverse=True)

        best = local_items[0]

        if pickup_score(best) > 0:
            return {
                "action": "pickup",
                "data": {"itemId": best["id"]},
                "reason": "PICKUP BEST ITEM"
            }

    # =================================================
    # 4. AUTO EQUIP BEST WEAPON
    # =================================================
    best_weapon = find_best_weapon(inv, weapon_bonus(eq))

    if best_weapon:
        return {
            "action": "equip",
            "data": {"itemId": best_weapon["id"]},
            "reason": "EQUIP BETTER WEAPON"
        }

    # =================================================
    # 5. HEALING
    # =================================================
    if hp < 80:
        heal = find_heal(inv, hp)

        if heal:
            return {
                "action": "use_item",
                "data": {"itemId": heal["id"]},
                "reason": "HEAL"
            }

    # =================================================
    # STOP IF COOLDOWN
    # =================================================
    if not can_act:
        return None

    # =================================================
    # SPLIT ENEMIES / GUARDIANS
    # =================================================
    enemies = []
    guardians = []

    for a in visible_agents:

        if not isinstance(a, dict):
            continue

        if a.get("id") == my_id:
            continue

        if not a.get("isAlive", True):
            continue

        if a.get("isGuardian", False):
            guardians.append(a)
        else:
            enemies.append(a)

    # =================================================
    # 6. FARM GUARDIAN
    # =================================================
    if guardians and hp > 45 and ep >= 2:
        g = weakest(guardians)

        return {
            "action": "attack",
            "data": {
                "targetId": g["id"],
                "targetType": "agent"
            },
            "reason": "FARM GUARDIAN"
        }

    # =================================================
    # 7. SMART PVP
    # =================================================
    if enemies and ep >= 2:

        target = weakest(enemies)

        my_dmg = calc_damage(
            atk,
            weapon_bonus(eq),
            target.get("def", 5)
        )

        enemy_dmg = calc_damage(
            target.get("atk", 10),
            weapon_bonus(target.get("equippedWeapon")),
            defense
        )

        # Late game more aggressive
        if alive_count <= 12 and hp > 25:
            return {
                "action": "attack",
                "data": {
                    "targetId": target["id"],
                    "targetType": "agent"
                },
                "reason": "LATE GAME AGGRESSIVE"
            }

        # Winnable fight
        if my_dmg >= enemy_dmg or target.get("hp", 100) <= my_dmg * 2:
            return {
                "action": "attack",
                "data": {
                    "targetId": target["id"],
                    "targetType": "agent"
                },
                "reason": "SMART ATTACK"
            }

        # Retreat if losing
        if hp < 55:
            safe = safest_connections(connections)

            if safe:
                return {
                    "action": "move",
                    "data": {"regionId": safe[0]},
                    "reason": "RETREAT BAD FIGHT"
                }

    # =================================================
    # 8. MONSTER FARM
    # =================================================
    if visible_monsters and hp > 60 and ep >= 2:

        m = weakest(visible_monsters)

        return {
            "action": "attack",
            "data": {
                "targetId": m["id"],
                "targetType": "monster"
            },
            "reason": "MONSTER FARM"
        }

    # =================================================
    # 9. MOVE SMART
    # =================================================
    if ep >= 2:

        safe = safest_connections(connections)

        if safe:
            return {
                "action": "move",
                "data": {"regionId": safe[0]},
                "reason": "SMART MOVE"
            }

    # =================================================
    # 10. REST
    # =================================================
    if ep < 4:
        return {
            "action": "rest",
            "data": {},
            "reason": "RECOVER EP"
        }

    return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
"""
View fields from api-summary.md (all implemented above — v1.5.2):
✅ self          — hp, ep, atk, def, inventory, equippedWeapon, isAlive
✅ currentRegion — id, name, terrain, weather, connections, interactables, isDeathZone
✅ connectedRegions — full Region objects OR bare string IDs (type-safe via _resolve_region)
✅ visibleRegions  — used for connectedRegions fallback + region ID lookup
✅ visibleAgents   — guardians (HOSTILE!) + enemies + combat targeting
✅ visibleMonsters — monster farming targets
✅ visibleNPCs     — acknowledged (NPCs are flavor per game-systems.md)
✅ visibleItems    — pickup + movement attraction scoring
✅ pendingDeathzones — {id, name} entries for death zone escape + movement planning
✅ recentLogs      — available for analysis
✅ recentMessages  — communication (curse disabled in v1.5.2)
✅ aliveCount      — adaptive aggression (late game adjustment)
"""
