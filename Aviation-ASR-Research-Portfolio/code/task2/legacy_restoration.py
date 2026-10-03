from __future__ import annotations

import json
import re
from pathlib import Path


DIGITS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2",
    "to": "2", "too": "2", "tree": "3", "three": "3", "four": "4",
    "for": "4", "five": "5", "fife": "5", "six": "6", "seven": "7",
    "eight": "8", "ate": "8", "niner": "9", "nine": "9",
}
AMBIGUOUS_SINGLE_DIGITS = {"o", "oh", "to", "too", "for", "ate"}
UNSAFE_GENERIC_NUMBER_STARTS = {"to", "too", "for"}
ONES = {
    "zero": 0, "oh": 0, "o": 0, "one": 1, "two": 2, "to": 2, "too": 2,
    "tree": 3, "three": 3, "four": 4, "for": 4, "five": 5, "fife": 5,
    "six": 6, "seven": 7, "eight": 8, "ate": 8, "niner": 9, "nine": 9,
}
TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"hundred", "hundreds", "thousand", "thousands", "tousand", "tauzend"}
NUMBER_WORDS = set(ONES) | set(TEENS) | set(TENS) | SCALES
RUNWAY_SIDE = {"left": "L", "right": "R", "center": "C", "centre": "C"}
NATO_LETTERS = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliett": "J",
    "juliet": "J", "kilo": "K", "lima": "L", "mike": "M", "november": "N",
    "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S",
    "tango": "T", "uniform": "U", "victor": "V", "whiskey": "W", "xray": "X",
    "yankee": "Y", "zulu": "Z",
}


def normalize_spoken(text: str) -> str:
    text = str(text or "").lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9./]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def join_tokens(tokens: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(token for token in tokens if token)).strip()


def load_config(path: Path | str) -> dict:
    item = json.loads(Path(path).read_text(encoding="utf-8"))
    prefixes = item.get("stable_callsign_prefixes")
    if not isinstance(prefixes, dict):
        raise ValueError("restoration config has no stable_callsign_prefixes")
    return item


def digit_sequence(tokens: list[str], start: int, maximum: int) -> tuple[str | None, int, list[str]]:
    values = []
    index = start
    while index < len(tokens) and len(values) < maximum:
        token = tokens[index]
        if token not in DIGITS and not token.isdigit():
            break
        values.append(token)
        index += 1
    if not values:
        return None, start, []
    digits = "".join(DIGITS.get(token, token) for token in values)
    return digits, index, values


def number_value(words: list[str]) -> int | None:
    if not words:
        return None
    if all(word in DIGITS or word.isdigit() for word in words):
        return int("".join(DIGITS.get(word, word) for word in words))
    total = current = 0
    seen = False
    for word in words:
        if word.isdigit():
            current = current * 10 + int(word)
            seen = True
        elif word in ONES:
            current += ONES[word]
            seen = True
        elif word in TEENS:
            current += TEENS[word]
            seen = True
        elif word in TENS:
            current += TENS[word]
            seen = True
        elif word in {"hundred", "hundreds"}:
            current = max(current, 1) * 100
            seen = True
        elif word in {"thousand", "thousands", "tousand", "tauzend"}:
            total += max(current, 1) * 1000
            current = 0
            seen = True
        else:
            return None
    return total + current if seen else None


