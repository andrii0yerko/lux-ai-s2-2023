from collections import Counter, defaultdict
import logging

import numpy as np
from bot.logging import BehaviourLoggingAdapter
from bot.task_manager import RobotTask, TaskManager
from bot.map_manager import MapManager
from lux.factory import Factory
from lux.kit import GameState


class FactoryBehaviour:
    def __init__(self, factory: Factory, game_state: GameState, manager: TaskManager, map_state: MapManager):
        self.factory = factory
        self.unit_id = self.factory.unit_id
        self.game_state = game_state
        self.manager = manager
        self.map_state = map_state
        self.robots = self.manager.get_factory_bots(self.factory.unit_id)

        logger = logging.getLogger(__class__.__name__)
        self.logger = BehaviourLoggingAdapter(logger, {"behaviour": self})
        # self.min_bots = {}

    def _under_attack(self):
        opp_botpos, opponent_unit_distances = self.map_state.get_tiles_distances(self.factory.pos, "enemy", "l2")
        if not len(opp_botpos):
            return False

        min_distance = opponent_unit_distances[0]
        self._closest_enemy = opp_botpos[0]
        return min_distance < 7

    def _have_defender(self):
        if not len(self.robots["defend"]):
            return False
        return True

    def _next_task(self):
        robots_num = Counter({task: len(robots) for task, robots in self.robots.items()})
        robots_num += Counter(self.manager.factory_queue[self.factory.unit_id])

        # NO. BOTS PER TASK
        self.logger.info("queue %s", self.manager.factory_queue.get(self.factory.unit_id))
        self.logger.info("task count %s", robots_num)

        # if (
        #     not robots_num["kill"]
        #     and (robots_num["ice"] or self.factory.can_build_n(self.game_state, 2, "HEAVY"))
        #     and self.factory.can_build_heavy(self.game_state)
        # ):
        #     return "kill"
        if not robots_num["ice"]:
            return "ice"
        # if robots_num["ore"] < 3:
        #     return "ore"
        if robots_num["rubble"] < 5:
            return "rubble"
        return None

    @property
    def min_bots(self):
        robots_num = Counter({task: len(robots) for task, robots in self.robots.items()})
        robots_num += Counter(self.manager.factory_queue[self.factory.unit_id])
        queue_order = [
            # ("kill", 1),
            ("ice", 1),
            # ("ore", 3),
            ("rubble", 5),
        ]

        min_bots = {}
        for task, desired_count in queue_order:
            min_bots[task] = desired_count
            if robots_num[task] < desired_count:
                break
        return min_bots

    def _rebalance_task(self):
        # TODO
        # It can cause issues with bots created on previous turn
        # We need to assign bots to tasks first, then rebalance/assign new

        heavies = defaultdict(
            list, {task: [robot for robot in robots if robot in self.map_state.botposheavy] for task, robots in self.robots.items()}
        )

        # At least one heavy should dig ice or factory will die (in the current approach with sequential task assigning)
        if not heavies["ice"] and (heavies["rubble"] or heavies["ore"]):
            new_bot = (heavies["rubble"] + heavies["ore"])[0]
            old_bot = None
            if self.robots["ice"]:
                old_bot = self.robots["ice"][0]

            prev_task = self.manager.bots[new_bot].task
            self.manager.bots[new_bot].task = "ice"
            if old_bot:
                self.manager.bots[old_bot].task = prev_task

    def _assign_defenders(self):
        preference = "HEAVY"

        # check if desired bot type available
        all_factory_bots = [x for v in self.robots.values() for x in v]

        heavies = {}
        for x in all_factory_bots:
            x_type = "HEAVY" if x in self.map_state.botposheavy else "LIGHT"
            if x_type == preference:
                heavies[x] = self.map_state.botposheavy[x]

        if not heavies:
            return False

        heavies_ids = list(heavies)
        heavies_pos = np.array(list(heavies.values()))

        unit_distances = np.mean((self._closest_enemy - heavies_pos) ** 2, 1)
        defender = heavies_ids[np.argmin(unit_distances)]

        self.manager.bots[defender] = RobotTask("defend")
        return True

    def _revoke_defenders(self):
        resid = {task: num - len(self.robots[task]) for task, num in self.min_bots.items()}

        for x in self.robots["defend"]:
            if resid.get("ice"):
                self.manager.bots[x] = RobotTask("ice")
                resid["ice"] -= 1
            elif resid.get("ore"):
                self.manager.bots[x] = RobotTask("ore")
                resid["ore"] -= 1
            else:
                self.manager.bots[x] = RobotTask("rubble")

    def _lichen_tiles_count(self):
        return np.sum(self.game_state.board.lichen_strains == self.factory.strain_id)

    def act(self):
        actions = {}
        unit_id = self.factory.unit_id
        game_state = self.game_state
        factory = self.factory

        self.next_bot_task = self._next_task()

        under_attack = self._under_attack()
        have_defenders = self._have_defender()

        if under_attack and not have_defenders:
            success = self._assign_defenders()
            if not success:
                self.next_bot_task = "defend"
        if not under_attack and have_defenders:
            self._revoke_defenders()

        self._rebalance_task()

        if self.next_bot_task is not None:
            if self.next_bot_task in [
                "kill",
                "defend",
            ]:
                if factory.can_build_heavy(game_state):
                    actions = {unit_id: factory.build_heavy()}
                    self.manager.factory_queue[unit_id].append(self.next_bot_task)
            elif self.next_bot_task in ["ice"]:
                if factory.can_build_heavy(game_state):
                    actions = {unit_id: factory.build_heavy()}
                    self.manager.factory_queue[unit_id].append(self.next_bot_task)
                elif factory.can_build_light(game_state):
                    actions = {unit_id: factory.build_light()}
                    self.manager.factory_queue[unit_id].append(self.next_bot_task)
            else:
                if factory.can_build_light(game_state):
                    actions = {unit_id: factory.build_light()}
                    self.manager.factory_queue[unit_id].append(self.next_bot_task)
                elif factory.can_build_heavy(game_state):
                    actions = {unit_id: factory.build_heavy()}
                    self.manager.factory_queue[unit_id].append(self.next_bot_task)

        # if not actions and factory.cargo.water > 100 and factory.power < 1000 and self._lichen_tiles_count() < 20:
        #     actions = {unit_id: factory.water()}

        step = game_state.real_env_steps
        if factory.can_water(game_state) and step > 800 and factory.cargo.water > (1000 - step) + 100:
            actions = {unit_id: factory.water()}

        return actions
