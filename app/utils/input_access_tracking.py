from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from typing import Any


class InputAccessTracker:
    def __init__(self) -> None:
        self._registered_paths: dict[str, set[str]] = defaultdict(set)
        self._read_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._access_types: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def wrap_source(self, source_name: str, value: Any) -> Any:
        normalized_source = str(source_name or "").strip() or "unknown"
        self._registered_paths[normalized_source].update(self._collect_paths(value))
        return self._wrap(normalized_source, value, "")

    def build_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for source_name, registered in self._registered_paths.items():
            read_counts = dict(self._read_counts.get(source_name, {}))
            used_paths = sorted(read_counts.keys())
            unused_paths = sorted(path for path in registered if path and path not in read_counts)
            summary[source_name] = {
                "used_paths": used_paths,
                "unused_paths": unused_paths,
                "read_counts": {path: read_counts[path] for path in used_paths},
                "access_types": {
                    path: sorted(self._access_types[source_name].get(path, set()))
                    for path in used_paths
                },
                "events": list(self._events.get(source_name, [])),
            }
        return summary

    def _wrap(self, source_name: str, value: Any, path: str) -> Any:
        if isinstance(value, TrackedDict) or isinstance(value, TrackedList):
            return value
        if isinstance(value, dict):
            return TrackedDict(value, tracker=self, source_name=source_name, path=path)
        if isinstance(value, list):
            return TrackedList(value, tracker=self, source_name=source_name, path=path)
        return value

    def record_access(self, source_name: str, path: str, access_type: str) -> None:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            return
        self._read_counts[source_name][normalized_path] += 1
        self._access_types[source_name][normalized_path].add(access_type)
        events = self._events[source_name]
        if len(events) >= 400:
            return
        events.append(
            {
                "timestamp": datetime.now().isoformat(),
                "path": normalized_path,
                "access_type": access_type,
            }
        )

    def _collect_paths(self, value: Any, prefix: str = "") -> set[str]:
        paths: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                next_path = f"{prefix}.{key}" if prefix else str(key)
                paths.add(next_path)
                paths.update(self._collect_paths(item, next_path))
            return paths
        if isinstance(value, list):
            for index, item in enumerate(value):
                next_path = f"{prefix}[{index}]" if prefix else f"[{index}]"
                paths.add(next_path)
                paths.update(self._collect_paths(item, next_path))
            return paths
        if prefix:
            paths.add(prefix)
        return paths


class TrackedDict(dict):
    def __init__(self, initial: dict[str, Any], *, tracker: InputAccessTracker, source_name: str, path: str) -> None:
        super().__init__(initial)
        self._tracker = tracker
        self._source_name = source_name
        self._path = path

    def _child_path(self, key: Any) -> str:
        key_text = str(key)
        return f"{self._path}.{key_text}" if self._path else key_text

    def _track(self, key: Any, access_type: str) -> str:
        child_path = self._child_path(key)
        self._tracker.record_access(self._source_name, child_path, access_type)
        return child_path

    def __getitem__(self, key: Any) -> Any:
        child_path = self._track(key, "__getitem__")
        return self._tracker._wrap(self._source_name, super().__getitem__(key), child_path)

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            child_path = self._track(key, "get")
            return self._tracker._wrap(self._source_name, super().get(key), child_path)
        return default

    def items(self) -> Iterator[tuple[Any, Any]]:
        for key in super().keys():
            child_path = self._track(key, "items")
            yield key, self._tracker._wrap(self._source_name, super().__getitem__(key), child_path)

    def values(self) -> Iterator[Any]:
        for key in super().keys():
            child_path = self._track(key, "values")
            yield self._tracker._wrap(self._source_name, super().__getitem__(key), child_path)

    def keys(self) -> Iterator[Any]:
        for key in super().keys():
            self._track(key, "keys")
            yield key

    def __iter__(self) -> Iterator[Any]:
        for key in super().keys():
            self._track(key, "__iter__")
            yield key

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            self._track(key, "__contains__")
        return super().__contains__(key)


class TrackedList(list):
    def __init__(self, initial: list[Any], *, tracker: InputAccessTracker, source_name: str, path: str) -> None:
        super().__init__(initial)
        self._tracker = tracker
        self._source_name = source_name
        self._path = path

    def _child_path(self, index: int) -> str:
        return f"{self._path}[{index}]" if self._path else f"[{index}]"

    def _track(self, index: int, access_type: str) -> str:
        child_path = self._child_path(index)
        self._tracker.record_access(self._source_name, child_path, access_type)
        return child_path

    def __getitem__(self, index: Any) -> Any:
        value = super().__getitem__(index)
        if isinstance(index, slice):
            result: list[Any] = []
            start = index.start or 0
            step = index.step or 1
            for offset, item in enumerate(value):
                child_path = self._track(start + (offset * step), "__getitem__slice")
                result.append(self._tracker._wrap(self._source_name, item, child_path))
            return result
        child_path = self._track(int(index), "__getitem__")
        return self._tracker._wrap(self._source_name, value, child_path)

    def __iter__(self) -> Iterator[Any]:
        for index, item in enumerate(super().__iter__()):
            child_path = self._track(index, "__iter__")
            yield self._tracker._wrap(self._source_name, item, child_path)