def restore(text: str, config: dict, return_trace: bool = False):
    tokens = normalize_spoken(text).split()
    stable_prefixes = {
        prefix: str(item["code"])
        for prefix, item in config["stable_callsign_prefixes"].items()
    }
    confidence_prefixes = {
        prefix: str(item["code"])
        for prefix, item in config.get("confidence_gated_callsign_prefixes", {}).items()
    }
    stable_prefixes.update(confidence_prefixes)
    output: list[str] = []
    trace: list[dict] = []
    index = 0

    def emit(kind: str, start: int, end: int, values: list[str]) -> None:
        output.extend(values)
        trace.append({
            "entity_type": kind,
            "source": " ".join(tokens[start:end]),
            "output": " ".join(values),
            "token_start": start,
            "token_end": end,
        })

    while index < len(tokens):
        matched = False
        for prefix, code in sorted(stable_prefixes.items(), key=lambda item: -len(item[0].split())):
            prefix_tokens = prefix.split()
            if tokens[index:index + len(prefix_tokens)] != prefix_tokens:
                continue
            digits, end, _ = digit_sequence(tokens, index + len(prefix_tokens), 5)
            if digits and 2 <= len(digits) <= 5:
                emit("callsign", index, end, [code + digits])
                index = end
                matched = True
                break
        if matched:
            continue

        token = tokens[index]
        if token == "pan" and index + 1 < len(tokens) and tokens[index + 1] == "pan":
            emit("urgency", index, index + 2, ["PANPAN"])
            index += 2
            continue

        if token in {"runway", "rwy"}:
            contextual_start = None
            contextual_prefix = []
            if tokens[index:index + 3] == ["runway", "in", "use"]:
                contextual_start = index + 3
                contextual_prefix = ["runway", "in", "use"]
            elif tokens[index:index + 3] == ["runway", "changed", "to"]:
                contextual_start = index + 3
                contextual_prefix = ["runway", "changed", "to"]
            if contextual_start is not None:
                digits, end, raw_digits = digit_sequence(tokens, contextual_start, 2)
                safe_single = len(raw_digits) != 1 or raw_digits[0] not in AMBIGUOUS_SINGLE_DIGITS
                if digits and safe_single:
                    side = ""
                    if end < len(tokens) and tokens[end] in RUNWAY_SIDE:
                        side = RUNWAY_SIDE[tokens[end]]
                        end += 1
                    emit("runway", index, end, contextual_prefix + [digits.zfill(2) + side])
                    index = end
                    continue
            digits, end, raw_digits = digit_sequence(tokens, index + 1, 2)
            safe_single = len(raw_digits) != 1 or raw_digits[0] not in AMBIGUOUS_SINGLE_DIGITS
            if digits and len(digits) <= 2 and safe_single:
                digits = digits.zfill(2)
                side = ""
                if end < len(tokens) and tokens[end] in RUNWAY_SIDE:
                    side = RUNWAY_SIDE[tokens[end]]
                    end += 1
                emit("runway", index, end, ["RWY", digits + side])
                index = end
                continue

        if token == "heading":
            digits, end, _ = digit_sequence(tokens, index + 1, 3)
            if digits and len(digits) == 3:
                emit("heading", index, end, ["heading", digits])
                index = end
                continue

        if token == "flight" and index + 1 < len(tokens) and tokens[index + 1] == "level":
            digits, end, _ = digit_sequence(tokens, index + 2, 3)
            if digits and 2 <= len(digits) <= 3:
                emit("flight_level", index, end, ["FL" + digits])
                index = end
                continue

        if token == "qnh":
            digits, end, _ = digit_sequence(tokens, index + 1, 4)
            if digits and len(digits) == 4:
                emit("qnh", index, end, ["QNH", digits])
                index = end
                continue

        if token == "squawk":
            digits, end, _ = digit_sequence(tokens, index + 1, 4)
            if digits and len(digits) == 4:
                emit("squawk", index, end, ["squawk", digits])
                index = end
                continue

        if token == "pob":
            digits, end, _ = digit_sequence(tokens, index + 1, 4)
            if digits and 2 <= len(digits) <= 4:
                emit("pob", index, end, ["POB", digits])
                index = end
                continue

        if token in {"temperature", "dewpoint"}:
            digits, end, _ = digit_sequence(tokens, index + 1, 2)
            if digits and 1 <= len(digits) <= 2:
                emit("weather_value", index, end, [token, digits])
                index = end
                continue

        if token == "number":
            digits, end, _ = digit_sequence(tokens, index + 1, 3)
            if digits:
                emit("sequence_number", index, end, ["No.", digits])
                index = end
                continue

        if token == "time" and index + 1 < len(tokens) and tokens[index + 1] == "at":
            digits, end, _ = digit_sequence(tokens, index + 2, 4)
            if digits and len(digits) == 4:
                emit("time", index, end, ["time", "at", digits])
                index = end
                continue

        if token in NATO_LETTERS:
            maximum = 6 if index > 0 and tokens[index - 1] == "numbered" else 3
            digits, end, _ = digit_sequence(tokens, index + 1, maximum)
            if digits:
                if index > 0 and tokens[index - 1] == "numbered" and len(digits) == 6:
                    rendered = NATO_LETTERS[token] + digits[:4] + "/" + digits[4:]
                    emit("notam_number", index, end, [rendered])
                else:
                    emit("surface_or_route_designator", index, end, [NATO_LETTERS[token] + digits])
                index = end
                continue

        digits, digit_end, _ = digit_sequence(tokens, index, 4)
        if digits and len(digits) == 4 and digit_end < len(tokens) and tokens[digit_end] == "utc":
            emit("time", index, digit_end + 1, [digits, "UTC"])
            index = digit_end + 1
            continue
        if digits and digit_end < len(tokens) and tokens[digit_end] == "decimal":
            right, right_end, _ = digit_sequence(tokens, digit_end + 1, 3)
            if right:
                emit("frequency", index, right_end, [digits + "." + right])
                index = right_end
                continue

        if (token in NUMBER_WORDS or token.isdigit()) and token not in UNSAFE_GENERIC_NUMBER_STARTS:
            end = index
            words = []
            while end < len(tokens) and len(words) < 8 and (
                tokens[end] in NUMBER_WORDS or tokens[end].isdigit()
            ):
                words.append(tokens[end])
                end += 1
            clock_suffix = bool(end < len(tokens) and tokens[end] == "clock" and words and words[-1] == "o")
            if clock_suffix:
                words = words[:-1]
            value = number_value(words)
            if value is not None and clock_suffix:
                emit("clock_position", index, end + 1, [str(value), "o'clock"])
                index = end + 1
                continue
            if value is not None and end < len(tokens):
                unit = tokens[end]
                if unit in {"meter", "meters", "metre", "metres", "m"}:
                    if end + 2 < len(tokens) and tokens[end + 1:end + 3] == ["per", "second"]:
                        emit("wind_speed", index, end + 3, [str(value), "m/s"])
                        index = end + 3
                        continue
                    emit("altitude_m", index, end + 1, [f"{value}m"])
                    index = end + 1
                    continue
                if unit in {"feet", "foot", "ft"}:
                    emit("altitude_ft", index, end + 1, [f"{value}ft"])
                    index = end + 1
                    continue
                if unit in {"kilometer", "kilometers", "kilometre", "kilometres", "km"}:
                    emit("distance", index, end + 1, [f"{value}km"])
                    index = end + 1
                    continue
                if unit in {"mile", "miles"}:
                    emit("distance", index, end + 1, [str(value), unit])
                    index = end + 1
                    continue
                if unit in {"knot", "knots", "kt"}:
                    emit("speed", index, end + 1, [f"{value}kt"])
                    index = end + 1
                    continue
                if unit in {"degree", "degrees"}:
                    rendered = str(value)
                    if all(word in DIGITS for word in words):
                        rendered = "".join(DIGITS[word] for word in words)
                    emit("degree", index, end + 1, [rendered, unit])
                    index = end + 1
                    continue
                if unit in {"minute", "minutes"}:
                    emit("duration", index, end + 1, [str(value), unit])
                    index = end + 1
                    continue
                if unit in NATO_LETTERS and "seat" in tokens[max(0, index - 4):index]:
                    emit("seat", index, end + 1, [str(value) + NATO_LETTERS[unit]])
                    index = end + 1
                    continue

        if token == "utc":
            emit("utc", index, index + 1, ["UTC"])
            index += 1
            continue
        if token == "mayday":
            emit("mayday", index, index + 1, ["MAYDAY"])
            index += 1
            continue
        output.append(token)
        index += 1

    restored = join_tokens(output)
    return (restored, trace) if return_trace else restored
