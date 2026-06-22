"""
MAGA Memory — 分级记忆系统
=============================
实现热 / 温 / 冷三层记忆架构：

- L1 热记忆：最近 N 轮完整对话 + 私密本子，不进摘要，直接注入 Prompt
- L2 温记忆：DM 生成的全局摘要，每轮更新，提供长期上下文
- L3 冷记忆：标记为 #CRITICAL 的事件，永久保留，按需检索

Usage:
    from engine.memory import MemoryManager
    mm = MemoryManager(global_hot_window=3)
    mm.add_public(player_id="p1", content="...")
    summary = mm.build_context_for_player(player_id="p1")
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from engine.schema import CriticalEvent, MemoryEntry, TieredMemory


class MemoryManager:
    """
    分级记忆管理器。

    每个玩家有独立的私密记忆空间（含公共 + 私密消息），
    另有一个全局记忆空间用于 DM 裁判。

    ┌─────────────────────────────────────────────────────┐
    │  Player A's View                                    │
    │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
    │  │ L1 热记忆 │  │  L2 温记忆    │  │  L3 冷记忆    │  │
    │  │ (最近3轮) │  │ (DM 摘要)     │  │ (关键事件)    │  │
    │  │ 完整对话   │  │ 全局战局概要   │  │ 永久归档     │  │
    │  └──────────┘  └──────────────┘  └──────────────┘  │
    └─────────────────────────────────────────────────────┘
    """

    def __init__(self, global_hot_window: int = 3, player_hot_window: int = 120):
        """
        Args:
            global_hot_window: 全局热记忆保留最近几轮
            player_hot_window: 每个玩家私密热记忆保留最近几轮
        """
        self.global_hot_window = global_hot_window
        self.player_hot_window = player_hot_window

        # 全局记忆（DM 用）
        self._global_memory = TieredMemory()

        # 每个玩家的私密记忆
        self._player_memories: dict[str, TieredMemory] = {}

        # 当前轮次
        self._current_round: int = 0

    # ── 公共 API ─────────────────────────────────────────────────

    def set_round(self, round_number: int) -> None:
        """设置当前轮次"""
        self._current_round = round_number

    def add_public(self, player_id: str, content: str, is_critical: bool = False) -> None:
        """
        添加一条公共发言到全局记忆和所有玩家记忆。

        Args:
            player_id: 发言玩家 ID
            content: 发言内容
            is_critical: 是否标记为关键事件，进入 L3 冷记忆
        """
        entry = MemoryEntry(
            round_number=self._current_round,
            content=f"[{player_id}]: {content}",
            is_critical=is_critical,
        )

        # 添加到全局
        self._global_memory.hot_memory.append(entry)
        if is_critical:
            self._global_memory.cold_memory.append(entry)

        # 添加到每个玩家的"公共可见"部分
        for mem in self._player_memories.values():
            mem.hot_memory.append(entry)
            if is_critical:
                mem.cold_memory.append(entry)

        # 清理过期热记忆
        self._trim_hot_memory(self._global_memory, self.global_hot_window)

    def add_private(self, player_id: str, content: str, is_critical: bool = False) -> None:
        """
        添加一条私密消息到指定玩家的记忆。
        DM 通过此方法向特定玩家发送秘密信息。

        Args:
            player_id: 目标玩家 ID
            content: 私密内容
            is_critical: 是否标记为关键事件
        """
        if player_id not in self._player_memories:
            self._player_memories[player_id] = TieredMemory(player_id=player_id)

        entry = MemoryEntry(
            round_number=self._current_round,
            content=content,
            is_critical=is_critical,
        )

        mem = self._player_memories[player_id]
        mem.hot_memory.append(entry)
        if is_critical:
            mem.cold_memory.append(entry)

        self._trim_hot_memory(mem, self.player_hot_window)

    def add_critical_event(self, event: CriticalEvent) -> None:
        """
        将 DM 标记的关键事件归档到 L3 冷记忆。

        Args:
            event: 关键事件对象
        """
        entry = MemoryEntry(
            round_number=event.round_number,
            content=event.event,
            is_critical=True,
            timestamp=event.timestamp,
        )

        # 添加到全局
        self._global_memory.cold_memory.append(entry)

        # 添加到相关玩家的私密记忆
        for pid in event.related_players:
            if pid in self._player_memories:
                self._player_memories[pid].cold_memory.append(entry)

    def update_warm_summary(self, summary: str) -> None:
        """
        更新 L2 温记忆（DM 生成的全局战局摘要）。
        每轮结算后调用。
        """
        self._global_memory.warm_summary = summary
        for mem in self._player_memories.values():
            mem.warm_summary = summary

    def register_player(self, player_id: str) -> None:
        """注册一个新玩家到记忆系统"""
        if player_id not in self._player_memories:
            self._player_memories[player_id] = TieredMemory(player_id=player_id)

    def build_context_for_player(self, player_id: str) -> str:
        """
        为指定玩家构建完整的上下文文本，用于注入 Prompt。

        按以下顺序拼接：
        1. L2 温记忆（全局战局摘要）
        2. L1 热记忆（最近几轮完整对话）
        3. 该玩家的私密本子（DM 秘密消息）

        Returns:
            拼接好的上下文字符串
        """
        mem = self._player_memories.get(player_id)
        if mem is None:
            return ""

        parts: list[str] = []

        # L2: 全局摘要
        if mem.warm_summary:
            parts.append(f"【全局战局摘要】\n{mem.warm_summary}")

        # L1: 最近对话
        if mem.hot_memory:
            recent = mem.hot_memory[-self.player_hot_window:]
            lines = [f"第{e.round_number}轮 {e.content}" for e in recent]
            parts.append(f"【近期公共对话】\n" + "\n".join(lines))

        # 私密消息（最后 5 条）
        private_entries = [e for e in mem.hot_memory if e.is_critical is False and "私密" in e.content]
        if private_entries:
            parts.append(f"【私密本子 - 仅你可见】\n" + "\n".join(e.content for e in private_entries[-5:]))

        return "\n\n".join(parts)

    def build_context_for_dm(self) -> str:
        """
        为 DM 构建完整的全局上下文。
        包含所有玩家的公开对话 + 秘密行动 + 全局摘要。
        """
        parts: list[str] = []

        # L2: 已有摘要
        if self._global_memory.warm_summary:
            parts.append(f"【上轮全局摘要】\n{self._global_memory.warm_summary}")

        # L1: 近期公开对话
        if self._global_memory.hot_memory:
            recent = self._global_memory.hot_memory[-self.global_hot_window * 2:]
            lines = [f"第{e.round_number}轮 {e.content}" for e in recent]
            parts.append(f"【全局公共对话记录】\n" + "\n".join(lines))

        # L3: 关键事件
        if self._global_memory.cold_memory:
            criticals = self._global_memory.cold_memory[-20:]
            lines = [f"🔴关键事件: {e.content}" for e in criticals]
            parts.append(f"【历史关键事件索引】\n" + "\n".join(lines))

        return "\n\n".join(parts)

    def get_player_notebook(self, player_id: str) -> list[str]:
        """
        获取玩家的私密本子（最近消息），供前端展示。
        """
        mem = self._player_memories.get(player_id)
        if mem is None:
            return []
        return [e.content for e in mem.hot_memory if "私密" in e.content][-10:]

    def get_critical_events(self) -> list[MemoryEntry]:
        """获取所有关键事件"""
        return list(self._global_memory.cold_memory)

    # ── 内部方法 ─────────────────────────────────────────────────

    def _trim_hot_memory(self, memory: TieredMemory, window: int) -> None:
        """
        裁剪热记忆，只保留最近 window 轮的内容。
        被裁剪的普通条目丢弃，关键条目迁移到冷记忆。
        """
        if len(memory.hot_memory) <= window * 10:
            return  # 还没到需要裁剪的程度

        current_round = self._current_round
        cutoff_round = current_round - window

        kept: list[MemoryEntry] = []
        for entry in memory.hot_memory:
            if entry.round_number >= cutoff_round:
                kept.append(entry)
            elif entry.is_critical:
                # 关键条目迁移到冷记忆
                memory.cold_memory.append(entry)

        memory.hot_memory = kept

    def reset(self) -> None:
        """重置所有记忆"""
        self._global_memory = TieredMemory()
        self._player_memories.clear()
        self._current_round = 0
