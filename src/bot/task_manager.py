from collections import defaultdict
from dataclasses import dataclass
import logging


@dataclass
class RobotTask:
    task: str
    action: str = None


class TaskManager:
    def __init__(self, player):
        self.player = player
        self.opp_player = "player_1" if self.player == "player_0" else "player_0"
        self.bots = {}
        self.bot_factory = {}
        self.bot_targets = {}
        self.factory_queue = defaultdict(list)

    def refresh(self, map_state):
        self.map_state = map_state
        self.bot_targets = {k: v for k, v in self.bot_targets.items() if k in self.map_state.botpos}

    def get_factory_bots(self, unit_id):
        result = defaultdict(list)
        for bot, factory in self.bot_factory.items():
            if bot not in self.map_state.botpos.keys():
                continue
            if factory != unit_id:
                continue
            task = self.bots.get(bot)
            result[task.task].append(bot)
        return result

    def register_bot(self, unit_id, unit):
        """
        assign bot to the closest factory
        """

        if unit_id not in self.bots.keys():
            self.bots[unit_id] = ""

        if unit_id not in self.bot_factory.keys() or self.bot_factory[unit_id] not in self.map_state.factory_ids:
            factory_id, closest_factory_tile = self.map_state.get_closest_factory(unit.pos)
            self.bot_factory[unit_id] = factory_id
        else:
            closest_factory_tile = self.map_state.factories[self.bot_factory[unit_id]].pos
        return closest_factory_tile

    def get_bot_task(self, unit_id):
        if self.bots[unit_id] == "":
            task = "ice"
            logging.info("%s, assign new task, len queue %s", unit_id, len(self.factory_queue[self.bot_factory[unit_id]]))
            if len(self.factory_queue[self.bot_factory[unit_id]]) != 0:
                task = self.factory_queue[self.bot_factory[unit_id]].pop(0)
            self.bots[unit_id] = RobotTask(task)
            # self.factory_bots[self.bot_factory[unit_id]][task].append(unit_id)
            # print(self.game_state.real_env_steps, unit_id, "new task", task)
        return self.bots[unit_id]
