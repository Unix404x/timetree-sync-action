from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar
from zoneinfo import ZoneInfo

LABEL_MARKER = "Étiquette TimeTree :"


def _extract_label_id(event: dict):
    """Return the TimeTree label id of an event, whatever the payload format."""
    label_id = event.get("label_id")
    if label_id is not None:
        return label_id
    try:
        rel_id = event["relationships"]["label"]["data"]["id"]
    except (KeyError, TypeError):
        return None
    if isinstance(rel_id, str) and "," in rel_id:
        rel_id = rel_id.split(",")[-1]
    try:
        return int(rel_id)
    except (TypeError, ValueError):
        return None


def _find_label(labels: dict | None, label_id) -> dict | None:
    if not labels or label_id is None:
        return None
    for key in (label_id, str(label_id)):
        if key in labels:
            return labels[key]
    try:
        wanted = int(str(label_id).split(",")[-1])
    except ValueError:
        return None
    for key, value in labels.items():
        try:
            if int(str(key).split(",")[-1]) == wanted:
                return value
        except ValueError:
            continue
    return None


@dataclass
class Event:
    SYNC_SOURCE: ClassVar[str] = "timetree-sync-action"

    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None = None
    description: str | None = None
    recurrences: list[str] | None = None
    label_name: str | None = None
    label_color: str | None = None

    @classmethod
    def from_timetree(cls, event: dict, labels: dict | None = None):
        label = _find_label(labels, _extract_label_id(event)) or {}
        start_tz = ZoneInfo(event["start_timezone"])
        end_tz = ZoneInfo(event["end_timezone"])

        return cls(
            id=event["uuid"] if "uuid" in event else event["id"],
            title=event["title"],
            start=datetime.fromtimestamp(
                event["start_at"] / 1000,
                tz=start_tz,
            ),
            end=datetime.fromtimestamp(
                event["end_at"] / 1000,
                tz=end_tz,
            ),
            all_day=event["all_day"],
            location=event.get("location") or None,
            description=event.get("note") or None,
            recurrences=event.get("recurrences") or None,
            label_name=(label.get("name") or None),
            label_color=(label.get("color") or None),
        )

    def google_description(self) -> str | None:
        """Note TimeTree, suivie d'une ligne avec l'étiquette (lue par Home Assistant)."""
        if not self.label_name and not self.label_color:
            return self.description
        tag = LABEL_MARKER + (f" {self.label_name}" if self.label_name else "")
        if self.label_color:
            color = self.label_color if self.label_color.startswith("#") else "#" + self.label_color
            tag += f" ({color.lower()})"
        tag = tag.strip()
        return f"{self.description}\n\n{tag}" if self.description else tag

    def to_google(self, calendar_code: str) -> dict:
        event = {
            "summary": self.title,
            "extendedProperties": {
                "private": {
                    "sync_source": self.SYNC_SOURCE,
                    "timetree_calendar_code": calendar_code,
                    "timetree_id": self.id,
                }
            },
        }

        if self.all_day:
            event["start"] = {
                "date": self.start.strftime("%Y-%m-%d"),
            }

            event["end"] = {
                "date": (self.end + timedelta(days=1)).strftime("%Y-%m-%d"),
            }

        else:
            timezone = self.start.tzinfo.key

            event["start"] = {
                "dateTime": self.start.isoformat(),
                "timeZone": timezone,
            }

            event["end"] = {
                "dateTime": self.end.isoformat(),
                "timeZone": timezone,
            }

        if self.location:
            event["location"] = self.location

        description = self.google_description()
        if description:
            event["description"] = description

        if self.recurrences:
            event["recurrence"] = self.recurrences

        return event

    def equals_google(self, google_event: dict, calendar_code: str) -> bool:
        google = self.to_google(calendar_code)

        return (
            google.get("summary") == google_event.get("summary")
            and google.get("location") == google_event.get("location")
            and google.get("description") == google_event.get("description")
            and google.get("start") == google_event.get("start")
            and google.get("end") == google_event.get("end")
            and google.get("recurrence") == google_event.get("recurrence")
        )
