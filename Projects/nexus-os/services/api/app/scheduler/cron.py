"""Five-field cron expressions, in a time zone. Pure and dependency-free.

    minute hour day-of-month month day-of-week

Each field takes ``*``, numbers, ranges ``a-b``, steps ``*/n`` or ``a-b/n``, and lists ``a,b``.
Months and weekdays also take names (``jan``, ``mon``); Sunday is 0 or 7. Shortcuts: ``@hourly``,
``@daily``, ``@weekly``, ``@monthly``, ``@yearly``. As in classic cron, when both day-of-month and
day-of-week are restricted, a day matches if *either* does. Times are computed in the schedule's
time zone (so "9:00" stays 9:00 across daylight-saving changes) and returned in UTC; a local time
skipped by a DST jump does not fire that day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SHORTCUTS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
DAYS = {d: i for i, d in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}
FIELDS: tuple[tuple[str, int, int, dict[str, int]], ...] = (
    ("minute", 0, 59, {}),
    ("hour", 0, 23, {}),
    ("day", 1, 31, {}),
    ("month", 1, 12, MONTHS),
    ("weekday", 0, 7, DAYS),
)
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


class CronError(ValueError):
    pass


@dataclass(frozen=True)
class CronSpec:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 = Sunday
    day_restricted: bool
    weekday_restricted: bool
    source: str

    def matches_day(self, d: datetime) -> bool:
        wd = (d.weekday() + 1) % 7  # Python: Monday = 0
        if self.day_restricted and self.weekday_restricted:
            return d.day in self.days or wd in self.weekdays
        return d.day in self.days and wd in self.weekdays


def _value(text: str, lo: int, hi: int, names: dict[str, int], field: str) -> int:
    t = text.strip().lower()
    if t in names:
        return names[t]
    if not t.isdigit():
        raise CronError(f"'{text}' is not a valid {field}.")
    v = int(t)
    if not lo <= v <= hi:
        raise CronError(f"{field.capitalize()} must be between {lo} and {hi} (got {v}).")
    return v


def _field(text: str, lo: int, hi: int, names: dict[str, int], field: str) -> tuple[frozenset[int], bool]:
    out: set[int] = set()
    for part in text.split(","):
        if not part:
            raise CronError(f"Empty item in the {field} field.")
        rng, _, step_s = part.partition("/")
        step = 1
        if step_s:
            if not step_s.isdigit() or int(step_s) == 0:
                raise CronError(f"'{step_s}' is not a valid step in the {field} field.")
            step = int(step_s)
        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, b = rng.split("-", 1)
            start, end = _value(a, lo, hi, names, field), _value(b, lo, hi, names, field)
            if start > end:
                raise CronError(f"The range {rng} in the {field} field goes backwards.")
        else:
            start = _value(rng, lo, hi, names, field)
            end = hi if step_s else start
        out.update(range(start, end + 1, step))
    return frozenset(out), text != "*"


def parse(expression: str) -> CronSpec:
    expr = SHORTCUTS.get(expression.strip().lower(), expression.strip())
    parts = expr.split()
    if len(parts) != 5:
        raise CronError(
            "A schedule needs five fields: minute hour day-of-month month day-of-week (e.g. '0 9 * * 1-5')."
        )
    values = [_field(p, lo, hi, names, name) for p, (name, lo, hi, names) in zip(parts, FIELDS, strict=True)]
    weekdays = frozenset(0 if d == 7 else d for d in values[4][0])
    return CronSpec(
        minutes=values[0][0],
        hours=values[1][0],
        days=values[2][0],
        months=values[3][0],
        weekdays=weekdays,
        day_restricted=values[2][1],
        weekday_restricted=values[4][1],
        source=expression.strip(),
    )


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise CronError(f"Unknown time zone '{name}'. Use a name like 'Europe/London' or 'UTC'.") from None


def next_after(spec: CronSpec, after: datetime, tz: str = "UTC") -> datetime:
    """The first matching minute strictly after ``after`` (aware), in UTC."""
    z = zone(tz)
    local = after.astimezone(z).replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = local.replace(hour=0, minute=0)
    for _ in range(366 * 5):  # every valid expression matches within a few years (Feb 29 at worst)
        if day.month in spec.months and spec.matches_day(day):
            for h in sorted(spec.hours):
                for m in sorted(spec.minutes):
                    candidate = datetime(day.year, day.month, day.day, h, m, tzinfo=z)
                    if candidate < local:
                        continue
                    # Skip wall-clock times that do not exist (the DST spring-forward gap).
                    roundtrip = candidate.astimezone(UTC).astimezone(z)
                    if (roundtrip.hour, roundtrip.minute) != (h, m):
                        continue
                    return candidate.astimezone(UTC)
        day = (day + timedelta(days=1)).replace(hour=0, minute=0)
    raise CronError("This schedule never runs (no date matches it).")


def upcoming(spec: CronSpec, after: datetime, tz: str = "UTC", count: int = 5) -> list[datetime]:
    out: list[datetime] = []
    t = after
    for _ in range(count):
        t = next_after(spec, t, tz)
        out.append(t)
    return out


def describe(spec: CronSpec) -> str:
    """A plain-language description of common shapes; anything else is described field by field."""
    mins, hours = sorted(spec.minutes), sorted(spec.hours)
    every_day = not spec.day_restricted and not spec.weekday_restricted and len(spec.months) == 12
    if len(mins) == 60 and len(hours) == 24 and every_day:
        return "Every minute"
    if len(mins) == 1 and len(hours) == 24 and every_day:
        return "Every hour" if mins[0] == 0 else f"Every hour at {mins[0]} minutes past"
    if len(mins) == 1 and len(hours) > 1 and every_day and len(hours) < 24:
        steps = {b - a for a, b in pairwise(hours)}
        if len(steps) == 1 and hours[0] == 0 and 24 % next(iter(steps)) == 0:
            return f"Every {next(iter(steps))} hours at :{mins[0]:02d}"
    if len(mins) == 1 and len(hours) == 1:
        at = f"{hours[0]:02d}:{mins[0]:02d}"
        if every_day:
            return f"Every day at {at}"
        if spec.weekday_restricted and not spec.day_restricted and len(spec.months) == 12:
            wd = sorted(spec.weekdays)
            if wd == [1, 2, 3, 4, 5]:
                return f"Weekdays at {at}"
            if wd == [0, 6]:
                return f"Weekends at {at}"
            return f"Every {', '.join(DAY_NAMES[d] for d in wd)} at {at}"
        if (
            spec.day_restricted
            and not spec.weekday_restricted
            and len(spec.months) == 12
            and len(spec.days) == 1
        ):
            return f"Monthly on day {next(iter(spec.days))} at {at}"
    return f"On the schedule '{spec.source}'"
