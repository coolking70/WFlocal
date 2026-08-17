#!/usr/bin/env python3
"""Generate the reference the Hub's DSL view reads.

The view needs three things the browser cannot work out for itself:

  names    which positional slot is which parameter - from the Haxe enum's
           __params__, already extracted into reverse/enum_params.json
  ranges   what the shipped skills use for that parameter, so a value can be
           read as "normal" or "far outside anything official"
  units    what the number means - frames, pixels, radians

reverse/ is not under the server root, and scanning 63 DSL files in the browser
to derive ranges would be slow and would duplicate logic that already exists
here. So this precomputes all of it into one served file.

    python3 tools/build_dsl_reference.py            # write WFTest/wfmod/dsl-reference.json
    python3 tools/build_dsl_reference.py --check    # fail if it is out of date

`--check` runs in verify_all.sh: an edited enum dump or a new DSL file must not
leave the Hub showing yesterday's reference.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "reverse" / "enum_params.json"
OUT = ROOT / "WFTest" / "wfmod" / "dsl-reference.json"
ASSET_ROOTS = (ROOT / "WFTest" / "assets" / "production",
               ROOT / "WFTest" / "assets" / "trial" / "production")
COMMAND_ENUM = "pinball.battle.action.dsl.ActionDslCommand"
FORK_DIR = "wfmod"

# What a number means, by parameter name. Only the three settled in
# reverse/character-skill-chain.md are marked measured; the rest say so, because
# a unit label the data does not support is worse than no label.
#
#   frames   1/60 s      - ShowEffect.lifetime 347 -> 120 measured ~2s on screen
#   px       logical px  - ShowEffect.u 2000 pushed the effect off a 540-wide screen
#   rad      radians     - NWay 6 @ 0.5236 produced hit areas at +-15/45/75 degrees
UNITS = {
    "frame": ("frames", "measured"),
    "lifetime": ("frames", "measured"),
    "minHitInterval": ("frames", "measured"),
    "u": ("px", "measured"),
    "v": ("px", "measured"),
    "radius": ("px", "measured"),
    "width": ("px", "measured"),
    "height": ("px", "measured"),
    "w": ("rad", "measured"),
    "angle": ("rad", "measured"),
    "a": ("rad", "measured"),
    "s": ("px", "inferred"),
    "o": ("px", "inferred"),
    "movingSpeed": ("px/frame", "inferred"),
    "spreadingSpeed": ("?", "unknown"),
    "damage": ("flat damage", "measured"),
}


# Chinese labels for the view. Hand-written, and deliberately incomplete: a
# parameter whose meaning has not been established gets no label rather than a
# guess, because a confident wrong label is worse than an empty cell. Where a
# meaning was settled by experiment, the note says so.
#
# PARAM_NOTES applies to a parameter name wherever it appears; COMMAND_NOTES adds
# per-command descriptions and overrides for names that mean different things in
# different commands.
PARAM_NOTES = {
    "id": "命令自身的编号，DSL 内部引用用；负数是绑定好的固定点（-1 场地中心 / -2 左上 / -17 角色 / -18 弹珠）",
    "symbol": "判定区跟随的对象（同上的编号规则）",
    "coordSys": "坐标系：AB 世界 / CD 角色朝向 / EF 移动方向 / GH 指向某对象",
    "u": "横向偏移（目标朝向旋转后的局部坐标，逻辑像素）",
    "v": "纵向偏移（同上）",
    "w": "角度偏移（弧度）",
    "frame": "持续帧数（60fps，即 1/60 秒）",
    "lifetime": "存在时长",
    "name": "名称（HideEffect 按名字关闭时要对上）",
    "effect": "特效资源路径",
    "layerZDepth": "绘制层次（角色前/后等）",
    "scale": "缩放倍数",
    "trackingPosition": "是否随目标移动",
    "trackingDirection": "是否随目标转向",
    "shape": "判定形状",
    "hAlign": "横向对齐",
    "vAlign": "纵向对齐",
    "formation": "多重判定的排布方式；NWay 分的是朝向而非位置（实测）",
    "minHitInterval": "同一目标两次命中的最小间隔",
    "maxNumOfHits": "命中次数上限（None 为不封顶）",
    "eliminatedOnHit": "命中后是否消失",
    "cracksWeakPoint": "是否能破弱点",
    "element": "属性（255 表示继承角色属性）",
    "damage": "固定伤害，与攻击力无关（实测）",
    "sLvMultiplierOfAttackPoint": "攻击力倍率，min/max 按技能等级插值",
    "hitEffect": "命中特效",
    "size": "震动幅度",
    "speed": "速度",
    "movingSpeed": "移动速度（单位未确认）",
    "endingSpeed": "结束时的速度处理",
    "suppressDirectAttack": "期间是否禁用直接攻击",
    "probability": "触发概率",
    "conditions": "施加的状态列表",
    "radius": "半径（逻辑像素）",
    "width": "宽（逻辑像素）",
    "height": "高（逻辑像素）",
    "angle": "张角（弧度）",
    "n": "数量",
    "a": "相邻两个之间的角度（弧度）",
    "s": "间距",
    "o": "整体偏移",
    "r": "半径",
    "value": "值",
    "minHitIntervalDirect": "直接指定的最小命中间隔",
}

COMMAND_NOTES = {
    "StopBall": {"zh": "把弹珠定在原地一段时间，结束后按 endingSpeed 处理速度"},
    "MoveBall": {"zh": "让弹珠朝指定方向移动；coordSys 用 GH(目标) 时是朝该目标直线冲"},
    "HideCharacter": {"zh": "隐藏角色一段时间（技能演出期间常用）"},
    "ShowEffect": {"zh": "播放一个特效"},
    "HideEffect": {"zh": "按名字关闭正在播放的特效"},
    "ShakeCamera": {"zh": "镜头震动"},
    "CreateHitArea": {"zh": "创建判定区域——技能的命中范围就在这里；它永不渲染，只能通过谁掉血观察"},
    "CreateNormalAttack": {"zh": "在判定区内造成普通攻击伤害"},
    "CreateCondition": {"zh": "施加状态（buff / debuff）"},
    "FindAllSubjects": {"zh": "找出所有符合条件的目标，对每个执行内层命令"},
    "FindNearSubjects": {"zh": "找出附近符合条件的目标"},
    "AddSkillPoint": {"zh": "增加技能槽能量"},
    "SubtractSkillPoint": {"zh": "减少技能槽能量"},
    "AddFeverPoint": {"zh": "增加 Fever 值"},
    "SubtractFeverPoint": {"zh": "减少 Fever 值"},
    "CreateShield": {"zh": "创建护盾；这个 build 缺 boss_shield 素材，尚未跑通"},
}


def dsl_files():
    seen = {}
    for root in ASSET_ROOTS:
        for path in sorted(root.rglob("*.action.dsl.json")):
            if FORK_DIR in path.parts:
                continue                      # our own forks are not evidence
            seen.setdefault(path.name, path)
        # both roots, first one wins; the shipped set is what counts as official
    return list(seen.values())


def commands(node, out):
    if isinstance(node, list):
        if len(node) == 2 and node[0] == "Command" and isinstance(node[1], list) and node[1]:
            out.append(node[1])
        for item in node:
            commands(item, out)
    return out


def note(stats, value):
    """Fold one argument into the running description of a parameter."""
    if isinstance(value, bool):
        stats.setdefault("values", {})[str(value).lower()] = \
            stats.setdefault("values", {}).get(str(value).lower(), 0) + 1
    elif isinstance(value, (int, float)):
        numbers = stats.setdefault("numeric", {"min": value, "max": value, "count": 0})
        numbers["min"] = min(numbers["min"], value)
        numbers["max"] = max(numbers["max"], value)
        numbers["count"] += 1
    elif isinstance(value, dict) and "min" in value and "max" in value:
        for side in ("min", "max"):
            note(stats, value[side])
    elif isinstance(value, list) and value and isinstance(value[0], str):
        kinds = stats.setdefault("kinds", {})
        kinds[value[0]] = kinds.get(value[0], 0) + 1
        for inner in value[1:]:
            note(stats.setdefault("inner", {}), inner)
    elif isinstance(value, str):
        stats.setdefault("values", {})[value] = stats.setdefault("values", {}).get(value, 0) + 1


def resolve_enums(all_enums, ranges):
    """Name each parameter's enum from the constructors the shipped data uses.

    Most of a command's numbers live *inside* an enum - the radius is in
    Shape.Circle(radius), the fan angle in Formation.NWay(n, a) - so without this
    the view can only label the outer parameter and leaves the interesting values
    unnamed and unconverted.

    Which enum a parameter holds is not written anywhere, but it is decidable:
    take the constructor names actually observed and find the enum whose
    constructors cover them. `Circle` alone is ambiguous between Shape and
    Formation; `{Circle, Rectangle}` is not.
    """
    candidates = {name: set(constructors) for name, constructors in all_enums.items()
                  if name.startswith("pinball.battle.action.dsl.")}
    out = {}
    for command, table in ranges.items():
        for param, stats in table["params"].items():
            observed = set((stats.get("kinds") or {}).keys())
            if not observed:
                continue
            # {None, Some} is Haxe's Option and identifies nothing: it matched
            # TweenSource by accident and labelled maxNumOfHits, an Option<Int>,
            # as a tween. A constructor set this generic must not name an enum.
            if observed <= {"None", "Some"}:
                out.setdefault(command, {})[param] = "Option"
                continue
            matches = [name for name, constructors in candidates.items()
                       if observed <= constructors]
            if len(matches) != 1:
                continue                       # ambiguous or unknown: say nothing
            short = matches[0].rsplit(".", 1)[-1]
            out.setdefault(command, {})[param] = short
    return out


def build():
    all_enums = json.loads(PARAMS.read_text(encoding="utf-8"))
    names = all_enums.get(COMMAND_ENUM)
    if not names:
        sys.exit(f"{PARAMS.relative_to(ROOT)} has no {COMMAND_ENUM}; "
                 f"run tools/dump_runtime_enums.mjs")

    files = dsl_files()
    ranges = {}
    for path in files:
        for command in commands(json.loads(path.read_text(encoding="utf-8")), []):
            name = command[0]
            fields = names.get(name)
            if not fields:
                continue
            table = ranges.setdefault(name, {"uses": 0, "params": {}})
            table["uses"] += 1
            for i, value in enumerate(command[1:]):
                if i >= len(fields):
                    break
                note(table["params"].setdefault(fields[i], {}), value)

    dsl_enums = {name.rsplit(".", 1)[-1]: constructors
                 for name, constructors in all_enums.items()
                 if name.startswith("pinball.battle.action.dsl.")}
    dsl_enums["Option"] = {"None": [], "Some": ["value"]}
    param_enums = resolve_enums(all_enums, ranges)

    return {
        "note": "generated by tools/build_dsl_reference.py - do not edit",
        "sampled": len(files),
        "enums": dsl_enums,
        "paramEnums": param_enums,
        "units": {k: {"unit": u, "confidence": c} for k, (u, c) in UNITS.items()},
        "paramNotes": PARAM_NOTES,
        "commands": {
            name: {
                "params": fields,
                "uses": ranges.get(name, {}).get("uses", 0),
                "enums": param_enums.get(name, {}),
                "zh": COMMAND_NOTES.get(name, {}).get("zh", ""),
                "paramZh": COMMAND_NOTES.get(name, {}).get("params", {}),
                "observed": ranges.get(name, {}).get("params", {})
            }
            for name, fields in sorted(names.items())
        }
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    reference = build()
    text = json.dumps(reference, ensure_ascii=False, indent=1) + "\n"

    if args.check:
        if not OUT.exists():
            sys.exit(f"{OUT.relative_to(ROOT)} does not exist; "
                     f"run python3 tools/build_dsl_reference.py")
        if OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"{OUT.relative_to(ROOT)} is out of date; "
                     f"run python3 tools/build_dsl_reference.py")
        used = sum(1 for c in reference["commands"].values() if c["uses"])
        print(f"dsl reference is current: {len(reference['commands'])} commands, "
              f"{used} used by the {reference['sampled']} shipped skills")
        return 0

    OUT.write_text(text, encoding="utf-8")
    used = sum(1 for c in reference["commands"].values() if c["uses"])
    annotated = sum(1 for c in reference["commands"].values() if c["zh"])
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  commands          {len(reference['commands'])} ({used} used by shipped skills)")
    print(f"  with a note       {annotated}")
    print(f"  parameter notes   {len(PARAM_NOTES)}")
    print(f"  DSL files sampled {reference['sampled']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
