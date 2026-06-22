"""Tests for Priority Queue — section 6.7."""
from __future__ import annotations

import time
import pytest

from workers.priority_queue import Priority, PriorityTask, PriorityTaskQueue


class TestPriority:
    def test_ordering(self):
        assert Priority.CRITICAL < Priority.HIGH < Priority.NORMAL < Priority.LOW < Priority.IDLE

    def test_values(self):
        assert Priority.CRITICAL == 0
        assert Priority.HIGH == 10
        assert Priority.NORMAL == 50
        assert Priority.LOW == 100
        assert Priority.IDLE == 200


class TestPriorityTask:
    def test_creation(self):
        t = PriorityTask(
            priority=Priority.HIGH,
            sequence=0,
            ready_at=time.time() - 1,
            task_id="abc",
            name="test_task",
            payload={"x": 1},
        )
        assert t.is_ready is True

    def test_delayed_task_not_ready(self):
        t = PriorityTask(
            priority=Priority.NORMAL,
            sequence=0,
            ready_at=time.time() + 999,
            task_id="del-1",
            name="delayed",
        )
        assert t.is_ready is False

    def test_ordering_by_priority(self):
        high = PriorityTask(priority=Priority.HIGH, sequence=0, ready_at=0, task_id="h", name="h")
        low = PriorityTask(priority=Priority.LOW, sequence=1, ready_at=0, task_id="l", name="l")
        assert high < low


class TestPriorityTaskQueue:
    def test_push_pop_basic(self):
        q = PriorityTaskQueue()
        q.push("task1", priority=Priority.NORMAL)
        task = q.pop()
        assert task is not None
        assert task.name == "task1"

    def test_priority_ordering(self):
        q = PriorityTaskQueue()
        q.push("low",      priority=Priority.LOW)
        q.push("critical", priority=Priority.CRITICAL)
        q.push("normal",   priority=Priority.NORMAL)
        q.push("high",     priority=Priority.HIGH)

        names = [q.pop().name for _ in range(4)]
        assert names[0] == "critical"
        assert names[1] == "high"
        assert names[2] == "normal"
        assert names[3] == "low"

    def test_fifo_within_same_priority(self):
        q = PriorityTaskQueue()
        q.push("first",  priority=Priority.NORMAL)
        q.push("second", priority=Priority.NORMAL)
        q.push("third",  priority=Priority.NORMAL)
        names = [q.pop().name for _ in range(3)]
        assert names == ["first", "second", "third"]

    def test_delayed_task_not_popped_early(self):
        q = PriorityTaskQueue()
        q.push("delayed", priority=Priority.CRITICAL, delay_seconds=999)
        task = q.pop()
        assert task is None
        assert q.size() == 1

    def test_size_and_is_empty(self):
        q = PriorityTaskQueue()
        assert q.is_empty
        q.push("t1")
        assert q.size() == 1
        assert not q.is_empty

    def test_peek(self):
        q = PriorityTaskQueue()
        q.push("low",  priority=Priority.LOW)
        q.push("high", priority=Priority.HIGH)
        top = q.peek()
        assert top is not None
        assert top.name == "high"
        assert q.size() == 2  # unchanged

    def test_remove(self):
        q = PriorityTaskQueue()
        t = q.push("removable", task_id="rm-001")
        assert q.size() == 1
        removed = q.remove("rm-001")
        assert removed is True
        assert q.size() == 0

    def test_remove_nonexistent(self):
        q = PriorityTaskQueue()
        assert q.remove("nonexistent") is False

    def test_max_size_raises(self):
        q = PriorityTaskQueue(max_size=2)
        q.push("t1")
        q.push("t2")
        with pytest.raises(OverflowError):
            q.push("t3")

    def test_inspect(self):
        q = PriorityTaskQueue()
        q.push("task_a", priority=Priority.HIGH)
        q.push("task_b", priority=Priority.LOW)
        snapshot = q.inspect()
        assert len(snapshot) == 2
        assert all("task_id" in s for s in snapshot)
        assert all("priority" in s for s in snapshot)

    def test_ready_count(self):
        q = PriorityTaskQueue()
        q.push("ready1", priority=Priority.NORMAL)
        q.push("ready2", priority=Priority.HIGH)
        q.push("delayed", delay_seconds=999)
        assert q.ready_count() == 2

    def test_custom_task_id(self):
        q = PriorityTaskQueue()
        t = q.push("named", task_id="custom-id-123")
        assert t.task_id == "custom-id-123"

    def test_len_dunder(self):
        q = PriorityTaskQueue()
        q.push("a")
        q.push("b")
        assert len(q) == 2
