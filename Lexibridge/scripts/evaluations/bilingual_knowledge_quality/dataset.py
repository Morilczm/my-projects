"""Synthetic corpus and frozen gold concepts for Task 11E."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from scripts.evaluations.bilingual_knowledge_quality.metrics import GoldConcept


@dataclass(frozen=True)
class SyntheticSource:
    source_id: str
    title: str
    filename: str
    language: str
    chapter: str
    domain: str
    text: str

    def to_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not include_text:
            payload.pop("text", None)
            payload["text_sha256"] = sha256_text(self.text)
            payload["text_chars"] = len(self.text)
        return payload


COURSE_NAME = "Synthetic Physics Quality Pilot 11E"
RANDOM_SEED = 1105
SCHEMA_VERSION = "11E-bilingual-knowledge-quality-v1"


GOLD_ROWS = (
    ("physics-01", "displacement", ("位移",), ("距离",), "mechanics", "mech-displacement"),
    ("physics-02", "velocity", ("速度",), ("速率",), "mechanics", "mech-velocity"),
    ("physics-03", "acceleration", ("加速度",), ("速度",), "mechanics", "mech-acceleration"),
    ("physics-04", "force", ("力",), ("功率",), "mechanics", "mech-force"),
    ("physics-05", "mass", ("质量",), ("惯性",), "mechanics", "mech-mass"),
    ("physics-06", "inertia", ("惯性",), ("质量",), "mechanics", "mech-inertia"),
    ("physics-07", "momentum", ("动量",), ("冲量",), "mechanics", "mech-momentum"),
    ("physics-08", "impulse", ("冲量",), ("动量",), "mechanics", "mech-impulse"),
    ("physics-09", "kinetic energy", ("动能",), ("功",), "mechanics", "mech-kinetic-energy"),
    ("physics-10", "gravitational potential energy", ("重力势能",), ("电势",), "mechanics", "mech-gravitational-potential-energy"),
    ("physics-11", "work", ("功",), ("能量",), "mechanics", "mech-work"),
    ("physics-12", "power", ("功率",), ("力",), "mechanics", "mech-power"),
    ("physics-13", "mechanical energy", ("机械能",), ("动能",), "mechanics", "mech-mechanical-energy"),
    ("physics-14", "conservation of momentum", ("动量守恒定律",), ("机械能守恒定律",), "mechanics", "mech-conservation-of-momentum"),
    ("physics-15", "conservation of mechanical energy", ("机械能守恒定律",), ("动量守恒定律",), "mechanics", "mech-conservation-of-mechanical-energy"),
    ("physics-16", "uniform circular motion", ("匀速圆周运动",), ("直线运动",), "mechanics", "mech-uniform-circular-motion"),
    ("physics-17", "centripetal force", ("向心力",), ("离心力",), "mechanics", "mech-centripetal-force"),
    ("physics-18", "angular velocity", ("角速度",), ("速度",), "mechanics", "mech-angular-velocity"),
    ("physics-19", "angular momentum", ("角动量",), ("力矩",), "mechanics", "mech-angular-momentum"),
    ("physics-20", "torque", ("力矩",), ("角动量",), "mechanics", "mech-torque"),
    ("physics-21", "electric charge", ("电荷",), ("电场",), "electricity", "elec-electric-charge"),
    ("physics-22", "electric field", ("电场",), ("电荷",), "electricity", "elec-electric-field"),
    ("physics-23", "electric potential", ("电势",), ("电势差",), "electricity", "elec-electric-potential"),
    ("physics-24", "potential difference", ("电势差",), ("电势",), "electricity", "elec-potential-difference"),
    ("physics-25", "capacitance", ("电容",), ("电荷",), "electricity", "elec-capacitance"),
)


ENGLISH_DEFINITIONS = {
    "displacement": "Displacement is a vector change in position from an initial point to a final point.",
    "velocity": "Velocity is the rate of change of displacement and includes direction.",
    "acceleration": "Acceleration is the rate of change of velocity with time.",
    "force": "Force is an interaction that can change an object's motion.",
    "mass": "Mass measures the amount of matter and appears in Newton's second law.",
    "inertia": "Inertia is the tendency of an object to resist changes in its motion.",
    "momentum": "Momentum is the product of mass and velocity.",
    "impulse": "Impulse is the product of force and the time interval during which the force acts.",
    "kinetic energy": "Kinetic energy is the energy an object has because of its motion.",
    "gravitational potential energy": "Gravitational potential energy is stored energy due to height in a gravitational field.",
    "work": "Work is the energy transferred when a force acts through a displacement.",
    "power": "Power is the rate at which work is done or energy is transferred.",
    "mechanical energy": "Mechanical energy is the sum of kinetic energy and potential energy.",
    "conservation of momentum": "Conservation of momentum says total momentum remains constant in an isolated system.",
    "conservation of mechanical energy": "Conservation of mechanical energy applies when only conservative forces do work.",
    "uniform circular motion": "Uniform circular motion is motion in a circle at constant speed.",
    "centripetal force": "Centripetal force is the net inward force required for circular motion.",
    "angular velocity": "Angular velocity is the rate of change of angular position.",
    "angular momentum": "Angular momentum describes rotational motion and depends on moment of inertia and angular velocity.",
    "torque": "Torque is the turning effect of a force about an axis.",
    "electric charge": "Electric charge is a property of matter that causes electric interactions.",
    "electric field": "Electric field is force per unit positive test charge at a point.",
    "electric potential": "Electric potential is electric potential energy per unit charge at a point.",
    "potential difference": "Potential difference is the difference in electric potential between two points.",
    "capacitance": "Capacitance is the charge stored per unit potential difference.",
}


CHINESE_DEFINITIONS = {
    "displacement": "位移（displacement）是从初位置指向末位置的位置变化量，具有方向。",
    "velocity": "速度（velocity）描述位移随时间变化的快慢和方向，应与速率区分。",
    "acceleration": "加速度（acceleration）是速度随时间变化的率。",
    "force": "力（force）是能够改变物体运动状态的相互作用。",
    "mass": "质量（mass）表示物体所含物质多少，并出现在牛顿第二定律中。",
    "inertia": "惯性（inertia）是物体保持原有运动状态的性质，不等同于质量本身。",
    "momentum": "动量（momentum）是物体质量与速度的乘积。",
    "impulse": "冲量（impulse）是力与作用时间间隔的乘积。",
    "kinetic energy": "动能（kinetic energy）是物体由于运动而具有的能量。",
    "gravitational potential energy": "重力势能（gravitational potential energy）是物体因高度和重力场而具有的势能。",
    "work": "功（work）是力在位移方向上转移能量的量。",
    "power": "功率（power）是做功或能量转移的快慢。",
    "mechanical energy": "机械能（mechanical energy）是动能和势能的总和。",
    "conservation of momentum": "动量守恒定律（conservation of momentum）说明孤立系统总动量保持不变。",
    "conservation of mechanical energy": "机械能守恒定律（conservation of mechanical energy）适用于只有保守力做功的情形。",
    "uniform circular motion": "匀速圆周运动（uniform circular motion）是在圆周上速率不变但速度方向不断改变的运动。",
    "centripetal force": "向心力（centripetal force）是维持圆周运动所需的指向圆心的合力。",
    "angular velocity": "角速度（angular velocity）是角位置随时间变化的率。",
    "angular momentum": "角动量（angular momentum）描述转动运动，与转动惯量和角速度有关。",
    "torque": "力矩（torque）是力使物体绕轴转动的效应。",
    "electric charge": "电荷（electric charge）是物质产生电相互作用的属性。",
    "electric field": "电场（electric field）表示单位正试探电荷在某点受到的力。",
    "electric potential": "电势（electric potential）是单位电荷在某点具有的电势能。",
    "potential difference": "电势差（potential difference）是两点电势的差值，也称电压。",
    "capacitance": "电容（capacitance）是单位电势差下储存的电荷量。",
}


CONFUSION_PARAGRAPHS = {
    "mechanics": (
        "Confusion checks: speed is scalar while velocity includes direction. "
        "Momentum and impulse are related but not identical. Work and energy share units, "
        "but work describes transfer. Angular momentum must not be confused with torque."
    ),
    "electricity": (
        "Confusion checks: electric potential is a point quantity, while potential difference "
        "compares two points. Electric field is not the same as electric charge."
    ),
}


def build_gold() -> list[GoldConcept]:
    return [
        GoldConcept(
            concept_id=concept_id,
            english_term=english_term,
            accepted_chinese_terms=accepted,
            rejected_confusions=rejected,
            required_english_evidence_ids=(_evidence_marker("EN", evidence_id),),
            required_chinese_evidence_ids=(_evidence_marker("ZH", evidence_id),),
            required_propositions=("definition",),
            forbidden_claims=("unsupported formula derivation", "unsupported synonym claim"),
            domain=domain,
        )
        for concept_id, english_term, accepted, rejected, domain, evidence_id in GOLD_ROWS
    ]


def build_corpus() -> list[SyntheticSource]:
    mechanics_terms = [row for row in GOLD_ROWS if row[4] == "mechanics"]
    electricity_terms = [row for row in GOLD_ROWS if row[4] == "electricity"]
    return [
        _english_source("english-mechanics", "English Mechanics", "english-mechanics.txt", "Mechanics", mechanics_terms),
        _chinese_source("chinese-mechanics", "Chinese Mechanics", "chinese-mechanics.txt", "Mechanics", mechanics_terms),
        _english_source("english-electricity", "English Electricity", "english-electricity.txt", "Electricity", electricity_terms),
        _chinese_source("chinese-electricity", "Chinese Electricity", "chinese-electricity.txt", "Electricity", electricity_terms),
    ]


def dataset_hashes() -> dict[str, str]:
    corpus = [source.to_dict(include_text=True) for source in build_corpus()]
    gold = [item.to_dict() for item in build_gold()]
    return {
        "corpus_sha256": sha256_json(corpus),
        "gold_sha256": sha256_json(gold),
    }


def gold_by_concept() -> dict[str, GoldConcept]:
    return {item.concept_id: item for item in build_gold()}


def english_term_to_concept_id() -> dict[str, str]:
    return {item.english_term.casefold(): item.concept_id for item in build_gold()}


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _english_source(source_id: str, title: str, filename: str, chapter: str, rows: list[tuple]) -> SyntheticSource:
    domain = "mechanics" if "Mechanics" in title else "electricity"
    lines = [
        f"{title}",
        "synthetic evaluation only, not authoritative teaching material",
        "",
    ]
    for _concept_id, english_term, _accepted, _rejected, _domain, evidence_id in rows:
        lines.extend([
            ENGLISH_DEFINITIONS[english_term],
            "",
        ])
    lines.append(CONFUSION_PARAGRAPHS[domain])
    return SyntheticSource(
        source_id=source_id,
        title=title,
        filename=filename,
        language="en",
        chapter=chapter,
        domain=domain,
        text="\n".join(lines),
    )


def _chinese_source(source_id: str, title: str, filename: str, chapter: str, rows: list[tuple]) -> SyntheticSource:
    domain = "mechanics" if "Mechanics" in title else "electricity"
    lines = [
        f"{title}",
        "synthetic evaluation only, not authoritative teaching material",
        "",
    ]
    for _concept_id, english_term, accepted, _rejected, _domain, evidence_id in rows:
        definition = CHINESE_DEFINITIONS[english_term].replace(
            f"{accepted[0]}（{english_term}）",
            f"{english_term} 即 {accepted[0]}",
        )
        lines.extend([
            definition,
            "",
        ])
    lines.append("易混概念提示：" + CONFUSION_PARAGRAPHS[domain])
    return SyntheticSource(
        source_id=source_id,
        title=title,
        filename=filename,
        language="zh",
        chapter=chapter,
        domain=domain,
        text="\n".join(lines),
    )


def _evidence_marker(language: str, evidence_id: str) -> str:
    normalized = str(evidence_id or "").upper().replace("-", "_")
    return f"EVIDENCE_{language}_{normalized}"
